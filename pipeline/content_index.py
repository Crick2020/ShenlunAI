#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日精读内容索引、关联文章与内容哈希。

被 parse_lecture_md.py 与 generate_daily.py 共用，是「单一数据源」的收口：
  - 扫描 daily/*.json 中 status=published 的讲义
  - 按关键词交集计算 relatedSlugs（打散上一篇/下一篇长链）
  - 计算 contentHash（供构建期增量预渲染判断）
  - 重建 index.json（全量）、index-recent.json（最近 RECENT_LIMIT 篇）、index-<year>.json（按年分片）

只用标准库。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from article_structure import compact

RECENT_LIMIT = 60
RELATED_LIMIT = 4
HASH_EXCLUDE = {"contentHash", "qualityReport", "generatedAt", "relatedSlugs"}
RESERVED_FILES = {"index.json", "index-recent.json", "daily.schema.json"}


def compute_hash(doc: dict) -> str:
    """内容指纹：排除易变的元数据与派生字段，只反映正文内容。"""
    payload = {k: v for k, v in doc.items() if k not in HASH_EXCLUDE}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_entry(doc: dict) -> dict:
    """清单条目：首页卡片、归档页、sitemap、RSS、llms.txt 共用。"""
    src = doc.get("source") or {}
    return {
        "date": doc.get("date"),
        "slug": doc.get("slug"),
        "edition": doc.get("edition", 1),
        "title": doc.get("title"),
        "keywords": doc.get("keywords") or [],
        "summary": doc.get("summary") or "",
        "source": {
            "newspaper": src.get("newspaper") or "人民日报",
            "paperDate": src.get("paperDate") or doc.get("date"),
            "page": src.get("page") or "",
            "column": src.get("column") or "",
            "author": src.get("author") or "",
            "charCount": src.get("charCount") or 0,
            "originalUrl": src.get("originalUrl") or "",
        },
        "segmentCount": len(doc.get("segments") or []),
        "structure": compact((doc.get("source") or {}).get("structure")),
        "status": doc.get("status"),
        "generatedAt": doc.get("generatedAt") or "",
        "contentHash": doc.get("contentHash") or "",
    }


def load_published(daily_dir: Path) -> list[tuple[Path, dict]]:
    items: list[tuple[Path, dict]] = []
    for path in sorted(daily_dir.glob("*.json")):
        if path.name in RESERVED_FILES or path.name.startswith("index-"):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if doc.get("status") == "published" and doc.get("slug"):
            items.append((path, doc))
    # 日期倒序，同日按 edition 升序
    items.sort(key=lambda it: (it[1].get("date") or "", -int(it[1].get("edition") or 1)), reverse=True)
    return items


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rebuild(daily_dir: Path) -> dict:
    """重建全部索引并回写 relatedSlugs / contentHash。返回统计信息。"""
    daily_dir = Path(daily_dir)
    daily_dir.mkdir(parents=True, exist_ok=True)
    items = load_published(daily_dir)

    # 相关文章：关键词交集最多的前 N 篇；不足时用相邻日期补齐，保证每篇都有内链
    for path, doc in items:
        kws = set(doc.get("keywords") or [])
        scored: list[tuple[int, int, str]] = []
        for other_path, other in items:
            if other_path == path:
                continue
            overlap = len(kws & set(other.get("keywords") or []))
            if overlap > 0:
                scored.append((overlap, _date_rank(other), other["slug"]))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        related = [slug for _, _, slug in scored[:RELATED_LIMIT]]
        if len(related) < 3:
            order = [it[1]["slug"] for it in items]
            pos = order.index(doc["slug"])
            for delta in (-2, -1, 1, 2, -3, 3):
                idx = pos + delta
                if 0 <= idx < len(order) and order[idx] not in related:
                    related.append(order[idx])
                if len(related) >= 3:
                    break
        related = related[:RELATED_LIMIT]
        changed = related != doc.get("relatedSlugs")
        doc["relatedSlugs"] = related
        new_hash = compute_hash(doc)
        if changed or new_hash != doc.get("contentHash"):
            doc["contentHash"] = new_hash
            write_json(path, doc)

    entries = [normalize_entry(doc) for _, doc in items]
    write_json(daily_dir / "index.json", entries)
    write_json(daily_dir / "index-recent.json", entries[:RECENT_LIMIT])

    years: dict[str, list[dict]] = {}
    for entry in entries:
        year = (entry.get("date") or "")[:4]
        if year:
            years.setdefault(year, []).append(entry)
    for year, year_entries in years.items():
        write_json(daily_dir / f"index-{year}.json", year_entries)

    # 清掉不再有内容的年份分片
    for stale in daily_dir.glob("index-????.json"):
        if stale.stem.split("-", 1)[-1] not in years:
            stale.unlink()

    return {
        "published": len(entries),
        "recent": min(len(entries), RECENT_LIMIT),
        "years": sorted(years.keys()),
        "slugs": [e["slug"] for e in entries],
    }


def _date_rank(doc: dict) -> int:
    """把日期转成可比较的整数，越新越大。"""
    try:
        return int((doc.get("date") or "0000-00-00").replace("-", ""))
    except ValueError:
        return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="重建每日精读索引 / 关联文章 / contentHash")
    ap.add_argument("--dir", required=True, help="daily JSON 目录")
    args = ap.parse_args()
    result = rebuild(Path(args.dir).expanduser())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
