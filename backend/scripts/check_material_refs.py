"""试卷数据自检：题目材料引用是否完整、前后端试卷是否一致。

检查三件事：
1. 每道题的 materialIds 都能在 materials 中找到（否则批改会缺材料）；
2. 题目标题里写明的「资料 1-4 / 资料 2、3、5」等引用，是否都被 materialIds 覆盖；
3. frontend/public/papers（APP 内置离线试卷）与 backend/data 是否一致（防止发版后数据漂移）。

用法：
    python3 scripts/check_material_refs.py          # 只检查后端 data
    python3 scripts/check_material_refs.py --all    # 同时比对内置试卷
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DATA = os.path.abspath(os.path.join(HERE, "..", "data"))
BUNDLED_PAPERS = os.path.abspath(os.path.join(HERE, "..", "..", "frontend", "public", "papers"))

REF_PATTERN = re.compile(
    r"(?:给定资料|给定材料|资料|材料)\s*([0-9]+(?:\s*(?:[-~～—至]|、|,|，|和|及)\s*[0-9]+)*)"
)
ENUM_SPLIT = re.compile(r"\s*(?:、|,|，|和|及)\s*")
RANGE_SEP = re.compile(r"\s*[-~～—至]\s*")


def parse_refs(text):
    """从题干中解析出引用的资料序号集合。

    '资料1-4' -> {1,2,3,4}；'资料2、3、5' -> {2,3,5}（列举式不按区间展开）。
    """
    refs = set()
    for match in REF_PATTERN.finditer(text or ""):
        for chunk in ENUM_SPLIT.split(match.group(1)):
            nums = [int(n) for n in re.findall(r"\d+", chunk)]
            if not nums:
                continue
            if len(nums) > 1 and RANGE_SEP.search(chunk):
                refs.update(range(min(nums), max(nums) + 1))
            else:
                refs.update(nums)
    return refs


def id_number(value):
    m = re.fullmatch(r"[mM]?(\d+)", str(value or "").strip())
    return int(m.group(1)) if m else None


def check_paper(path, strict_refs=True):
    problems = []
    try:
        paper = json.load(open(path, encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [f"JSON 解析失败: {exc}"]

    material_ids = [m.get("id") for m in (paper.get("materials") or [])]
    for q in paper.get("questions") or []:
        qid = q.get("id")
        ids = q.get("materialIds") or q.get("material_ids") or []
        ids = ids if isinstance(ids, list) else [ids]
        missing = [i for i in ids if i not in material_ids]
        if missing:
            problems.append(f"{qid} 引用了不存在的材料 {missing}")
        if not ids:
            problems.append(f"{qid} 缺少 materialIds（批改会退化为发全卷）")
            continue
        if strict_refs:
            refs = parse_refs((q.get("title") or "") + (q.get("requirements") or ""))
            covered = {id_number(i) for i in ids} - {None}
            uncovered = sorted(refs - covered)
            if uncovered:
                problems.append(f"{qid} 题干引用资料 {sorted(refs)}，但 materialIds 只覆盖 {sorted(covered)}")
    return problems


def main():
    check_all = "--all" in sys.argv
    total = 0
    failed = 0

    files = sorted(glob.glob(os.path.join(BACKEND_DATA, "*.json")))
    print(f"检查后端试卷 {len(files)} 份 ...")
    for path in files:
        total += 1
        problems = check_paper(path)
        if problems:
            failed += 1
            print(f"  ✗ {os.path.basename(path)}")
            for p in problems:
                print(f"      - {p}")

    if check_all:
        print(f"比对内置离线试卷 {BUNDLED_PAPERS} ...")
        for path in files:
            name = os.path.basename(path)
            bundled = os.path.join(BUNDLED_PAPERS, name)
            if not os.path.exists(bundled):
                print(f"  ✗ 内置试卷缺失: {name}")
                failed += 1
                continue
            if json.load(open(path, encoding="utf-8")) != json.load(open(bundled, encoding="utf-8")):
                print(f"  ✗ 与后端数据不一致（需要重新同步并重新打包 APP）: {name}")
                failed += 1

    print(f"\n完成：共 {total} 份，问题 {failed} 份")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
