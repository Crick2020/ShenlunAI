#!/usr/bin/env python3
"""修复广西和贵州JSON文件中大作文(ESSAY)的字段：type、materialIds、wordLimit"""

import json
import re
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def parse_word_limit(requirements: str) -> int | None:
    """从requirements中解析字数要求，返回合适的wordLimit"""
    if not requirements:
        return None
    # 不少于1000字 -> 1000
    m = re.search(r'不少于(\d+)字', requirements)
    if m:
        return int(m.group(1))
    # 1000~1200字、1000—1200字、1000-1200字 -> 1100
    m = re.search(r'(\d+)[~—\-]\s*(\d+)字', requirements)
    if m:
        return (int(m.group(1)) + int(m.group(2))) // 2
    # 1000字左右、约1000字 -> 1000
    m = re.search(r'(\d+)字\s*左右|约\s*(\d+)字', requirements)
    if m:
        return int(m.group(1) or m.group(2))
    # 不超过XXX字 - 用于小题，不处理
    return None


def is_essay_question(q: dict, questions: list, idx: int) -> bool:
    """判断是否为大作文题目"""
    title = q.get("title", "")
    req = q.get("requirements", "")
    word_limit = q.get("wordLimit", 0)
    # 大作文特征：requirements中含 不少于XXX字、1000字左右、1000~1200字 等
    req_has_essay_count = bool(re.search(r'不少于\d+字|(\d+)[~—\-]\s*\d+字|\d+字\s*左右|约\s*\d+字|总字数\s*\d+', req))
    # 题目特征
    title_has_essay = (
        "写一篇" in title or "写⼀篇" in title or
        ("自拟题" in title and "写" in title) or
        ("联系实际" in title and "写" in title)
    )
    # 排除明确的小题型
    exclude_keywords = ["简报", "报告", "倡议书", "短评", "宣传稿", "报道", "提纲", "动员"]
    if any(kw in title for kw in exclude_keywords):
        # 倡议书、简报等若要求400-600字，不是大作文
        if re.search(r'不超过[34]\d{2}字|不超过[56]\d{2}字|[34]\d{2}-[45]\d{2}字', req):
            return False
    # 大作文：题目或要求符合，且通常是最后一题
    return (req_has_essay_count or (title_has_essay and word_limit >= 600)) and idx == len(questions) - 1


def fix_file(filepath: Path) -> bool:
    """修复单个JSON文件，返回是否有修改"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    materials = data.get("materials", [])
    questions = data.get("questions", [])
    material_ids = [m["id"] for m in materials]
    
    modified = False
    for idx, q in enumerate(questions):
        if not is_essay_question(q, questions, idx):
            continue
        # 大作文：设置 type=ESSAY, materialIds=全部材料, 修正 wordLimit
        if q.get("type") != "ESSAY":
            q["type"] = "ESSAY"
            modified = True
        if set(q.get("materialIds", [])) != set(material_ids):
            q["materialIds"] = material_ids
            modified = True
        new_limit = parse_word_limit(q.get("requirements", ""))
        if new_limit and q.get("wordLimit") != new_limit:
            q["wordLimit"] = new_limit
            modified = True
    
    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return modified


def main():
    count = 0
    for name in os.listdir(DATA_DIR):
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
