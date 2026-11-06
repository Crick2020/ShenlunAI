"""标尺审核工具：查看质量、复核证据、把 draft 升级为 approved。

用法：
    cd backend
    python3 scripts/review_rubrics.py --list                 # 列出所有标尺及质量指标
    python3 scripts/review_rubrics.py --show gwy_jiangsu_2025_C__q1
    python3 scripts/review_rubrics.py --verify gwy_jiangsu_2025_C__q1   # 重新跑证据校验
    python3 scripts/review_rubrics.py --approve gwy_jiangsu_2025_C__q1  # 人工确认后升级
    python3 scripts/review_rubrics.py --reject  gwy_jiangsu_2025_C__q1  # 打回 draft

质量指标含义：
    evidence=1.00  每个要点的 evidence 都能在材料原文中找到（越高越可信）
    keyword=1.00   要点关键词在材料中出现的比例
    coverage=✓     每份材料都有要点归属（防漏段）
    status         approved=批改时强制执行；draft=仅作参考，允许模型补充
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, BACKEND_DIR)

import main as backend  # noqa: E402


def load_rubrics():
    files = sorted(glob.glob(os.path.join(backend.RUBRIC_DIR, "*.json")))
    items = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                items.append((path, json.load(f)))
        except Exception as e:  # noqa: BLE001
            print(f"[跳过] {os.path.basename(path)} 解析失败: {e}")
    return items


def find_rubric(rubric_id):
    for path, rubric in load_rubrics():
        if os.path.basename(path) == f"{rubric_id}.json":
            return path, rubric
    return None, None


def print_row(path, rubric):
    q = rubric.get("quality") or {}
    status = rubric.get("status") or "approved"
    flag = "✓" if q.get("coverageComplete") else "✗"
    print(
        f"{os.path.basename(path)[:-5]:<44} "
        f"{rubric.get('questionId', ''):<4} "
        f"{status:<9} "
        f"要点{len(rubric.get('points') or []):<3} "
        f"evidence={q.get('verifiedRatio', '-'):<5} "
        f"keyword={q.get('keywordRatio', '-'):<5} "
        f"coverage={flag} "
        f"满分{rubric.get('maxScore', '-')}"
    )


def cmd_list():
    items = load_rubrics()
    if not items:
        print(f"还没有标尺文件（目录：{backend.RUBRIC_DIR}）")
        return 0
    print(f"{'文件':<44} {'题':<4} {'状态':<9} {'要点':<4} {'质量':<20}")
    for path, rubric in items:
        print_row(path, rubric)
    approved = sum(1 for _, r in items if (r.get("status") or "approved") == "approved")
    print(f"\n共 {len(items)} 份，approved {approved} 份，draft {len(items) - approved} 份")
    return 0


def cmd_show(rubric_id):
    path, rubric = find_rubric(rubric_id)
    if not rubric:
        print(f"未找到标尺：{rubric_id}")
        return 1
    print(json.dumps(rubric, ensure_ascii=False, indent=2))
    return 0


def _load_materials(rubric):
    paper = backend._load_paper_by_id(rubric.get("paperId"))
    if not paper:
        return None
    qid = rubric.get("questionId")
    question = next(
        (q for q in paper.get("questions") or [] if str(q.get("id")) == str(qid)),
        None,
    )
    all_materials = paper.get("materials") or []
    ids = (question or {}).get("materialIds") or (question or {}).get("material_ids") or []
    ids = ids if isinstance(ids, list) else [ids]
    if not ids:
        return all_materials
    wanted = set()
    for i in ids:
        wanted |= backend._id_variants(i)
    return [m for m in all_materials if backend._id_variants(backend._material_id(m)) & wanted]


def cmd_verify(rubric_id, approve_if_pass=False):
    path, rubric = find_rubric(rubric_id)
    if not rubric:
        print(f"未找到标尺：{rubric_id}")
        return 1
    materials = _load_materials(rubric)
    if not materials:
        print("找不到对应试卷材料，无法复核")
        return 1
    quality = backend._verify_rubric_quality(rubric, materials)
    if approve_if_pass:
        rubric["status"] = backend._rubric_status_by_quality(quality)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rubric, f, ensure_ascii=False, indent=2)
    print(json.dumps(quality, ensure_ascii=False, indent=2))
    for p in rubric.get("points") or []:
        mark = {"exact": "✓", "partial": "≈", "": "✗"}.get(p.get("evidenceMatch", ""), "?")
        print(f"  {mark} 要点{p.get('no')}: {p.get('summary')}  ← {str(p.get('evidence'))[:30]}")
    return 0


def cmd_set_status(rubric_id, status):
    path, rubric = find_rubric(rubric_id)
    if not rubric:
        print(f"未找到标尺：{rubric_id}")
        return 1
    rubric["status"] = status
    rubric["reviewedAt"] = backend.datetime.now(backend.timezone.utc).astimezone().isoformat(timespec="seconds")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rubric, f, ensure_ascii=False, indent=2)
    print(f"已把 {rubric_id} 标记为 {status}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="标尺审核工具")
    parser.add_argument("--list", action="store_true", help="列出所有标尺")
    parser.add_argument("--show", metavar="ID", help="打印标尺 JSON")
    parser.add_argument("--verify", metavar="ID", help="重新跑证据校验")
    parser.add_argument("--verify-all", action="store_true", help="对所有标尺重跑证据校验")
    parser.add_argument("--approve", metavar="ID", help="标记为 approved")
    parser.add_argument("--reject", metavar="ID", help="标记为 draft")
    args = parser.parse_args()

    if args.list:
        return cmd_list()
    if args.show:
        return cmd_show(args.show)
    if args.verify:
        return cmd_verify(args.verify)
    if args.verify_all:
        for path, rubric in load_rubrics():
            rid = os.path.basename(path)[:-5]
            cmd_verify(rid)
        return 0
    if args.approve:
        return cmd_set_status(args.approve, "approved")
    if args.reject:
        return cmd_set_status(args.reject, "draft")
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
