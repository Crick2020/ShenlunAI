#!/usr/bin/env python3
"""修复广西和贵州JSON文件中每题的分值(maxScore)，从题目标题中解析"""

import json
import re
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def parse_score_from_question(q: dict) -> int | None:
    """从题目标题或要求中解析分值，返回分值或None"""
    title = q.get("title", "")
    req = q.get("requirements", "")
    text = title + req
    # 匹配 （15分）、(20分)、（40分） 等，支持全角半角括号
    m = re.search(r'[（(](\d{1,2})分[）)]', text)
    if m:
        return int(m.group(1))
    # 匹配标题被截断的情况，如 "……（25" 或 "……（25分"
    m = re.search(r'[（(](\d{1,2})(?:分)?\s*$', title)
    if m:
        return int(m.group(1))
    # 匹配 requirements 中的分值
    m = re.search(r'[（(](\d{1,2})分[）)]', req)
    if m:
        return int(m.group(1))
    return None


def fix_file(filepath: Path) -> bool:
    """修复单个JSON文件的分值，返回是否有修改"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    questions = data.get("questions", [])
    modified = False
    
    for q in questions:
        parsed = parse_score_from_question(q)
        if parsed is not None and q.get("maxScore") != parsed:
            q["maxScore"] = parsed
            modified = True
    
    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return modified


def main():
    count = 0
    for name in sorted(os.listdir(DATA_DIR)):
        if not (name.startswith("gwy_guangxi_") or name.startswith("gwy_guizhou_") or name.startswith("gwy_guangdong_")):
            continue
        if not name.endswith(".json"):
            continue
        path = DATA_DIR / name
        if fix_file(path):
            print(f"已修复: {name}")
            count += 1
    print(f"\n共修复 {count} 个文件")


if __name__ == "__main__":
    main()
