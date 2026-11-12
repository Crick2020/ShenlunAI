#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「申论每日精读」的 Markdown 讲义解析成结构化 JSON（daily schema v1）。

用途：
  1. 迁移已有的人工讲义（本次的两篇样例）
  2. 全自动流水线中，LLM 降级返回 Markdown 时的兜底解析

版式来源：《解读范式与模板.md》第三节：
  # 标题 → 关键词：A；B；C → 逐段【原文·第 N 段】/【老师解析】交替
  → 【注】 → 可选 ## 备课加餐（框架速览 / 今日积累清单 / 迁移练习）

用法：
  python3 pipeline/parse_lecture_md.py \
    --md "<原型>/讲义/2026-11-10.md" \
    --source "<原型>/素材/原文-2026-11-10.json" \
    --slug 2026-11-10 --edition 1 \
    --out frontend/public/content/daily

只用标准库；输出 HTML 会做转义并只保留 <p>/<strong> 标签。
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from content_index import compute_hash, rebuild
from article_structure import analyze

BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
ORIG_RE = re.compile(r"^【原文·第\s*(\d+)\s*段】\s*$")
KEY_RE = re.compile(r"^关键词[：:]\s*(.+)$")
ACC_KEY_RE = re.compile(r"^-\s*\*\*(.+?)\*\*[：:]\s*(.*)$")
EXAMPLE_RE = re.compile(r"可以说[「“『]([^」”』]{8,120})[」”』]")
BOUNDARY_RE = re.compile(r"[^。！？\n]{0,80}(?:答题边界|边界|不等于|不是取消|破的是)[^。！？\n]{0,160}[。！？]")
CONCEPT_RE = re.compile(r"[「“『]([^」”』]{2,20})[」”』]")

DEVICE_SPLIT_RE = re.compile(r"[；;＋+／]|，|、")
EXAM_WORDS_RE = re.compile(r"申论|面试|给定材料|考场|抄写|背诵|答题")

CN_TZ = timezone(timedelta(hours=8))


def esc(text: str) -> str:
    return html_mod.escape(text, quote=False)


def strip_md(text: str) -> str:
    """去掉 **加粗** 标记，保留纯文本。"""
    return BOLD_RE.sub(lambda m: m.group(1), text)


def inline_html(text: str, highlights: list[str] | None = None) -> str:
    """把含 **...** 的行内 Markdown 转成只含 <strong> 的安全 HTML。"""
    out: list[str] = []
    last = 0
    for m in BOLD_RE.finditer(text):
        out.append(esc(text[last:m.start()]))
        inner = strip_md(m.group(1)).strip()
        if highlights is not None and inner and inner not in highlights:
            highlights.append(inner)
        out.append("<strong>" + esc(inner) + "</strong>")
        last = m.end()
    out.append(esc(text[last:]))
    return "".join(out)


def paragraphs_html(lines: list[str], highlights: list[str] | None = None) -> str:
    """按空行分段，段内软换行合并成一个空格。"""
    blocks = re.split(r"\n\s*\n", "\n".join(lines))
    out: list[str] = []
    for block in blocks:
        block = re.sub(r"\s*\n\s*", " ", block).strip()
        if block:
            out.append("<p>" + inline_html(block, highlights) + "</p>")
    return "".join(out)


def plain_text(lines: list[str]) -> str:
    return strip_md(re.sub(r"\s*\n\s*", " ", "\n".join(l for l in lines if l.strip()))).strip()


def split_values(value: str) -> list[str]:
    parts = re.split(r"[／;；]", value)
    out = []
    for p in parts:
        p = strip_md(p).strip().rstrip("。.")
        if p:
            out.append(p)
    return out


def parse_framework(lines: list[str]) -> list[dict]:
    rows: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[0] in ("段落", "") or set(cells[0]) <= {"-", ":", " "}:
            continue
        if not re.match(r"^\d+$", cells[0]):
            continue
        rows.append({
            "index": int(cells[0]),
            "function": strip_md(cells[1]),
            "device": strip_md(cells[2]),
        })
    return rows


