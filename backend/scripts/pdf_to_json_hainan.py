#!/usr/bin/env python3
"""
将海南申论 PDF 试卷转为与 gwy_anhui_2023_A 一致的 JSON 格式。
使用 pdfplumber 提取文本，解析材料、题目，大作文对应 ESSAY 类型且关联所有材料。
"""
import json
import os
import re
import sys
from pathlib import Path

# 抑制 pdfplumber 的 FontBBox 警告
import warnings
warnings.filterwarnings("ignore", message=".*FontBBox.*")

try:
    import pdfplumber
except ImportError:
    print("请先安装: pip install pdfplumber")
    sys.exit(1)

# 海南 PDF 目录
HAINAN_PDF_DIR = Path("/Users/luzhipeng/Documents/学习及生活/申论/海南")
# 输出目录（与 gwy_anhui_2023_A 相同）
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"


def extract_full_text(pdf_path: Path) -> str:
    """从 PDF 提取全部文本，并做 NFKC 归一化（PDF 常含康熙部首等变体）"""
    import unicodedata
    full = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            t = p.extract_text()
            if t:
                full.append(t)
    raw = "\n".join(full)
    return unicodedata.normalize("NFKC", raw)


def parse_filename_to_id(filename: str) -> tuple:
    """
    从文件名解析出 paper_id, name, year, suffix。
    例: 2023年公务员多省联考《申论》题（海南A卷）.pdf -> gwy_hainan_2023_A
    """
    name = filename.replace(".pdf", "")
    year_match = re.search(r"(\d{4})年", name)
    year = int(year_match.group(1)) if year_match else 2020

    suffix = ""
    if "海南A卷" in name or "海南a卷" in name:
        suffix = "A"
    elif "海南B卷" in name or "海南b卷" in name:
        suffix = "B"
    elif "海南C卷" in name or "海南c卷" in name:
        suffix = "C"
    elif "县级卷" in name or "县级" in name:
        suffix = "XianJi"
    elif "乡镇卷" in name or "乡镇" in name:
        suffix = "XiangZhen"
    elif "海南卷" in name and not suffix:
        suffix = ""  # 2017、2018 年无分卷

    paper_id = f"gwy_hainan_{year}"
    if suffix:
        paper_id += f"_{suffix}"

    return paper_id, name, year, suffix


def _clean_page_footer(text: str) -> str:
    """移除页脚、页码、试卷标题重复等无关内容"""
    # · 本试卷由粉笔用户xxx生成 第X页,共Y页 及变体（，, 空格等）
    text = re.sub(r"·\s*本试卷由[^\n]+?第\s*\d+\s*页[，,\s]*共\s*\d+\s*页[^\n]*", "", text)
    # 重复的试卷标题：2023年公务员多省联考《申论》题(海南X卷)
    text = re.sub(r"\d{4}年公务员[^》]*》[^）\)]*[）\)][^\n]*", "", text)
    return text


def _find_zuoda_yaoqiu_pos(text: str) -> int:
    """找到真正的「作答要求」位置（题目区的，非注意事项里的）。"""
    # 注意事项中有「作答要求」字样，真正的题目区在后方
    for m in re.finditer(r"作答要求\s*\n\s*第[一二三四五六七八九十]+题", text):
        return m.start()
    # 备选：最后一个 作答要求
    last = -1
    for m in re.finditer(r"作答要求", text):
        last = m.start()
    return last


def parse_materials(text: str) -> list:
    """
    解析材料。支持: 材料1/材料2, 给定资料1/给定资料2
    截断到「作答要求」之前。
    """
    start_markers = [
        r"给定材料\s*\n\s*材料1",
        r"给定材料\s*\n\s*给定资料1",
        r"\n\s*材料1\s*\n",
        r"\n\s*给定资料1\s*\n",
    ]
    materials_start = 0
    for pat in start_markers:
        m = re.search(pat, text)
        if m:
            materials_start = m.start()
            break

    req_pos = _find_zuoda_yaoqiu_pos(text)
    if req_pos > 0 and req_pos > materials_start:
        materials_text = text[materials_start:req_pos]
    else:
        materials_text = text[materials_start:]

    # 按 材料N 或 给定资料N 分割
    parts = re.split(r"\n\s*(材料|给定资料)(\d+)\s*\n", materials_text, flags=re.IGNORECASE)
    materials = []
    for i in range(1, len(parts) - 1, 3):
        if i + 2 <= len(parts):
            num = parts[i + 1]
            content = parts[i + 2].strip()
            content = _clean_page_footer(content)
            # 合并多余空白，保留段落换行
            content = re.sub(r"[ \t]+", " ", content)
            content = re.sub(r"\n{3,}", "\n\n", content).strip()
            content = re.sub(r" (?=[，。！？、：；）】])", "", content)
            if len(content) > 50:
                materials.append({
                    "id": f"m{num}",
                    "title": f"给定资料{num}",
                    "content": content,
                })
    return materials


