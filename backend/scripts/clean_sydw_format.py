#!/usr/bin/env python3
"""
事业单位联考（sydw_*.json）材料正文格式清洗：
- 去掉无意义符号：行首「-」「##」、独立页码行、「……段N：」等 OCR 残留
- 合并汉字/数字/字母间误插入的空格
- 常见错别字替换

在 clean_sydw_placeholders 的图片占位清理之后串联执行。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import clean_sydw_placeholders as csp  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"

# 需要走「含 HTML 标签」分支的字段（分段清洗，避免破坏标签）
HTML_KEYS = frozenset({"bodyHtml", "leftHtml", "excerptHtml"})

# 材料/题目正文、要求、题干标题、含 HTML 的工作笔记单元格
TEXT_KEYS = frozenset({"content", "requirements", "title", *HTML_KEYS})

# 整段替换错别字（先长后短）
TYPO_REPLACEMENTS: list[tuple[str, str]] = [
    ("社会规织", "社会组织"),
    ("询间", "询问"),
    ("询通", "沟通"),
    ("政策内客", "政策内容"),
    ("内客", "内容"),
    ("未成年人法制教育", "未成年人法治教育"),
    ("法制教育区", "法治教育区"),
    ("法制教育", "法治教育"),
    ("效果很好、除此以外", "效果很好。除此以外"),
    ("老俩口", "老两口"),
    ("测管协同", "测管协同"),  # 保留
]


def _merge_intraline_spaces(t: str) -> str:
    """合并 OCR 在汉字/数字/字母之间误插入的空格。"""
    for _ in range(30):
        old = t
        # 汉字-汉字
        t = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", t)
        # 数字-汉字 / 汉字-数字
        t = re.sub(r"([0-9]+)\s+([\u4e00-\u9fff%‰])", r"\1\2", t)
        t = re.sub(r"([\u4e00-\u9fff])\s+([0-9]+)", r"\1\2", t)
        # 字母-汉字（如 A市、C市）
        t = re.sub(r"([A-Za-z])\s+([\u4e00-\u9fff])", r"\1\2", t)
        t = re.sub(r"([\u4e00-\u9fff])\s+([A-Za-z])", r"\1\2", t)
        # 标点与汉字
        t = re.sub(r"([\u4e00-\u9fff])\s+([，。、；：！？、「」『』《》])", r"\1\2", t)
        t = re.sub(r"([，。、；：！？])\s+([\u4e00-\u9fff])", r"\1\2", t)
        # 弯引号/直引号后误接空格（OCR 常见：” 为、” 另）
        t = re.sub(r"([\u201d\u2019])\s+([\u4e00-\u9fff])", r"\1\2", t)
        t = re.sub(r'(")\s+([\u4e00-\u9fff])', r"\1\2", t)
        if t == old:
            break
    # 行内多余空白（保留换行）
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r" \n", "\n", t)
    t = re.sub(r"\n ", "\n", t)
    return t


def _strip_noise_markers(t: str) -> str:
    """去掉列表符、markdown 标题符、页码行、段标记等。"""
    # 先去掉行首 ##（含「## - 【」），再删行首「-」，否则「## - 」会先删不掉「-」
    for _ in range(6):
        old = t
        t = re.sub(r"(?m)^\s*##\s*[-－]?\s*", "", t)
        t = re.sub(r"(?m)^\s*##\s*", "", t)
        t = re.sub(r"(?m)^\s*[-－]\s*", "", t)
        if t == old:
            break
    # 「…… 段9：」等
    t = re.sub(r"……\s*段\d+\s*[：:]", "……", t)
    # 仅含 1～2 位数字的独立行（PDF 页码）
    t = re.sub(r"(?<=\n)\s*\d{1,2}\s*(?=\n)", "", t)
    t = re.sub(r"^\s*\d{1,2}\s*$", "", t, flags=re.M)
    # 合并因删行产生的多余空行
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t


def _apply_typos(t: str) -> str:
    for old, new in TYPO_REPLACEMENTS:
        if old != new:
            t = t.replace(old, new)
    return t


_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
_TABLE_RE = re.compile(r"<table\b[^>]*>.*?</table>", re.I | re.DOTALL)


def _extract_table_tags(t: str) -> tuple[str, list[str]]:
    """合并空格前暂存整段 <table>…</table>。"""
    tags: list[str] = []

    def repl(_m: re.Match[str]) -> str:
        tags.append(_m.group(0))
        return f"\x00TBL{len(tags)-1}\x00"

    return _TABLE_RE.sub(repl, t), tags


def _restore_table_tags(t: str, tags: list[str]) -> str:
    for i, tag in enumerate(tags):
        t = t.replace(f"\x00TBL{i}\x00", tag)
    return t


def _extract_img_tags(t: str) -> tuple[str, list[str]]:
    """合并空格前暂存 <img>，避免误伤属性或整段被删。"""
    tags: list[str] = []

    def repl(_m: re.Match[str]) -> str:
        tags.append(_m.group(0))
        return f"\x00IMG{len(tags)-1}\x00"

    return _IMG_TAG_RE.sub(repl, t), tags


def _restore_img_tags(t: str, tags: list[str]) -> str:
    for i, tag in enumerate(tags):
        t = t.replace(f"\x00IMG{i}\x00", tag)
    return t


def format_clean_plain(t: str) -> str:
    """纯文本材料 content / requirements。"""
    t, table_tags = _extract_table_tags(t)
    t, img_tags = _extract_img_tags(t)
    t = _strip_noise_markers(t)
    t = _apply_typos(t)
    t = _merge_intraline_spaces(t)
    t = _restore_img_tags(t, img_tags)
    t = _restore_table_tags(t, table_tags)
    return t


_HTML_SPLIT = re.compile(r"(<[^>]+>)")


def format_clean_html(t: str) -> str:
    """含 <u>、<img> 等标签的 HTML 片段。"""
    parts: list[str] = []
    for seg in _HTML_SPLIT.split(t):
        if not seg:
            continue
        if seg.startswith("<"):
            parts.append(seg)
        else:
            parts.append(format_clean_plain(seg))
    return "".join(parts)


def _merge_segments_html(t: str) -> str:
    """仅对 HTML 标签外的正文再跑一轮字间空格合并（供 OCR 后处理）。"""
    parts: list[str] = []
    for seg in _HTML_SPLIT.split(t):
        if not seg:
            continue
        if seg.startswith("<"):
            parts.append(seg)
        else:
            parts.append(_merge_intraline_spaces(seg))
    return "".join(parts)


def full_clean_string(value: str, key: str) -> str:
    """串联：格式清洗 → 删 md 图占位 → 既有 OCR 字面替换。"""
    if key in HTML_KEYS:
        t = format_clean_html(value)
    else:
        t = format_clean_plain(value)
    t = csp._strip_markdown_images(t)
    t = csp._clean_ocr_noise(t)
    # clean_sydw_placeholders 的字面替换可能再次产生「汉 字」间空格，须再合并一轮
    if key in HTML_KEYS:
        t = _merge_segments_html(t)
    else:
        t, _tbl2 = _extract_table_tags(t)
        t, _imgs2 = _extract_img_tags(t)
        t = _merge_intraline_spaces(t)
        t = _restore_img_tags(t, _imgs2)
        t = _restore_table_tags(t, _tbl2)
    t = re.sub(r"\n{4,}", "\n\n\n", t)
    t = re.sub(r"(<br>\s*){3,}", "<br><br>", t)
    return t.strip()


def walk(obj: object) -> None:
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str) and k in TEXT_KEYS:
                obj[k] = full_clean_string(v, k)
            else:
                walk(v)
    elif isinstance(obj, list):
        for item in obj:
            walk(item)


def main() -> int:
    files = sorted(DATA.glob("sydw_*.json"))
    if not files:
        print("No sydw_*.json found", file=sys.stderr)
        return 1
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        walk(data)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.write("\n")
        print("OK", fp.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