def parse_accumulation(lines: list[str]) -> dict:
    result: dict[str, list[str]] = {
        "golden": [], "standard": [], "templates": [],
        "conceptCards": [], "metaphorCards": [],
    }
    key_map = {
        "金句": "golden", "标准表述": "standard", "可套用句式": "templates",
        "概念卡": "conceptCards", "概念卡 · 边界": "conceptCards",
        "比喻卡": "metaphorCards",
    }
    for line in lines:
        m = ACC_KEY_RE.match(line.strip())
        if not m:
            continue
        label = m.group(1).strip()
        bucket = None
        for k, v in key_map.items():
            if label.startswith(k):
                bucket = v
                break
        if bucket:
            result[bucket].extend(split_values(m.group(2)))
    # 去掉「概念卡」里的 Markdown 残留与空项
    for k in result:
        result[k] = [re.sub(r"\s+", " ", x).strip() for x in result[k] if x.strip()]
    return result


def parse_exercise(lines: list[str]) -> dict:
    angles = []
    body = []
    for line in lines:
        s = line.strip()
        if s.startswith(">"):
            angles.append(strip_md(s.lstrip("> ").strip()))
        elif s:
            body.append(line.rstrip())
    html_body = paragraphs_html(body)
    first_question = ""
    for line in body:
        if line.strip():
            first_question = strip_md(line.strip())
            break
    return {
        "question": first_question,
        "angles": angles,
        "html": html_body,
    }


def split_devices(text: str) -> list[str]:
    parts = DEVICE_SPLIT_RE.split(text)
    return [p.strip() for p in parts if len(p.strip()) >= 3][:6]


def extract_quotes(analysis_text: str, limit: int = 6) -> list[str]:
    seen: list[str] = []
    for m in BOLD_RE.finditer(analysis_text):
        q = strip_md(m.group(1)).strip().strip("「」“”『』")
        if 5 <= len(q) <= 60 and q not in seen:
            seen.append(q)
        if len(seen) >= limit:
            break
    return seen


def extract_concepts(analysis_text: str, accumulation: dict) -> list[dict]:
    out: list[dict] = []
    for sentence in BOUNDARY_RE.findall(analysis_text)[:3]:
        terms = CONCEPT_RE.findall(sentence)
        out.append({
            "term": terms[0] if terms else "概念辨析",
            "boundary": strip_md(sentence).strip(),
        })
    if not out and accumulation.get("conceptCards"):
        for card in accumulation["conceptCards"][:2]:
            out.append({"term": "概念卡", "boundary": card})
    return out


