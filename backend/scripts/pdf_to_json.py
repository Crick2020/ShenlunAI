#!/usr/bin/env python3
"""
申论 PDF 试卷转 JSON（支持多省份）
用法: python pdf_to_json.py --pdf-dir <PDF目录> --region <省份> [--output-dir <输出目录>]
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import warnings
warnings.filterwarnings("ignore", message=".*FontBBox.*")

try:
    import pdfplumber
except ImportError:
    print("请先安装: pip install pdfplumber")
    sys.exit(1)

# 省份名 -> paper_id 中的 region_id
REGION_MAP = {
    "海南": "hainan", "广西": "guangxi", "贵州": "guizhou", "广东": "guangdong",
    "安徽": "anhui", "江苏": "jiangsu", "福建": "fujian", "甘肃": "gansu",
    "北京": "beijing", "吉林": "jilin", "河北": "hebei", "国家": "guojia",
}

# 分卷后缀匹配：文件名关键词 -> paper_id 后缀
SUFFIX_RULES = [
    (r"A卷|a卷", "A"), (r"B卷|b卷", "B"), (r"C卷|c卷", "C"),
    (r"县级卷|县级", "XianJi"), (r"乡镇卷|乡镇", "XiangZhen"),
    (r"公安卷|公安", "GongAn"), (r"实事|市事", "ShiShi"),
    (r"县级|县乡|县巷", "XianZhen"),
    (r"乡镇选调|乡镇卷", "XiangZhen"), (r"普通选调", "A"),
    (r"行政执法|行政执业|行执", "XingZhengZhiFa"), (r"省直", "ShengZhi"),
    (r"县乡|县巷", "XianXiang"), (r"省市", "ShiShi"), (r"省直卷", "ShengZhi"),
    (r"审计|省计", "ShenJi"), (r"市县|市县", "ShiXian"), (r"通用|普通", "General"),
]


def extract_full_text(pdf_path: Path) -> str:
    full = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            t = p.extract_text()
            if t:
                full.append(t)
    return unicodedata.normalize("NFKC", "\n".join(full))


def _clean_page_footer(text: str) -> str:
    text = re.sub(r"·\s*本试卷由[^\n]+?第\s*\d+\s*页[，,\s]*共\s*\d+\s*页[^\n]*", "", text)
    text = re.sub(r"\d{4}年公务员[^》]*》[^）\)]*[）\)][^\n]*", "", text)
    return text


def _find_zuoda_yaoqiu_pos(text: str) -> int:
    for m in re.finditer(r"作答要求\s*\n\s*第[一二三四五六七八九十]+题", text):
        return m.start()
    last = -1
    for m in re.finditer(r"作答要求", text):
        last = m.start()
    return last


def parse_filename_to_id(filename: str, region: str, region_id: str) -> tuple:
    name = filename.replace(".pdf", "")
    year_match = re.search(r"(\d{4})年", name)
    year = int(year_match.group(1)) if year_match else 2020
    suffix = ""
    for pattern, suf in SUFFIX_RULES:
        if re.search(pattern, name, re.I):
            suffix = suf
            break
    paper_id = f"gwy_{region_id}_{year}"
    if suffix:
        paper_id += f"_{suffix}"
    return paper_id, name, year, suffix


def parse_materials(text: str) -> list:
    start_markers = [
        r"给定材料\s*\n\s*材料1", r"给定材料\s*\n\s*给定资料1",
        r"\n\s*材料1\s*\n", r"\n\s*给定资料1\s*\n",
    ]
    materials_start = 0
    for pat in start_markers:
        m = re.search(pat, text)
        if m:
            materials_start = m.start()
            break
    req_pos = _find_zuoda_yaoqiu_pos(text)
    materials_text = text[materials_start:req_pos] if req_pos > materials_start else text[materials_start:]
    parts = re.split(r"\n\s*(材料|给定资料)(\d+)\s*\n", materials_text, flags=re.IGNORECASE)
    materials = []
    for i in range(1, len(parts) - 1, 3):
        if i + 2 <= len(parts):
            num = parts[i + 1]
            content = parts[i + 2].strip()
            content = _clean_page_footer(content)
            content = re.sub(r"[ \t]+", " ", content)
            content = re.sub(r"\n{3,}", "\n\n", content).strip()
            content = re.sub(r" (?=[，。！？、：；）】])", "", content)
            if len(content) > 50:
                materials.append({"id": f"m{num}", "title": f"给定资料{num}", "content": content})
    return materials


def parse_questions(text: str, material_ids: list) -> list:
    req_pos = _find_zuoda_yaoqiu_pos(text)
    if req_pos < 0:
        req_pos = max(0, text.find("第一题"))
    q_text = text[req_pos:]
    if q_text.find("答题纸") > 0:
        q_text = q_text[:q_text.find("答题纸")]
    q_blocks = re.split(r"\n\s*第([一二三四五六七八九十]+)题\s*\n", q_text)
    questions = []
    for i in range(1, len(q_blocks), 2):
        if i + 1 > len(q_blocks):
            break
        block = q_blocks[i + 1].strip()
        req_match = re.search(r"要求[：:]\s*(.+?)(?=第[一二三四五六七八九十]+题|$)", block, re.DOTALL)
        if req_match:
            title_part, req_part = block[:req_match.start()].strip(), req_match.group(1).strip()
        else:
            req_m = re.search(r"要求\s*[：:]?\s*\n?\s*[（(]\d+[)）][^\n]+", block)
            title_part = block[:req_m.start()].strip() if req_m else block
            req_part = block[req_m.start():].strip() if req_m else ""
        title_part = re.sub(r"\s+", " ", title_part).strip()
        req_part = _clean_page_footer(re.sub(r"\s+", " ", req_part).strip())
        refs = re.findall(r'[「"]?给定资料(\d+)[」"]?|[「"]?材料(\d+)[」"]?', title_part)
        mat_refs = [f"m{a or b}" for a, b in refs if (a or b) and f"m{a or b}" in material_ids]
        is_last = (i + 2 >= len(q_blocks))
        if is_last or ("议论文" in block) or ("写一篇" in block and "1000" in block):
            q_type, mat_refs = "ESSAY", material_ids
        else:
            q_type = "SMALL"
            if not mat_refs and material_ids:
                mat_refs = [material_ids[0]]
        score_m = re.search(r"（(\d+)分）|\((\d+)分\)|(\d+)分", block)
        max_score = int(score_m.group(1) or score_m.group(2) or score_m.group(3) or 20) if score_m else 20
        wm = re.search(r"不超过(\d+)字|不少于(\d+)字|(\d+)[～~\-](\d+)字", block)
        word_limit = 300
        if wm:
            gs = wm.groups()
            word_limit = (int(gs[2]) + int(gs[3])) // 2 if gs[2] and gs[3] else int(gs[0] or gs[1] or 300)
        questions.append({
            "id": f"q{len(questions)+1}", "title": title_part, "requirements": req_part,
            "maxScore": max_score, "wordLimit": word_limit, "type": q_type, "materialIds": mat_refs,
        })
    return questions


def pdf_to_json(pdf_path: Path, region: str, region_id: str) -> dict | None:
    text = extract_full_text(pdf_path)
    if not text or len(text) < 500:
        return None
    paper_id, name, year, _ = parse_filename_to_id(pdf_path.name, region, region_id)
    materials = parse_materials(text)
    material_ids = [m["id"] for m in materials]
    questions = parse_questions(text, material_ids)
    if not materials:
        print(f"  警告: {pdf_path.name} 未解析出材料")
    if not questions:
        print(f"  警告: {pdf_path.name} 未解析出题目")
    return {
        "id": paper_id, "name": name, "examType": "公务员", "region": region,
        "year": year, "materials": materials, "questions": questions,
    }


def main():
    parser = argparse.ArgumentParser(description="申论 PDF 转 JSON（多省份）")
    parser.add_argument("--pdf-dir", required=True, help="PDF 所在目录")
    parser.add_argument("--output-dir", default=None, help="输出目录，默认 backend/data")
    parser.add_argument("--region", required=True, help="省份名，如：海南、广西、贵州、广东")
    args = parser.parse_args()

    region = args.region.strip()
    region_id = REGION_MAP.get(region)
    if not region_id:
        region_id = region.lower().replace("省", "").replace("市", "")
    pdf_dir = Path(args.pdf_dir)
    output_dir = Path(args.output_dir) if args.output_dir else Path(__file__).resolve().parent.parent / "data"

    if not pdf_dir.is_dir():
        print(f"目录不存在: {pdf_dir}")
        sys.exit(1)
    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"未找到 PDF: {pdf_dir}")
        return

    os.makedirs(output_dir, exist_ok=True)
    print(f"[{region}] 找到 {len(pdf_files)} 个 PDF，开始转换...")
    success = 0
    for pdf_path in pdf_files:
        try:
            data = pdf_to_json(pdf_path, region, region_id)
            if data and (data.get("materials") or data.get("questions")):
                out_path = output_dir / f"{data['id']}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=0)
                print(f"  ✓ {pdf_path.name} -> {data['id']}.json")
                success += 1
            else:
                print(f"  ✗ {pdf_path.name} 解析结果为空")
        except Exception as e:
            print(f"  ✗ {pdf_path.name} 失败: {e}")
    print(f"\n完成：{success}/{len(pdf_files)}，输出: {output_dir}")


if __name__ == "__main__":
    main()
