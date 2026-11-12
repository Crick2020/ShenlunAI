#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日精读全自动编排：抓稿 → 选文 → 逐段生成解析 → 质量门禁 → 落盘 → 重建索引。

核心防幻觉设计：**原文段落不经过 LLM**，直接由 fetch_rmrb 的 picked.paragraphs 逐字填入；
模型只生成解析与必须是原文子串的 highlights。因此「逐字准确」是结构性保证，
validate_daily.py 只是第二道保险。

用法：
  python3 pipeline/generate_daily.py --date 2026-11-10 --out frontend/public/content/daily
  python3 pipeline/generate_daily.py --date 2026-11-10 --pick "烟火气" --redo --out ...
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fetch_sources
import article_structure
from content_index import compute_hash, rebuild
from llm_client import chat_json
from parse_lecture_md import esc, paragraphs_html, plain_text
from validate_daily import validate_doc

CN_TZ = timezone(timedelta(hours=8))
PROMPT_FILE = Path(__file__).with_name("lecture_prompt.md")
BATCH_SIZE = 2
MAX_QUALITY_RETRIES = 2
PROMPT_VERSION = "lecture-v3"
# 当天无结构达标文章时，最多回溯几期报纸（可用环境变量覆盖）
DEFAULT_ESSAY_LOOKBACK = max(0, min(14, int(os.getenv("ESSAY_LOOKBACK_DAYS") or "5")))
# 版权降级开关：默认 full（全文公开）；设为 excerpt 时只展示每段前 80 字，
# 用于将来需要收缩原文转载范围的场景，无需改数据结构。
CONTENT_MODE = (os.getenv("DAILY_CONTENT_MODE") or "full").strip().lower()
EXCERPT_CHARS = 80


def apply_content_mode(doc: dict) -> dict:
    if CONTENT_MODE != "excerpt":
        return doc
    for seg in doc["segments"]:
        text = seg["original"]["text"]
        if len(text) <= EXCERPT_CHARS:
            continue
        cut = text[:EXCERPT_CHARS] + "……"
        seg["original"]["text"] = cut
        seg["original"]["html"] = esc(cut)
        seg["original"]["highlights"] = [h for h in seg["original"]["highlights"] if h in cut]
    doc["source"]["paragraphs"] = [s["original"]["text"] for s in doc["segments"]]
    doc["note"] = doc["note"].replace("原文照录，未作删改", "原文为节选，未作改写")
    return doc


def load_system() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def highlight_html(text: str, highlights: list[str]) -> tuple[str, list[str]]:
    """把原文子串包成 <strong>；不在原文里的 highlight 直接丢弃。"""
    marks: list[tuple[int, int]] = []
    accepted: list[str] = []
    for h in sorted(set(x for x in highlights if x), key=len, reverse=True):
        if h not in text:
            continue
        start = 0
        found = False
        while True:
            i = text.find(h, start)
            if i < 0:
                break
            if not any(i < e and i + len(h) > s for s, e in marks):
                marks.append((i, i + len(h)))
                found = True
                break
            start = i + len(h)
        if found:
            accepted.append(h)
    marks.sort()
    out: list[str] = []
    last = 0
    for s, e in marks:
        out.append(esc(text[last:s]))
        out.append("<strong>" + esc(text[s:e]) + "</strong>")
        last = e
    out.append(esc(text[last:]))
    return "".join(out), accepted[:3]


def load_used_urls(out_dir: Path, exclude_slug: str | None = None) -> set[str]:
    """已发布讲义用过的原文 URL，避免回溯时重复选同一篇。"""
    urls: set[str] = set()
    for path in out_dir.glob("*.json"):
        if not re.match(r"^\d{4}-\d{2}-\d{2}(-\d+)?\.json$", path.name):
            continue
        if exclude_slug and path.stem == exclude_slug:
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        url = ((doc.get("source") or {}).get("originalUrl") or "").strip()
        if url:
            urls.add(url)
    return urls


def first_qualified(arts: list[dict], used_urls: set[str]) -> dict | None:
    """结构达标、申论文风达标且原文未被用过的第一篇；无达标者时退回结构达标首篇。"""
    candidates = [
        a for a in arts
        if (a.get("url") or "").strip() not in used_urls
        and a.get("structure", {}).get("essayLike")
    ]
    for a in candidates:
        if (a.get("structure", {}).get("essayFlavor") or {}).get("value", 0) >= 55:
            return a
    return candidates[0] if candidates else None