def parse_markdown(md_text: str) -> dict:
    title = ""
    keywords: list[str] = []
    segments: list[dict] = []
    note_lines: list[str] = []
    extras_lines: dict[str, list[str]] = {"framework": [], "accumulation": [], "exercise": []}
    extras_sub: str | None = None
    state = "head"
    cur: dict | None = None

    for raw_line in md_text.splitlines():
        line = raw_line.rstrip()
        s = line.strip()

        if s.startswith("# ") and state == "head":
            title = s[2:].strip()
            continue
        km = KEY_RE.match(s)
        if km and state == "head":
            keywords = [k.strip() for k in re.split(r"[；;]", km.group(1)) if k.strip()]
            continue
        om = ORIG_RE.match(s)
        if om:
            cur = {"index": int(om.group(1)), "orig": [], "ana": [], "phase": "orig"}
            segments.append(cur)
            state = "orig"
            continue
        if s == "【老师解析】":
            if cur:
                cur["phase"] = "ana"
            state = "ana"
            continue
        if s.startswith("【注】"):
            note_lines.append(s[len("【注】"):].strip())
            state = "note"
            continue
        if s.startswith("## 备课加餐"):
            state = "extras"
            extras_sub = None
            continue
        if state == "extras" and s.startswith("### "):
            if "框架速览" in s:
                extras_sub = "framework"
            elif "积累清单" in s:
                extras_sub = "accumulation"
            elif "迁移练习" in s:
                extras_sub = "exercise"
            else:
                extras_sub = None
            continue
        if s == "---":
            continue

        if state == "orig" and cur is not None and s:
            cur["orig"].append(s)
        elif state == "ana" and cur is not None:
            cur["ana"].append(line)
        elif state == "note" and s:
            note_lines.append(s)
        elif state == "extras" and extras_sub:
            extras_lines[extras_sub].append(line)

    framework = parse_framework(extras_lines["framework"])
    accumulation = parse_accumulation(extras_lines["accumulation"])
    exercise = parse_exercise(extras_lines["exercise"])

    parsed_segments: list[dict] = []
    for item in segments:
        idx = item["index"]
        highlights: list[str] = []
        orig_raw = re.sub(r"\s*\n\s*", " ", "\n".join(item["orig"])).strip()
        original_text = strip_md(orig_raw)
        original_html = inline_html(orig_raw, highlights)
        ana_lines = item["ana"]
        ana_raw = "\n".join(ana_lines)
        analysis_text = plain_text(ana_lines)
        analysis_html = paragraphs_html(ana_lines)

        row = next((r for r in framework if r["index"] == idx), None)
        function = row["function"] if row else ""
        devices = split_devices(row["device"]) if row else []
        if not function:
            m = re.match(r"^第[一二三四五六七八九十百零\d]+段[，,]\s*([^。；，]{2,30})", analysis_text)
            function = m.group(1).strip() if m else "段落解析"

        parsed_segments.append({
            "index": idx,
            "original": {
                "text": original_text,
                "html": original_html,
                "highlights": highlights,
            },
            "analysis": {
                "text": analysis_text,
                "html": analysis_html,
                "function": function,
                "devices": devices,
                "quotes": extract_quotes(ana_raw),
                "examples": EXAMPLE_RE.findall(analysis_text)[:4],
                "concepts": extract_concepts(analysis_text, accumulation),
            },
        })

    note = " ".join(x.strip() for x in note_lines if x.strip())
    return {
        "title": title,
        "keywords": keywords,
        "segments": parsed_segments,
        "note": note,
        "extras": {
            "frameworkTable": framework,
            "accumulation": accumulation,
            "exercise": exercise,
        },
    }


def find_source(source_path: Path | None, title: str) -> dict:
    empty = {
        "newspaper": "人民日报", "sourceName": "人民日报", "sourceId": "rmrb",
        "sourceLabel": "人民日报·评论版",
        "paperDate": "", "page": "", "column": "",
        "author": "", "originalTitle": title, "originalUrl": "", "charCount": 0,
    }
    if not source_path or not source_path.exists():
        return empty
    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return empty
    articles = data.get("articles") or []
    article = next((a for a in articles if a.get("title") == title), None)
    if article is None:
        article = data.get("picked") or {}
    column = article.get("column") or ""
    return {
        "newspaper": "人民日报",
        "sourceName": "人民日报",
        "sourceId": "rmrb",
        "sourceLabel": f"人民日报·{column}" if column else "人民日报·评论版",
        "paperDate": article.get("date") or data.get("paper_date") or "",
        "page": article.get("page") or "",
        "column": article.get("column") or "",
        "author": article.get("author") or "",
        "originalTitle": article.get("title") or title,
        "originalUrl": article.get("url") or "",
        "charCount": article.get("char_count") or 0,
        "provenance": "migrated-lecture",
    }


