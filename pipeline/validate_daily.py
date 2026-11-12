#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日精读质量门禁：把《解读范式与模板》第八节的 8 条自检变成可执行规则。

核心是「防幻觉」：每段原文必须与 source.paragraphs 逐字一致，
highlights 必须是对应原文的子串。全自动流水线里原文由脚本直接填入，
这里是第二道保险。

用法：
  python3 pipeline/validate_daily.py --file frontend/public/content/daily/2026-11-10.json
  python3 pipeline/validate_daily.py --dir  frontend/public/content/daily --write
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from content_index import compute_hash
from fetch_rmrb import TOPIC_WORDS

EXAM_WORDS = re.compile(r"申论|面试|给定材料|考场|抄写|背诵|答题")
TEACH_WORDS = re.compile(r"大家|我们|同学们")
BANNED_WORDS = re.compile(r"本文认为|笔者|这篇文章写了|新闻摘要")
NOTE_YEAR = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")
NOTE_PAGE = re.compile(r"第\s*\d+\s*版")
NOTE_CHARS = re.compile(r"(?:共计|约|全文约)\s*\d+\s*字")


def norm(text: str) -> str:
    """空白归一化：用于逐字比对（允许排版空格差异）。"""
    return re.sub(r"\s+", " ", (text or "").replace("\u3000", " ").replace("\xa0", " ")).strip()


def validate_doc(doc: dict) -> dict:
    checks: list[dict] = []

    def check(cid: str, ok: bool, detail: str = "") -> None:
        checks.append({"id": cid, "ok": bool(ok), "detail": detail})

    # 1. 关键词是考点词，不是内容概括
    kws = doc.get("keywords") or []
    ok_kw = 2 <= len(kws) <= 5 and all(
        isinstance(k, str) and 2 <= len(k) <= 12 and not re.search(r"[，。！？；]", k)
        for k in kws
    )
    hits = sum(1 for k in kws if any(w in k for w in TOPIC_WORDS))
    check("keywords", ok_kw and hits >= 1, f"{len(kws)} 个，命中考点词 {hits} 个")

    source = doc.get("source") or {}
    paragraphs = source.get("paragraphs") or []
    segments = doc.get("segments") or []

    # 2. 每段原文后紧跟解析，无遗漏无合并
    indexes = [s.get("index") for s in segments]
    continuous = indexes == list(range(1, len(segments) + 1))
    body_ok = all(
        (s.get("original") or {}).get("text") and (s.get("analysis") or {}).get("text")
        for s in segments
    )
    check("segments", bool(segments) and len(segments) == len(paragraphs) and continuous and body_ok,
          f"segments={len(segments)} paragraphs={len(paragraphs)} 连续={continuous}")

    # 3. 每段点明功能 + 拆一种写法 + 摘一处可背表述
    weak = []
    for s in segments:
        a = s.get("analysis") or {}
        if not a.get("function") or not (a.get("devices") or []) or "<strong>" not in (a.get("html") or ""):
            weak.append(s.get("index"))
    check("per_segment", not weak, f"缺项的段落：{weak}" if weak else "每段齐全")

    # 4. ≥1 处概念/比喻讲解带答题边界，2–3 处举一反三
    concepts = [c for s in segments for c in ((s.get("analysis") or {}).get("concepts") or [])]
    examples = [e for s in segments for e in ((s.get("analysis") or {}).get("examples") or [])]
    boundaries = [c for c in concepts if (c.get("boundary") or "").strip()]
    check("concepts_examples", len(boundaries) >= 1 and len(examples) >= 2,
          f"概念边界 {len(boundaries)} 处，举一反三 {len(examples)} 处")

    # 5. ≥3 次落到考试语境
    all_analysis = "\n".join((s.get("analysis") or {}).get("text") or "" for s in segments)
    exam_hits = len(EXAM_WORDS.findall(all_analysis))
    check("exam_context", exam_hits >= 3, f"考试语境命中 {exam_hits} 次")

    # 6. 口吻是讲课，无「本文认为」
    banned = BANNED_WORDS.findall(all_analysis)
    teach = len(TEACH_WORDS.findall(all_analysis))
    check("tone", not banned and teach >= 3, f"禁用词 {len(banned)} 处，讲课称呼 {teach} 次")

    # 7. 【注】含来源/日期/版次/原题/字数/免责
    note = doc.get("note") or ""
    note_ok = all([
        "《人民日报》" in note,
        bool(NOTE_YEAR.search(note)),
        bool(NOTE_PAGE.search(note)),
        bool(re.search(r"《[^》]{2,40}》", note)),
        bool(NOTE_CHARS.search(note)),
        "仅供学习交流" in note,
    ])
    check("note", note_ok, "来源/日期/版次/原题/字数/免责")

    # 8. 原文逐字准确、highlights 为子串、来源链接可信
    verbatim = True
    bad_segments = []
    for i, s in enumerate(segments):
        orig = (s.get("original") or {}).get("text") or ""
        expected = paragraphs[i] if i < len(paragraphs) else ""
        if norm(orig) != norm(expected):
            verbatim = False
            bad_segments.append(s.get("index"))
        for h in (s.get("original") or {}).get("highlights") or []:
            if h and h not in orig:
                verbatim = False
                bad_segments.append(s.get("index"))
    url = source.get("originalUrl") or ""
    url_ok = (not url) or url.startswith("https://paper.people.com.cn/") or url.startswith("http://paper.people.com.cn/")
    check("verbatim", verbatim and url_ok,
          f"不一致段落 {sorted(set(bad_segments))}，来源域名={'ok' if url_ok else 'bad'}")

    # 9. 申论大作文结构骨架（本次新增）
    st = source.get("structure") or {}
    outline = st.get("outline") or []
    framework = ((doc.get("extras") or {}).get("frameworkTable") or [])
    roles = [str(r.get("role") or "") for r in framework if isinstance(r, dict)]
    sub_roles = [r for r in roles if r.startswith("分论点")]
    outline_ok = (not outline) or len(outline) == len(segments)
    status = st.get("status")
    if status in ("standard", "acceptable"):
        has_head = any(r == "总论点" for r in roles)
        has_tail = any(r == "结尾" for r in roles)
        structure_ok = has_head and len(sub_roles) >= 2 and has_tail
        detail = (f"status={status} 总论点={has_head} 分论点={len(sub_roles)} "
                  f"结尾={has_tail} outline={len(outline)}/{len(segments)}")
    else:
        # partial / weak / 旧数据：由讲义做结构提示，不阻断发布
        structure_ok = True
        detail = f"status={status or 'unknown'}（放宽；outline={len(outline)}/{len(segments)}）"
    check("essay_structure", outline_ok and structure_ok, detail)

    # 10. 严格分论点（选文硬门槛的二次保险：段首主张句 + 段内展开 + 语义独立）
    strict = st.get("strict") or {}
    if strict:
        s_pass = bool(strict.get("pass"))
        k = int(st.get("subThesisCount") or 0)
        pattern = st.get("pattern") or "无"
        strict_ok = s_pass and k >= 2 and len(sub_roles) >= 2 and pattern != "无"
        detail = (f"strictPass={s_pass} 分论点={k} 框架表分论点={len(sub_roles)} "
                  f"结构关系={pattern}")
        if status in ("partial", "weak", "legacy"):
            strict_ok = True  # 兜底发布时由讲义首段如实提示结构差异
            detail += "（partial/weak 放宽）"
    else:
        strict_ok = True
        detail = "旧数据无 strict 字段，放宽"
    check("strict_subtheses", strict_ok, detail)

    # 11. 多源来源署名与回链（版权 + SEO/GEO）
    has_source = bool(source.get("sourceName") or source.get("newspaper"))
    has_url = bool(source.get("originalUrl"))
    label_ok = bool(source.get("sourceLabel")) or source.get("newspaper") == "人民日报"
    check("source_attribution", has_source and has_url and label_ok,
          f"媒体={source.get('sourceName') or source.get('newspaper') or '缺失'} "
          f"标签={'Y' if source.get('sourceLabel') else 'N'} 回链={'Y' if has_url else 'N'}")

    passed = all(c["ok"] for c in checks)
    return {
        "passed": passed,
        "verbatimMatch": verbatim,
        "mode": "migrated" if source.get("provenance") == "migrated-lecture" else "generated",
        "checks": checks,
    }


