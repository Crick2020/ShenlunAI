
import os
from pathlib import Path

def generate_map(region_name, folder_name):
    base_path = Path("/Users/luzhipeng/Documents/学习及生活/申论") / folder_name
    if not base_path.exists():
        print(f"Path not found: {base_path}")
        return

    files = sorted([f for f in os.listdir(base_path) if f.endswith(".pdf")])
    
    print(f'    "{region_name}": (')
    print(f'        SHENLUN_BASE / "{folder_name}",')
    print(f'        "{region_name}",')
    print('        {')
    
    for f in files:
        # Generate ID
        # Example: 2018年公务员多省联考《申论》题（湖南乡镇卷）.pdf -> gwy_hunan_2018_XiangZhen
        # Example: 2021年江苏省公考《申论》题（A、普通选调卷）.pdf -> gwy_jiangsu_2021_A
        
        year = f[:4]
        
        # Determine suffix
        suffix = ""
        if "乡镇" in f or "县乡" in f:
            suffix = "XiangZhen" # Standardize
        elif "行政执法" in f:
            suffix = "XingZhengZhiFa"
        elif "省市" in f or "市级" in f:
            suffix = "ShengShi"
        elif "通用" in f:
            suffix = "TongYong"
        elif "A" in f or "甲" in f:
            suffix = "A"
        elif "B" in f or "乙" in f:
            suffix = "B"
        elif "C" in f or "丙" in f:
            suffix = "C"
        else:
            suffix = "General"
            
        # Refine suffix based on specific keywords to match existing style if possible, 
        # but standardized is better.
        
        # Jiangsu specific
        if region_name == "江苏":
            if "A" in f: suffix = "A"
            elif "B" in f: suffix = "B"
            elif "C" in f: suffix = "C"
            
        # Jilin specific
        if region_name == "吉林":
            if "甲" in f: suffix = "A"
            elif "乙" in f: suffix = "B"
            elif "丙" in f: suffix = "C"

        # Hunan specific
        if region_name == "湖南":
            if "乡镇" in f or "县乡" in f: suffix = "XiangZhen"
            elif "行政执法" in f: suffix = "XingZhengZhiFa"
            elif "省市" in f: suffix = "ShengShi"
            elif "通用" in f: suffix = "TongYong"

        
        # Pinyin for region
        region_pinyin = {
            "湖南": "hunan",
            "江苏": "jiangsu",
            "吉林": "jilin",
            "江西": "jiangxi",
            "辽宁": "liaoning",
            "内蒙古": "neimenggu",
            "宁夏": "ningxia",
            "青海": "qinghai",
            "山东": "shandong",
            "山西": "shanxi",
            "陕西": "shaanxi"
        }.get(region_name, "unknown")
        
        paper_id = f"gwy_{region_pinyin}_{year}_{suffix}"
        print(f'            "{f}": "{paper_id}",')
        
    print('        },')
    print('    ),')

print("# Generated Maps")
generate_map("山东", "山东")
generate_map("山西", "山西")
generate_map("陕西", "陕西")
