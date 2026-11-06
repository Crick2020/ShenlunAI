"""批量预生成小题「踩分标尺」（rubric），让每道题的要点在发版前就固定下来。

为什么需要它：批改时如果标尺不存在，会在第一次批改现场生成（多一次模型调用）。
预生成并提交到仓库后，线上（Render 等临时文件系统）重启也不会丢，所有用户拿到的都是同一份标尺。

用法：
    cd backend
    python3 scripts/build_rubrics.py --limit 5              # 先试 5 道题看看效果
    python3 scripts/build_rubrics.py --paper gwy_jiangsu_2025_C
    python3 scripts/build_rubrics.py --force                # 覆盖重建已有标尺
    python3 scripts/build_rubrics.py --dry-run              # 只看会生成哪些，不调模型

需要环境变量里有模型 Key（同线上：DEEPSEEK_API_KEY 等）。
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


def iter_questions(paper):
    for q in paper.get("questions") or []:
        if not isinstance(q, dict):
            continue
        if (q.get("type") or "").upper() == "ESSAY":
            continue
        yield q


def pick_materials(paper, question):
    all_materials = paper.get("materials") or []
    ids = question.get("materialIds") or question.get("material_ids") or []
    ids = ids if isinstance(ids, list) else [ids]
    if not ids:
        return all_materials
    wanted = set()
    for i in ids:
        wanted |= backend._id_variants(i)
    return [m for m in all_materials if backend._id_variants(backend._material_id(m)) & wanted]


def main():
    parser = argparse.ArgumentParser(description="批量生成小题踩分标尺")
    parser.add_argument("--paper", help="只处理指定试卷 id（不含 .json）")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少道题")
    parser.add_argument("--force", action="store_true", help="已存在也重新生成")
    parser.add_argument("--dry-run", action="store_true", help="只列出计划，不调用模型")
    args = parser.parse_args()

    files = sorted(glob.glob(os.path.join(backend.get_data_dir(), "*.json")))
    if args.paper:
        files = [f for f in files if os.path.basename(f) == f"{args.paper}.json"]

    created = skipped = failed = planned = 0
    for path in files:
        try:
            paper = json.load(open(path, encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"[跳过] {os.path.basename(path)} 解析失败: {e}")
            continue
        paper_id = str(paper.get("id") or os.path.basename(path)[:-5])
        for q in iter_questions(paper):
            qid = str(q.get("id") or q.get("qid") or "")
            if not qid:
                continue
            materials = pick_materials(paper, q)
            max_score = int(q.get("maxScore") or q.get("score") or 20)
            material_hash = backend._rubric_material_hash(materials)
            exists = backend._load_rubric(paper_id, qid, material_hash) is not None

            if args.dry_run:
                planned += 1
                print(f"[计划] {paper_id} {qid} 满分{max_score} 材料{len(materials)}份 {'(已有)' if exists else ''}")
                continue

            if exists and not args.force:
                skipped += 1
                continue

            if args.force and exists:
                try:
                    os.remove(backend._rubric_path(paper_id, qid))
                except OSError:
                    pass

            rubric, source = backend.get_or_create_rubric(
                paper_id=paper_id,
                question=q,
                materials=materials,
                max_score=max_score,
                province_label=(backend.PROVINCE_GRADING_PROFILE.get(paper.get("region")) or {}).get("label", ""),
            )
            if rubric:
                created += 1
                q = rubric.get("quality") or {}
                print(
                    f"[完成] {paper_id} {qid} {len(rubric['points'])} 个要点 / {max_score} 分 "
                    f"status={rubric.get('status')} evidence={q.get('verifiedRatio')} "
                    f"coverage={'✓' if q.get('coverageComplete') else '✗'}"
                )
                if rubric.get("status") != "approved":
                    print("        ↑ 质量未达标，已存为 draft（仅作参考）；可人工复核后 "
                          f"`python3 scripts/review_rubrics.py --approve {paper_id}__{qid}`")
            else:
                failed += 1
                print(f"[失败] {paper_id} {qid}")

            if args.limit and (created + failed) >= args.limit:
                print(f"\n达到 --limit {args.limit}，停止")
                print(f"汇总：新建 {created}，跳过 {skipped}，失败 {failed}")
                return 0 if failed == 0 else 1

    if args.dry_run:
        print(f"\n共 {planned} 道小题待处理（dry-run，未调用模型）")
    else:
        print(f"\n汇总：新建 {created}，跳过 {skipped}，失败 {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
