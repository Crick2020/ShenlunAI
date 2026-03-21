#!/usr/bin/env python3
"""从 backend/data 下所有试卷 JSON 的 content 字段中删除 Markdown 配图占位（/images/）。"""
import json
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def _strip_markdown_images(t: str) -> str:
    """与 clean_sydw_placeholders._strip_markdown_images 逻辑一致。"""
    prev = None
    while prev != t:
        prev = t
        t = re.sub(r"\n*!\[[^\]]*\]\(/images/[^)]+\)", "", t)
        t = re.sub(r"\n*!\[[^\]]*\]\(/images/\s*", "", t)
    t = t.replace("：##", "：\n\n##")
    return t


def _walk(obj):
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k == "content" and isinstance(v, str):
                obj[k] = _strip_markdown_images(v)
            else:
                _walk(v)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item)


def main() -> int:
    files = sorted(DATA.glob("*.json"))
    if not files:
        print("No json in data/", file=sys.stderr)
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