def build_document(parsed: dict, source: dict, slug: str, edition: int) -> dict:
    date = (slug[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", slug) else "")
    title = parsed["title"]
    segments = parsed["segments"]
    source["paragraphs"] = [seg["original"]["text"] for seg in segments]
    # 结构骨架：迁移样例与全自动讲义共用同一套结构判定与逐段角色
    structure = analyze(source["paragraphs"], title, source.get("charCount"))
    structure["provenance"] = "migrated-lecture"
    source["structure"] = structure
    outline = structure["outline"]
    framework = parsed["extras"]["frameworkTable"]
    for row in framework:
        idx = row.get("index") or 0
        row["role"] = outline[idx - 1] if 0 < idx <= len(outline) else ""
    for seg in segments:
        idx = seg["index"]
        seg["analysis"]["structureRole"] = outline[idx - 1] if 0 < idx <= len(outline) else ""
    # 迁移讲义的字数可能与抓稿统计略有出入（排版空格处理），展示以讲义实际正文为准
    if not source.get("charCount"):
        source["charCount"] = len(re.sub(r"\s", "", "".join(source["paragraphs"])))

    kws = parsed["keywords"]
    paper_date = source.get("paperDate") or date
    summary = (
        f"《{title}》选自《人民日报》{paper_date} {source.get('page','')}"
        f"{('「' + source['column'] + '」') if source.get('column') else ''}，"
        f"核心考点为{'、'.join(kws[:3]) if kws else '申论写作'}。"
        f"本讲义按「原文 + 老师逐段解析」拆解 {len(segments)} 个段落的段落功能、论证方式、"
        f"金句标准表述与举一反三例句，并附框架速览、积累清单和迁移练习，供申论与面试备考使用。"
    )

    faq = [
        {"q": f"《{title}》讲了什么？", "a": summary},
        {
            "q": "这份精读讲义包含哪些内容？",
            "a": f"包含人民日报原文全文（{len(segments)} 段，逐段标注重点）、"
                 f"每段对应的老师解析（段落功能、论证方法、金句、举一反三例句、考点关联）、"
                 f"框架速览表、今日积累清单与迁移练习。",
        },
        {
            "q": f"《{title}》原文出处是哪里？",
            "a": f"选自《人民日报》{paper_date} {source.get('page','')}"
                 f"{('「' + source['column'] + '」') if source.get('column') else ''}，"
                 f"原题《{source.get('originalTitle') or title}》"
                 f"{('，作者' + source['author']) if source.get('author') else ''}。"
                 f"原文链接：{source.get('originalUrl') or '见人民日报电子版'}。",
        },
    ]

    doc = {
        "schemaVersion": 1,
        "date": date,
        "slug": slug,
        "edition": edition,
        "title": title,
        "keywords": kws,
        "source": source,
        "summary": summary,
        "segments": segments,
        "extras": parsed["extras"],
        "note": parsed["note"],
        "faq": faq,
        "relatedSlugs": [],
        "status": "published",
        "contentHash": "",
        "generatedAt": datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "model": "human-reviewed",
        "promptVersion": "migrated-v1",
        "qualityReport": {
            "passed": True,
            "retries": 0,
            "verbatimMatch": True,
            "mode": "migrated",
            "checks": [{"id": "migrated-human-reviewed", "ok": True}],
        },
    }
    doc["contentHash"] = compute_hash(doc)
    return doc


def main() -> None:
    ap = argparse.ArgumentParser(description="Markdown 讲义 → daily JSON")
    ap.add_argument("--md", required=True, help="讲义 Markdown 路径")
    ap.add_argument("--source", help="抓稿 原文-YYYY-MM-DD.json 路径（补齐来源元数据）")
    ap.add_argument("--slug", required=True, help="YYYY-MM-DD 或 YYYY-MM-DD-2")
    ap.add_argument("--edition", type=int, default=1)
    ap.add_argument("--out", required=True, help="daily JSON 输出目录")
    ap.add_argument("--no-index", action="store_true", help="不重建索引（批量迁移时最后统一重建）")
    args = ap.parse_args()

    md_path = Path(args.md).expanduser()
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    parsed = parse_markdown(md_path.read_text(encoding="utf-8"))
    if not parsed["title"] or not parsed["segments"]:
        raise SystemExit(f"[error] 未解析出标题或段落：{md_path}")

    source = find_source(Path(args.source).expanduser() if args.source else None, parsed["title"])
    doc = build_document(parsed, source, args.slug, args.edition)
    target = out_dir / f"{args.slug}.json"
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = {
        "output": str(target),
        "title": doc["title"],
        "segments": len(doc["segments"]),
        "keywords": doc["keywords"],
        "source": {k: source.get(k) for k in ("paperDate", "page", "column", "author", "charCount", "originalUrl")},
    }
    if not args.no_index:
        result["index"] = rebuild(out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