def validate_file(path: Path, write: bool = False) -> tuple[bool, dict]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    report = validate_doc(doc)
    if write:
        doc["qualityReport"] = report
        doc["contentHash"] = compute_hash(doc)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report["passed"], {"file": str(path), "slug": doc.get("slug"),
                              "passed": report["passed"],
                              "failed": [c["id"] for c in report["checks"] if not c["ok"]]}


def main() -> None:
    ap = argparse.ArgumentParser(description="每日精读质量门禁")
    ap.add_argument("--file", help="单个讲义 JSON")
    ap.add_argument("--dir", help="讲义目录（批量）")
    ap.add_argument("--write", action="store_true", help="把 qualityReport / contentHash 写回 JSON")
    args = ap.parse_args()

    if not args.file and not args.dir:
        ap.error("需要 --file 或 --dir")

    targets: list[Path] = []
    if args.file:
        targets.append(Path(args.file).expanduser())
    if args.dir:
        d = Path(args.dir).expanduser()
        targets += sorted(p for p in d.glob("*.json")
                          if re.match(r"^\d{4}-\d{2}-\d{2}(-\d+)?\.json$", p.name))

    results = []
    all_ok = True
    for t in targets:
        if not t.exists():
            print(f"[error] 文件不存在：{t}", file=sys.stderr)
            all_ok = False
            continue
        ok, summary = validate_file(t, args.write)
        results.append(summary)
        all_ok = all_ok and ok

    print(json.dumps({"allPassed": all_ok, "count": len(results), "results": results},
                     ensure_ascii=False, indent=2))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
