import os
import re
import json
from typing import Dict, List, Optional, Tuple

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

PDF_DIR = "/Users/luzhipeng/Documents/学习及生活/申论/湖北"
OUT_DIR = "/Users/luzhipeng/Documents/喂/ShenlunAI/backend/data"

# 需要跳过的已精修文件
SKIP_FILES = {
    "gwy_hubei_2024_ShengShi.json",
    "gwy_hubei_2025_ShengShi.json"
}

def normalize_text(text: str) -> str:
    """
    标准化文本，处理特殊字符和奇怪的空格
    """
    # 替换康熙部首为标准汉字
    replacements = {
        '⼀': '一', '⼆': '二', '三': '三', '四': '四', '五': '五',
        '六': '六', '七': '七', '⼋': '八', '九': '九', '⼗': '十'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    
    # 修复数字间的空格，如 "2 019" -> "2019"
    # 匹配规则：数字+空格+数字，且空格前后不是标点
    text = re.sub(r'(?<=\d) (?=\d)', '', text)
    
    return text

def clean_content(text: str) -> str:
    """
    清洗PDF提取的文本，去除页眉页脚、答题纸等无关内容
    """
    lines = text.split('\n')
    cleaned_lines = []
    
    # 标记是否在“答题纸”区域
    in_answer_sheet = False
    
    # 标记是否在“注意事项”区域
    in_notice = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 1. 去除页眉页脚特征
        if re.search(r'本试卷由粉笔用户.*生成', line):
            continue
        if re.search(r'第 \d+ 页，共 \d+ 页', line):
            continue
        if re.search(r'^\d+年.*公务员.*《申论》题', line):
            continue
        if re.search(r'^-- \d+ of \d+ --$', line):
            continue
        # 去除残留的页眉片段，如 "乡卷）"
        if re.search(r'^[^\u4e00-\u9fa5]*卷）$', line):
            continue
            
        # 2. 去除“答题纸”及其之后的内容
        if '答题纸' in line and len(line) < 10:
            in_answer_sheet = True
            continue
        if in_answer_sheet:
            continue
            
        # 3. 去除“注意事项”到“给定材料”之间的内容
        if line == '注意事项':
            in_notice = True
            continue
        if in_notice:
            if '给定材料' in line or '给定资料' in line:
                in_notice = False
                # 不跳过这一行，因为它是材料开始的标记
            else:
                continue
                
        cleaned_lines.append(line)
        
    return '\n'.join(cleaned_lines)

def parse_materials(text: str) -> List[Dict]:
    """
    解析给定材料
    """
    materials = []
    
    # 定位“给定材料”或“给定资料”
    # 忽略之前的所有内容
    match = re.search(r'(?:^|\n)(给定材料|给定资料)', text)
    if not match:
        # 如果找不到标记，尝试直接找“材料1”
        start_idx = 0
    else:
        start_idx = match.start()
        
    # 截取从材料开始到“作答要求”之前的内容
    req_match = re.search(r'(?:^|\n)作答要求', text[start_idx:])
    if req_match:
        material_text = text[start_idx : start_idx + req_match.start()]
    else:
        material_text = text[start_idx:]
        
    # 分割材料
    # 使用正则 split，保留捕获组（材料编号）
    # 匹配 "材料1"、"材料一"、"资料1" 等
    # (?:^|\n) 确保匹配行首
    # \s* 允许前面有空格
    # (?:材料|资料) 匹配前缀
    # \s* 允许中间有空格
    # ([\d一二三四五六七八九十]+) 捕获编号
    parts = re.split(r'(?:^|\n)\s*(?:材料|资料)\s*([\d一二三四五六七八九十]+)', material_text)
    
    # parts[0] 是“给定材料”这几个字以及之前的空白
    # parts[1] 是编号1
    # parts[2] 是内容1
    # parts[3] 是编号2
    # parts[4] 是内容2
    # ...
    
    if len(parts) < 3:
        # 没分割成功，可能只有一个材料或者格式不对
        # 尝试直接把 material_text 作为 m1
        # 去掉开头的 "给定材料"
        content = re.sub(r'^(给定材料|给定资料)\s*', '', material_text).strip()
        if content:
            materials.append({
                "id": "m1",
                "title": "材料",
                "content": content
            })
        return materials

    # 从索引1开始遍历，步长为2
    for i in range(1, len(parts), 2):
        num_str = parts[i].strip()
        content = parts[i+1].strip()
        
        # 转换中文数字为阿拉伯数字（用于ID）
        num_map = {'一': '1', '二': '2', '三': '3', '四': '4', '五': '5', 
                   '六': '6', '七': '7', '八': '8', '九': '9', '十': '10'}
        m_id_suffix = num_map.get(num_str, num_str)
        
        materials.append({
            "id": f"m{m_id_suffix}",
            "title": f"材料{num_str}",
            "content": content
        })
        
    return materials

def extract_meta(q_text: str) -> Tuple[int, int]:
    score = 0
    word_limit = 0
    
    # 提取分值，兼容全角半角括号
    s_match = re.search(r'[（(](\d+)分[)）]', q_text)
    if s_match:
        score = int(s_match.group(1))
        
    # 提取字数
    # 1. 不超过xxx字
    w_match = re.search(r'不超过(\d+)字', q_text)
    if not w_match:
        # 2. xxx-xxx字 (兼容破折号、波浪号、汉字到)
        w_match = re.search(r'(\d+)\s*[-~到—]\s*(\d+)字', q_text)
        if w_match:
            word_limit = int(w_match.group(2))
    else:
        word_limit = int(w_match.group(1))

    if not w_match and word_limit == 0:
        # 3. xxx字左右
        w_match = re.search(r'(\d+)字左右', q_text)
        if w_match:
            word_limit = int(w_match.group(1))
            
    return score, word_limit

def parse_questions(text: str, material_ids: List[str]) -> List[Dict]:
    """
    解析作答要求
    """
    questions = []
    
    match = re.search(r'(?:^|\n)作答要求', text)
    if not match:
        return []
        
    req_text = text[match.end():]
    
    # 分割题目
    # 匹配 "第一题"、"一、"、"1." 等
    # 常见格式： "第一题"
    parts = re.split(r'(?:^|\n)(第[一二三四五]题)', req_text)
    
    current_title = "" # 这里其实是题号，如“第一题”
    current_content = []
    
    def process_question(title, content_lines):
        full_text = "\n".join(content_lines).strip()
        if not full_text:
            return
            
        score, word_limit = extract_meta(full_text)
        
        # 尝试推断关联材料
        m_refs = []
        # 匹配 "根据给定资料1"、"结合材料2" 等
        # 增加对 "资料3" 的匹配
        m_matches = re.findall(r'(?:资料|材料)\s*(\d+|[一二三四五])', full_text)
        for m_num in m_matches:
            # 简单映射：1->m1, 一->m1
            num_map = {'一': '1', '二': '2', '三': '3', '四': '4', '五': '5'}
            idx = num_map.get(m_num, m_num)
            m_id = f"m{idx}"
            if m_id in material_ids:
                m_refs.append(m_id)
        
        # 判断题型
        q_type = "ESSAY" if score >= 35 or word_limit >= 800 else "SMALL"
        
        # 提取题目内容（通常是第一段）和要求（通常以“要求：”开头）
        split_req = re.split(r'(?:^|\n)要求：', full_text)
        q_title_text = split_req[0].strip()
        q_req = "要求：" + "".join(split_req[1:]).strip() if len(split_req) > 1 else ""
        
        questions.append({
            "id": f"q{len(questions)+1}",
            "title": q_title_text,
            "requirements": q_req,
            "maxScore": score,
            "wordLimit": word_limit,
            "type": q_type,
            "materialIds": list(set(m_refs))
        })

    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        if re.match(r'^第[一二三四五]题$', part):
            if current_title:
                process_question(current_title, current_content)
            current_title = part
            current_content = []
        else:
            current_content.append(part)
            
    # 处理最后一题
    if current_title:
        process_question(current_title, current_content)
        
    return questions

def detect_year(filename: str) -> int:
    m = re.search(r"(20\d{2})", filename)
    if not m:
        return 2025 # Default
    return int(m.group(1))

def detect_suffix(filename: str) -> str:
    if "省市县卷" in filename:
        return "ShengShiXian"
    if "省市卷" in filename:
        return "ShengShi"
    if "县乡卷" in filename or "县级卷" in filename or "乡镇卷" in filename:
        return "XianXiang"
    if "湖北卷" in filename:
        return "General"
    return "General"

def build_id(year: int, filename: str) -> str:
    suffix = detect_suffix(filename)
    return f"gwy_hubei_{year}_{suffix}"

def extract_text(pdf_path: str) -> str:
    if PdfReader is None:
        raise RuntimeError("PyPDF2 未安装")
    reader = PdfReader(pdf_path)
    texts = []
    for page in reader.pages:
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        texts.append(txt)
    return "\n".join(texts)

def main():
    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)
        
    for fname in os.listdir(PDF_DIR):
        if not fname.lower().endswith(".pdf"):
            continue
            
        year = detect_year(fname)
        _id = build_id(year, fname)
        out_name = f"{_id}.json"
        
        # 跳过已精修文件
        if out_name in SKIP_FILES:
            print(f"跳过已精修文件: {out_name}")
            continue
            
        pdf_path = os.path.join(PDF_DIR, fname)
        print(f"正在处理: {fname} -> {out_name}")
        
        try:
            raw_text = extract_text(pdf_path)
            norm_text = normalize_text(raw_text)
            cleaned_text = clean_content(norm_text)
            
            materials = parse_materials(cleaned_text)
            material_ids = [m['id'] for m in materials]
            questions = parse_questions(cleaned_text, material_ids)
            
            # 如果解析失败，回退到全文模式
            if not materials:
                print(f"  警告: 未能识别材料结构，回退到全文模式: {fname}")
                materials = [{
                    "id": "m1",
                    "title": "材料",
                    "content": cleaned_text
                }]
                
            data = {
                "id": _id,
                "name": os.path.splitext(fname)[0],
                "examType": "公务员",
                "region": "湖北",
                "year": year,
                "materials": materials,
                "questions": questions
            }
            
            out_path = os.path.join(OUT_DIR, out_name)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"  失败: {e}")

if __name__ == "__main__":
    main()