def build_source(picked: dict, paper_date: str, selection_note: str = "") -> dict:
    paragraphs = list(picked.get("paragraphs") or [])
    structure = picked.get("structure") or article_structure.analyze(
        paragraphs, picked.get("title") or "", picked.get("char_count")
    )
    return {
        "newspaper": picked.get("sourceName") or "人民日报",
        "sourceName": picked.get("sourceName") or "人民日报",
        "sourceId": picked.get("source") or "rmrb",
        "sourceLabel": picked.get("sourceLabel")
                       or (f"人民日报·{picked.get('column') or '评论版'}"),
        "paperDate": picked.get("date") or paper_date,
        "page": picked.get("page") or "",
        "column": picked.get("column") or "",
        "author": picked.get("author") or "",
        "originalTitle": picked.get("title") or "",
        "originalUrl": picked.get("url") or "",
        "charCount": picked.get("char_count") or len(re.sub(r"\s", "", "".join(paragraphs))),
        "paragraphs": paragraphs,
        "provenance": "fetch_sources",
        "structure": structure,
        **({"selectionNote": selection_note} if selection_note else {}),
    }


def source_phrase(source: dict, long_date: bool = False) -> str:
    """统一的来源描述：报纸带版次，网站带栏目，覆盖多官媒来源。"""
    raw = source.get("paperDate") or ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if long_date:
        date_text = (f"{m.group(1)} 年 {int(m.group(2))} 月 {int(m.group(3))} 日"
                     if m else raw)
    else:
        date_text = raw
    name = source.get("sourceName") or "人民日报"
    label = source.get("sourceLabel") or name
    page = source.get("page") or ""
    column = source.get("column") or ""
    if name == "人民日报" and page:
        return f"《{name}》{date_text} {page}" + (f"「{column}」" if column else "")
    return f"{label} {date_text}".strip()


def build_note(source: dict) -> str:
    prefix = source.get("selectionNote") or ""
    return (
        prefix +
        f"本文选自{source_phrase(source, long_date=True)}，"
        f"原题《{source.get('originalTitle','')}》"
        f"{('，作者 ' + source['author']) if source.get('author') else ''}，"
        f"全文共计 {source.get('charCount', 0)} 字。"
        "原文照录，未作删改，按申论考试要求进行了逐段编号、重点标注与分析，仅供学习交流使用。"
    )


def fallback_summary(title: str, source: dict, keywords: list[str], n: int) -> str:
    st = (source.get("structure") or {})
    skeleton = (f"，具备总论点、{st.get('subThesisCount', 0)} 个分论点与结尾的完整大作文结构"
                if st.get("essayLike") else "")
    return (
        f"《{title}》选自{source_phrase(source)}{skeleton}，"
        f"核心考点为{'、'.join(keywords[:3]) if keywords else '申论写作'}。"
        f"本讲义按「原文 + 老师逐段解析」拆解 {n} 个段落的段落功能、论证方式、"
        f"金句标准表述与举一反三例句，并附框架速览、积累清单和迁移练习，供申论与面试备考使用。"
    )


def fallback_faq(title: str, source: dict, summary: str, n: int) -> list[dict]:
    return [
        {"q": f"《{title}》讲了什么？", "a": summary},
        {"q": "这份精读讲义包含哪些内容？",
         "a": f"包含原文全文（{n} 段，逐段标注重点）、每段对应的老师解析"
              f"（段落功能、论证方法、金句、举一反三例句、考点关联）、框架速览表、今日积累清单与迁移练习。"},
        {"q": f"《{title}》原文出处是哪里？",
         "a": f"选自{source_phrase(source)}，原题《{source.get('originalTitle', title)}》。"
              f"原文链接：{source.get('originalUrl') or '见原刊电子版'}。"},
    ]


