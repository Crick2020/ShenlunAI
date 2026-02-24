
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
        year = f[:4]
        suffix = "General"

        if region_name == "上海":
            if "A" in f: suffix = "A"
            elif "B" in f: suffix = "B"
            elif "行政执法" in f: suffix = "XingZhengZhiFa"
            
        elif region_name == "四川":
            parts = []
            if "上半年" in f: parts.append("ShangBanNian")
            elif "下半年" in f: parts.append("XiaBanNian")
            
            if "乡镇" in f: parts.append("XiangZhen")
            elif "县乡" in f: parts.append("XianXiang")
            elif "省市县" in f: parts.append("ShengShiXian")
            elif "省市" in f: parts.append("ShengShi")
            elif "行政执法" in f: parts.append("XingZhengZhiFa")
            elif "B" in f: parts.append("B")
            elif "C" in f: parts.append("C")
            elif "A" in f: parts.append("A")
            
            if parts:
                suffix = "_".join(parts)
            else:
                suffix = "General"

        elif region_name == "重庆":
            parts = []
            if "上半年" in f: parts.append("ShangBanNian")
            elif "下半年" in f: parts.append("XiaBanNian")
            
            if "乡镇" in f: parts.append("XiangZhen")
            elif "行政执法" in f: parts.append("XingZhengZhiFa")
            elif "通用" in f: parts.append("TongYong")
            
            if parts:
                suffix = "_".join(parts)
            else:
                suffix = "General"
                
        elif region_name == "深圳":
            if "I类" in f: suffix = "I"
            elif "II类" in f: suffix = "II"
            elif "III类" in f: suffix = "III"
            elif "A" in f: suffix = "A"
            elif "B" in f: suffix = "B"

        else:
            # Default logic for other regions (Tianjin, Yunnan, Zhejiang, etc.)
            if "乡镇" in f or "县乡" in f: suffix = "XiangZhen"
            elif "行政执法" in f: suffix = "XingZhengZhiFa"
            elif "省市" in f or "市级" in f: suffix = "ShengShi"
            elif "通用" in f: suffix = "TongYong"
            elif "A" in f or "甲" in f: suffix = "A"
            elif "B" in f or "乙" in f: suffix = "B"
            elif "C" in f or "丙" in f: suffix = "C"
            elif "I类" in f: suffix = "I"
            elif "II类" in f: suffix = "II"

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
            "陕西": "shaanxi",
            "上海": "shanghai",
            "四川": "sichuan",
            "重庆": "chongqing",
            "天津": "tianjin",
            "云南": "yunnan",
            "浙江": "zhejiang",
            "深圳": "shenzhen"
        }.get(region_name, "unknown")
        
        paper_id = f"gwy_{region_pinyin}_{year}_{suffix}"
        print(f'            "{f}": "{paper_id}",')
        
    print('        },')
    print('    ),')

print("# Generated Maps")
generate_map("重庆", "重庆")
generate_map("天津", "天津")
generate_map("云南", "云南")
generate_map("浙江", "浙江")
generate_map("深圳", "深圳")
