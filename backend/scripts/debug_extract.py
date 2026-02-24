
import sys
import re
import pdfplumber
from pathlib import Path

def extract_text(pdf_path):
    full = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            t = p.extract_text()
            if t:
                full.append(t)
    return "\n".join(full)

path = Path("/Users/luzhipeng/Documents/学习及生活/申论/安徽/2018年公务员多省联考《申论》题（安徽A、普通选调卷）.pdf")
text = extract_text(path)
print(text[-1000:])