def generate_segments(system: str, title: str, paragraphs: list[str],
                      outline: list[str] | None = None, feedback: str = "",
                      source_label: str = "", pattern: str = "") -> list[dict]:
    full_text = "\n".join(f"【第 {i + 1} 段】{p}" for i, p in enumerate(paragraphs))
    skeleton = ""
    if outline:
        skeleton = ("\n本文结构骨架（逐段角色，脚本已判定，请严格对应）：\n"
                    + "\n".join(f"第 {i + 1} 段：{role}" for i, role in enumerate(outline)))
    if source_label or pattern:
        skeleton += ("\n文章实际来源：" + (source_label or "官媒评论")
                     + f"；分论点结构关系：{pattern or '无'}")
        skeleton += "\n（开场定调必须按这个实际来源说，不要一律写成《人民日报》。）"
    result: list[dict] = []
    indexes = list(range(1, len(paragraphs) + 1))

    for batch in chunks(indexes, BATCH_SIZE):
        user = (
            f"文章标题：《{title}》\n\n"
            f"全文原文（仅供理解上下文，绝对不要输出原文）：\n{full_text}\n"
            f"{skeleton}\n\n"
            f"本次只为这些段号写解析：{batch}\n"
            f"返回 JSON：{{\"segments\":[...]}}，segments 数量必须等于 {len(batch)}，"
            f"index 依次为 {batch}。highlights 只能是对应原文段里的原样子串。\n"
            "每段的 structureRole 必须照抄上面结构骨架里的角色；function 要与角色对应"
            "（总论点段点明中心论点，分论点段必须写明是第几个分论点、论证什么，结尾段点明回扣与收束）。\n"
            "解析正文写在 analysis_markdown 字段，用 **…** 标出金句与写法名称，不要复述原文。"
        )
        if feedback:
            user += f"\n上一轮质量门禁未通过，请针对性修正：\n{feedback}\n"
        data = chat_json(system, user, temperature=0.55, max_tokens=4096)
        items = data.get("segments") if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise ValueError(f"段落批次返回格式错误：{str(data)[:200]}")
        result.extend(items)
    return result


def generate_overview(system: str, title: str, paragraphs: list[str],
                      source: dict, segments: list[dict], feedback: str = "",
                      outline: list[str] | None = None) -> dict:
    brief = "\n".join(
        f"第 {s['index']} 段｜功能：{(s.get('analysis') or {}).get('function','')}"
        f"｜写法：{'、'.join(((s.get('analysis') or {}).get('devices') or [])[:2])}"
        for s in segments
    )
    skeleton = ""
    if outline:
        skeleton = "\n结构骨架（逐段）：" + " / ".join(
            f"{i + 1}:{role}" for i, role in enumerate(outline))
    full_text = "\n".join(f"【第 {i + 1} 段】{p}" for i, p in enumerate(paragraphs))
    user = (
        f"文章标题：《{title}》\n"
        f"文章实际来源：{source_phrase(source)}（{source.get('paperDate','')}），"
        f"原题《{source.get('originalTitle','')}》，全文约 {source.get('charCount',0)} 字。"
        f"分论点结构关系：{(source.get('structure') or {}).get('pattern') or '无'}。\n"
        f"写 summary / FAQ 时必须使用这个实际来源标签，不要一律写成《人民日报》。\n\n"
        f"全文原文（不要输出）：\n{full_text}\n\n"
        f"各段解析要点：\n{brief}\n{skeleton}\n\n"
        "请返回全篇 JSON：keywords / summary / faq / frameworkTable / accumulation / exercise。"
        "frameworkTable 每行必须带 role 字段，取值照抄结构骨架（总论点 / 分论点一… / 结尾 / 论据 / 过渡分析）。"
        "summary 必须自包含（含标题、实际来源标签、日期、考点、以及本文的总论点与几个分论点、结构关系）。"
    )
    if feedback:
        user += f"\n上一轮质量门禁未通过，请针对性修正：\n{feedback}\n"
    data = chat_json(system, user, temperature=0.4, max_tokens=4096)
    return data if isinstance(data, dict) else {}