def parse_questions(text: str, material_ids: list) -> list:
    """
    解析题目。从「作答要求」后开始，按 第一题/第二题/一、 等分割。
    最后一题通常为大作文(ESSAY)，关联所有材料。
    """
    req_pos = _find_zuoda_yaoqiu_pos(text)
    if req_pos < 0:
        req_pos = text.find("第一题")
    if req_pos < 0:
        req_pos = 0
    q_text = text[req_pos:]
    # 去掉答题纸部分
    answer_pos = q_text.find("答题纸")
    if answer_pos > 0:
        q_text = q_text[:answer_pos]

    # 按 第一题/第二题/第三题/第四题/第五题 或 一、二、三、 分割
    q_blocks = re.split(
        r"\n\s*第([一二三四五六七八九十]+)题\s*\n",
        q_text,
    )
    questions = []
    for i in range(1, len(q_blocks), 2):
        if i + 1 > len(q_blocks):
            break
        block = q_blocks[i + 1].strip()
        # 提取题目正文（到「要求」之前）和 要求 部分
        req_match = re.search(r"要求[：:]\s*(.+?)(?=第[一二三四五六七八九十]+题|$)", block, re.DOTALL)
        if req_match:
            title_part = block[: req_match.start()].strip()
            req_part = req_match.group(1).strip()
        else:
            # 尝试 (1)(2)(3) 形式的要求
            req_match = re.search(r"要求\s*[：:]?\s*\n?\s*[（(]\d+[)）][^\n]+", block)
            if req_match:
                title_part = block[: req_match.start()].strip()
                req_part = block[req_match.start():].strip()
            else:
                title_part = block
                req_part = ""

        title_part = re.sub(r"\s+", " ", title_part).strip()
        req_part = re.sub(r"\s+", " ", req_part).strip()
        req_part = _clean_page_footer(req_part)
        req_part = re.sub(r"\s+", " ", req_part).strip()

        # 从题目中提取引用的材料：给定资料1 -> m1
        refs = re.findall(r'[「"]?给定资料(\d+)[」"]?|[「"]?材料(\d+)[」"]?', title_part)
        mat_refs = []
        for a, b in refs:
            n = a or b
            if n and f"m{n}" in material_ids:
                mat_refs.append(f"m{n}")

        # 最后一题为大作文
        is_last = (i + 2 >= len(q_blocks))
        if is_last or "议论文" in block or "写一篇" in block and "1000" in block:
            q_type = "ESSAY"
            mat_refs = material_ids  # 大作文引用全部材料
        else:
            q_type = "SMALL"
            if not mat_refs and material_ids:
                # 若无法从题干推断，小题默认只引用第一则材料（保守）
                mat_refs = [material_ids[0]] if material_ids else []

        # 分值
        score_m = re.search(r"（(\d+)分）|\((\d+)分\)|(\d+)分", block)
        max_score = 20
        if score_m:
            for g in score_m.groups():
                if g:
                    max_score = int(g)
                    break

        # 字数
        wm = re.search(r"不超过(\d+)字|不少于(\d+)字|(\d+)[～~\-](\d+)字", block)
        word_limit = 300
        if wm:
            gs = wm.groups()
            if gs[2] and gs[3]:  # 1000～1200字
                word_limit = (int(gs[2]) + int(gs[3])) // 2
            elif gs[0]:
                word_limit = int(gs[0])
            elif gs[1]:
                word_limit = int(gs[1])

        questions.append({
            "id": f"q{len(questions)+1}",
            "title": title_part,
            "requirements": req_part,
            "maxScore": max_score,
            "wordLimit": word_limit,
            "type": q_type,
            "materialIds": mat_refs,
        })

    return questions


def pdf_to_json(pdf_path: Path) -> dict | None:
    """将单个 PDF 转为 JSON 结构"""
    text = extract_full_text(pdf_path)
    if not text or len(text) < 500:
        return None

    paper_id, name, year, _ = parse_filename_to_id(pdf_path.name)
    materials = parse_materials(text)
    material_ids = [m["id"] for m in materials]
    questions = parse_questions(text, material_ids)

    if not materials:
        print(f"  警告: {pdf_path.name} 未解析出材料")
    if not questions:
        print(f"  警告: {pdf_path.name} 未解析出题目")

    return {
        "id": paper_id,
        "name": name,
        "examType": "公务员",
        "region": "海南",
        "year": year,
        "materials": materials,
        "questions": questions,
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pdf_files = sorted(HAINAN_PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"未找到 PDF 文件: {HAINAN_PDF_DIR}")
        return

    print(f"找到 {len(pdf_files)} 个海南 PDF，开始转换...")
    success = 0
    for pdf_path in pdf_files:
        try:
            data = pdf_to_json(pdf_path)
            if data and (data.get("materials") or data.get("questions")):
                out_path = OUTPUT_DIR / f"{data['id']}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=0)
                print(f"  ✓ {pdf_path.name} -> {out_path.name}")
                success += 1
            else:
                print(f"  ✗ {pdf_path.name} 解析结果为空，跳过")
        except Exception as e:
            print(f"  ✗ {pdf_path.name} 失败: {e}")

    print(f"\n完成：成功 {success}/{len(pdf_files)} 份，输出目录: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
