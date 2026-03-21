#!/usr/bin/env python3
"""Remove OCR placeholder markers from sydw_*.json material/question content."""
import json
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# 图片 OCR 占位（含 markdown / HTML 变体）
_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"<br>\s*\*\*-----\s*End of picture text\s*-----\*\*\s*<br>", re.I), ""),
    (re.compile(r"\*\*-----\s*Start of picture text\s*-----\*\*\s*<br>", re.I), ""),
    (re.compile(r"<br>\s*\*\*-----\s*End of picture text\s*-----\*\*", re.I), ""),
    (re.compile(r"\*\*-----\s*End of picture text\s*-----\*\*", re.I), ""),
    (re.compile(r"\*\*-----\s*Start of picture text\s*-----\*\*", re.I), ""),
    (re.compile(r"----- End of picture text -----", re.I), ""),
    (re.compile(r"----- Start of picture text -----", re.I), ""),
]


def _clean_string(s: str) -> str:
    t = s
    for pat, repl in _SUBS:
        t = pat.sub(repl, t)
    # 单独成行、被截断的试卷标题（常见于图注残留）
    t = re.sub(
        r"(?m)^\s*20\d{2}年.+全国事业单位联考[^。\n]*（[^）\n]*_\s*\.\.\.\s*$",
        "",
        t,
    )
    t = re.sub(r"(?m)^\s*—20\d{2}年）》。\s*$", "", t)
    # 合并多余空行
    t = re.sub(r"\n{4,}", "\n\n\n", t)
    t = re.sub(r"(<br>\s*){3,}", "<br><br>", t)
    return t.strip()


def _walk(obj):
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k == "content" and isinstance(v, str):
                obj[k] = _clean_string(v)
            else:
                _walk(v)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item)


def main() -> int:
    files = sorted(DATA.glob("sydw_*.json"))
    if not files:
        print("No sydw_*.json found", file=sys.stderr)
        return 1
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        _walk(data)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.write("\n")
        print("OK", fp.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