def assemble(date: str, slug: str, edition: int, picked: dict, paper_date: str,
             raw_segments: list[dict], overview: dict, selection_note: str = "") -> dict:
    source = build_source(picked, paper_date, selection_note)
    paragraphs = source["paragraphs"]
    outline = (source.get("structure") or {}).get("outline") or []
    title = source["originalTitle"] or picked.get("title", "")
    segments: list[dict] = []

    for item in raw_segments:
        idx = int(item.get("index") or 0)
        if not 1 <= idx <= len(paragraphs):
            continue
        orig_text = paragraphs[idx - 1]                       # 权威逐字原文
        highlights = [h for h in (item.get("highlights") or []) if isinstance(h, str)]
        orig_html, accepted = highlight_html(orig_text, highlights)
        ana_lines = str(item.get("analysis_markdown") or "").splitlines()
        ana_html = paragraphs_html(ana_lines)
        ana_text = plain_text(ana_lines)
        segments.append({
            "index": idx,
            "original": {"text": orig_text, "html": orig_html, "highlights": accepted},
            "analysis": {
                "text": ana_text,
                "html": ana_html,
                "function": str(item.get("function") or "").strip(),
                "structureRole": str(item.get("structureRole") or
                                     (outline[idx - 1] if idx - 1 < len(outline) else "")),
                "devices": [str(d) for d in (item.get("devices") or []) if str(d).strip()],
                "quotes": [str(q) for q in (item.get("quotes") or []) if str(q).strip()],
                "examples": [str(e) for e in (item.get("examples") or []) if str(e).strip()],
                "concepts": [
                    {"term": str(c.get("term") or ""), "boundary": str(c.get("boundary") or "")}
                    for c in (item.get("concepts") or []) if isinstance(c, dict)
                ],
            },
        })
    segments.sort(key=lambda s: s["index"])

    keywords = [str(k).strip() for k in (overview.get("keywords") or []) if str(k).strip()][:5]
    if len(keywords) < 2:
        keywords = (picked.get("topic_hits") or ["申论写作", "素材积累"])[:5]
    summary = str(overview.get("summary") or "").strip()
    if len(summary) < 60:
        summary = fallback_summary(title, source, keywords, len(segments))
    faq = overview.get("faq") or []
    if not isinstance(faq, list) or len(faq) < 2:
        faq = fallback_faq(title, source, summary, len(segments))

    acc = overview.get("accumulation") or {}
    exercise = overview.get("exercise") or {}
    exercise_lines = str(exercise.get("markdown") or exercise.get("question") or "").splitlines()
    extras = {
        "frameworkTable": [
            {"index": int(r.get("index") or 0),
             "function": str(r.get("function") or ""),
             "device": str(r.get("device") or ""),
             "role": str(r.get("role") or
                         (outline[int(r.get("index") or 0) - 1]
                          if 0 < int(r.get("index") or 0) <= len(outline) else ""))}
            for r in (overview.get("frameworkTable") or []) if isinstance(r, dict)
        ],
        "accumulation": {
            key: [str(x) for x in (acc.get(key) or []) if str(x).strip()]
            for key in ("golden", "standard", "templates", "conceptCards", "metaphorCards")
        },
        "exercise": {
            "question": str(exercise.get("question") or ""),
            "angles": [str(a) for a in (exercise.get("angles") or []) if str(a).strip()],
            "html": paragraphs_html(exercise_lines),
        },
    }

    doc = {
        "schemaVersion": 1,
        "date": date,
        "slug": slug,
        "edition": edition,
        "title": title,
        "keywords": keywords,
        "source": source,
        "summary": summary,
        "segments": segments,
        "extras": extras,
        "note": build_note(source),
        "faq": faq,
        "relatedSlugs": [],
        "status": "published",
        "contentHash": "",
        "generatedAt": datetime.now(CN_TZ).isoformat(timespec="seconds"),
        "model": (os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip(),
        "promptVersion": PROMPT_VERSION,
        "qualityReport": {},
    }
    apply_content_mode(doc)
    doc["contentHash"] = compute_hash(doc)
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description="全自动生成每日精读讲义")
    ap.add_argument("--date", help="YYYY-MM-DD，默认今天（北京时间）")
    ap.add_argument("--pick", help="改选文章：标题包含该关键词的候选优先")
    ap.add_argument("--redo", action="store_true", help="覆盖当天已存在的内容")
    ap.add_argument("--edition", type=int, default=1, help="同日第几篇，默认 1")
    ap.add_argument("--out", required=True, help="daily JSON 输出目录")
    ap.add_argument("--raw-out", help="抓稿候选原文输出目录（建议 gitignore）")
    ap.add_argument("--essay-only", action="store_true",
                    help="只保留严格结构达标（总论点 + ≥2 分论点 + 结尾）的候选")
    ap.add_argument("--require-essay", action="store_true",
                    help="抓稿窗口内均无结构达标文章时跳过上新（首页回退上一篇）")
    ap.add_argument("--essay-lookback", type=int, default=DEFAULT_ESSAY_LOOKBACK,
                    help=f"多源抓稿窗口向前回溯几天，默认 {DEFAULT_ESSAY_LOOKBACK}")
    ap.add_argument("--sources", help="逗号分隔的源 id（rmrb,people_opinion,rmlt,gmw,ce,12371），默认全部")
    ap.add_argument("--dry-run", action="store_true", help="只抓稿选文，不调用 LLM")
    args = ap.parse_args()

    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = (datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=CN_TZ)
              if args.date else datetime.now(CN_TZ))
    date = wanted.strftime("%Y-%m-%d")
    slug = date if args.edition == 1 else f"{date}-{args.edition}"
    target = out_dir / f"{slug}.json"

    # 幂等：已发布且非 --redo 时直接跳过，避免重复生成 / 重复构建
    if target.exists() and not args.redo:
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
            if existing.get("status") == "published":
                print(json.dumps({"skipped": True, "slug": slug,
                                  "reason": "已存在已发布讲义（使用 --redo 覆盖）"}, ensure_ascii=False))
                return 0
        except (json.JSONDecodeError, OSError):
            pass

    # 1) 多源聚合抓稿：一次抓 [date-lookback, date] 窗口内所有官媒，
    #    按「当天优先 → 严格结构达标 → 未用过」挑一篇；结构不达标一律不发。
    used_urls = load_used_urls(out_dir, exclude_slug=slug)
    sources = [x.strip() for x in args.sources.split(",") if x.strip()] if args.sources else None
    arts = fetch_sources.collect(wanted, essay_only=args.essay_only,
                                 lookback=args.essay_lookback, sources=sources)
    if not arts:
        print(json.dumps({"error": "多官媒均未抓到评论类文章", "date": date,
                          "sources": sources or "all"}, ensure_ascii=False))
        return 2
    if args.pick:
        match = next((a for a in arts if args.pick in a["title"]), None)
        if match:
            arts.remove(match)
            arts.insert(0, match)
            match["picked_by"] = "manual"
        else:
            print(f"[warn] 未找到标题含「{args.pick}」的候选，沿用自动选文", file=sys.stderr)

    selection_note = ""
    if args.pick:
        picked = arts[0]  # 人工改选优先
    else:
        picked = first_qualified(arts, used_urls)
        if picked:
            picked["picked_by"] = "structure"
        elif args.require_essay:
            print(json.dumps({
                "skipped": True,
                "reason": f"当天及前 {args.essay_lookback} 天各官媒均无严格分论点达标的文章（--require-essay）",
                "date": date, "lookback": args.essay_lookback,
                "candidates": [
                    {"title": a.get("title"), "source": a.get("sourceLabel"),
                     "status": a.get("structure", {}).get("status"),
                     "score": a.get("structure", {}).get("score")}
                    for a in arts[:5]
                ],
            }, ensure_ascii=False, indent=2))
            return 0
        else:
            # 窗口内也没有：取结构分最高的议论文，并在讲义里提示结构缺陷
            pool = [a for a in arts if not a.get("structure", {}).get("newsReport")] or arts
            picked = max(pool, key=lambda a: (
                (a.get("structure", {}).get("essayFlavor") or {}).get("value", 0),
                a.get("structure", {}).get("score", 0),
            ))
            picked["picked_by"] = "structure-fallback"
            picked.setdefault("structure", {})["status"] = "partial"

    paper_date = picked.get("date") or date
    if paper_date != date and picked.get("picked_by") == "structure":
        picked["picked_by"] = "structure-backtrack"
        selection_note = (
            f"因 {date} 当天各官媒评论栏目未选到符合申论大作文结构的文章，"
            f"回溯选用 {paper_date} {picked.get('sourceLabel') or picked.get('sourceName') or '官媒'}"
            f"的《{picked.get('title', '')}》；"
        )

    if args.raw_out:
        raw_dir = Path(args.raw_out).expanduser()
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / f"原文-{paper_date}.json").write_text(
            json.dumps({"requested_date": date, "paper_date": paper_date,
                        "selection_note": selection_note,
                        "picked": picked, "candidates": [
                            {k: a.get(k) for k in ("title", "column", "page", "author",
                                                   "char_count", "score", "url", "sourceLabel")}
                            for a in arts]}, ensure_ascii=False, indent=2),
            encoding="utf-8")

    if args.dry_run:
        print(json.dumps({"dryRun": True, "requested_date": date, "paper_date": paper_date,
                          "picked": {k: picked.get(k) for k in
                                     ("title", "page", "column", "author", "char_count", "url",
                                      "source", "sourceName", "sourceLabel")},
                          "paragraphs": len(picked.get("paragraphs") or []),
                          "candidates": len(arts),
                          "structure": article_structure.compact(picked.get("structure")),
                          "pattern": (picked.get("structure") or {}).get("pattern"),
                          "outline": (picked.get("structure") or {}).get("outline"),
                          "pickedBy": picked.get("picked_by") or "score",
                          "lookbackDays": args.essay_lookback,
                          "selectionNote": selection_note}, ensure_ascii=False, indent=2))
        return 0

    # 2) 逐段生成解析（原文不交给 LLM）+ 全篇概览
    system = load_system()
    paragraphs = list(picked.get("paragraphs") or [])
    if len(paragraphs) < 3:
        print(json.dumps({"error": "原文段落过少", "paragraphs": len(paragraphs)}, ensure_ascii=False))
        return 2

    source_preview = build_source(picked, paper_date, selection_note)
    outline = (source_preview.get("structure") or {}).get("outline") or []
    structure_warning = ""
    if picked.get("structure", {}).get("status") == "partial":
        missing = "、".join(picked.get("structure", {}).get("missing") or [])
        structure_warning = (
            f"\n注意：本文结构不完全符合申论大作文规范（{missing}）。"
            "请在第 1 段解析里如实提示同学「这篇是评论文章，结构上与考场大作文有差别」，"
            "并给出若改写成大作文应如何补齐结构。"
        )

    report = {"passed": False, "checks": []}
    doc: dict | None = None
    for attempt in range(MAX_QUALITY_RETRIES + 1):
        failed = [] if attempt == 0 else [
            f"{c['id']}: {c['detail']}" for c in report.get("checks", []) if not c["ok"]
        ]
        feedback = "；".join(failed) + structure_warning
        raw_segments = generate_segments(
            system, picked["title"], paragraphs, outline, feedback,
            source_preview.get("sourceLabel") or "",
            (source_preview.get("structure") or {}).get("pattern") or "",
        )
        preview = [
            {"index": s.get("index"),
             "analysis": {"function": s.get("function"),
                          "structureRole": s.get("structureRole"),
                          "devices": s.get("devices") or []}}
            for s in raw_segments
        ]
        overview = generate_overview(system, picked["title"], paragraphs,
                                     source_preview, preview, feedback, outline)
        doc = assemble(date, slug, args.edition, picked, paper_date,
                       raw_segments, overview, selection_note)
        report = validate_doc(doc)
        report["retries"] = attempt
        if report["passed"]:
            break
        print(f"[warn] 质量门禁第 {attempt + 1} 轮未通过：{feedback}", file=sys.stderr)

    if doc is None:
        print(json.dumps({"error": "生成失败"}, ensure_ascii=False))
        return 1

    doc["qualityReport"] = report
    if report["passed"]:
        doc["status"] = "published"
    else:
        # draft 不进索引、不 commit、不预渲染；首页自动回退上一篇 published
        doc["status"] = "draft"
    doc["contentHash"] = compute_hash(doc)
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = {
        "slug": slug,
        "title": doc["title"],
        "date": date,
        "paperDate": paper_date,
        "source": (doc.get("source") or {}).get("sourceName"),
        "sourceLabel": (doc.get("source") or {}).get("sourceLabel"),
        "selectionNote": selection_note,
        "status": doc["status"],
        "segments": len(doc["segments"]),
        "structure": article_structure.compact((doc.get("source") or {}).get("structure")),
        "pattern": ((doc.get("source") or {}).get("structure") or {}).get("pattern"),
        "pickedBy": picked.get("picked_by") or "score",
        "qualityReport": {"passed": report["passed"], "retries": report.get("retries", 0),
                          "verbatimMatch": report.get("verbatimMatch"),
                          "failed": [c["id"] for c in report["checks"] if not c["ok"]]},
        "output": str(target),
    }
    if doc["status"] == "published":
        result["index"] = rebuild(out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 3


if __name__ == "__main__":
    sys.exit(main())
