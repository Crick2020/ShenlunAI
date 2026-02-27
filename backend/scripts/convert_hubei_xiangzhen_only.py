import os
import re
import json
from pathlib import Path
from typing import List, Dict

# 复用已有的解析逻辑
import sys
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.append(str(CURRENT_DIR))

import convert_hubei_pdfs_v2 as base

PDF_DIR = Path('/Users/luzhipeng/Documents/学习及生活/申论/湖北')
OUT_DIR = Path('/Users/luzhipeng/Documents/喂/ShenlunAI/backend/data')

TARGET_FILES = [
    '2019年公务员多省联考《申论》题（湖北乡镇卷）.pdf',
    '2020年0822公务员多省联考《申论》题（湖北乡镇卷）.pdf',
]


def detect_year(filename: str) -> int:
    m = re.search(r'(20\d{2})', filename)
    return int(m.group(1)) if m else 0


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for fname in TARGET_FILES:
        pdf_path = PDF_DIR / fname
        if not pdf_path.exists():
            print(f'跳过(文件不存在): {pdf_path}')
            continue

        year = detect_year(fname)
        paper_id = f'gwy_hubei_{year}_XiangZhen'
        out_path = OUT_DIR / f'{paper_id}.json'

        print(f'处理乡镇卷: {fname} -> {out_path.name}')

        raw_text = base.extract_text(str(pdf_path))
        norm_text = base.normalize_text(raw_text)
        cleaned_text = base.clean_content(norm_text)

        materials = base.parse_materials(cleaned_text)
        material_ids = [m['id'] for m in materials]
        questions = base.parse_questions(cleaned_text, material_ids)

        # 大作文题如果未显式关联材料，则默认关联全部材料
        for q in questions:
            if q.get('type') == 'ESSAY' and not q.get('materialIds'):
                q['materialIds'] = list(material_ids)

        if not materials:
            materials = [{
                'id': 'm1',
                'title': '材料',
                'content': cleaned_text,
            }]

        data = {
            'id': paper_id,
            'name': os.path.splitext(fname)[0],
            'examType': '公务员',
            'region': '湖北',
            'year': year,
            'materials': materials,
            'questions': questions,
        }

        with out_path.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
