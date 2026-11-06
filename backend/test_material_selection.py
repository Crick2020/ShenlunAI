"""校验「小题只发对应材料」的选取逻辑。

重点复现线上故障：APP 端内置离线包版本较旧，payload 只带 1 份材料（m1）且题目 materialIds 只写 ['m1']，
而后端试卷文件里该题应为 资料1-4（m1~m4）。修复后应始终按试卷文件的 materialIds 发送 4 份材料。

运行（需先安装 fastapi）：
    cd backend && python3 test_material_selection.py
"""
import json
import sys

import main as backend

FAKE_OUTPUT = "## 批改结果\n（测试桩输出）"


def grade_with_capture(payload):
    """调用 grade_essay，拦截模型调用，返回发给模型的 prompt。"""
    captured = {}

    def fake_call(prompt, image_data_list=None, *, temperature=0.3, top_p=0.9):
        captured["prompt"] = prompt
        return FAKE_OUTPUT, "test", "test-model"

    original = backend.call_grading_model
    backend.call_grading_model = fake_call
    try:
        backend.grade_essay(request=None, payload=payload)
    finally:
        backend.call_grading_model = original
    return captured.get("prompt", "")


def check(name, prompt, expect_ids, forbid_ids=()):
    hit = [i for i in expect_ids if f'"id": "{i}"' in prompt]
    leaked = [i for i in forbid_ids if f'"id": "{i}"' in prompt]
    ok = len(hit) == len(expect_ids) and not leaked
    print(f"[{'通过' if ok else '失败'}] {name} → 命中 {hit}；多余 {leaked}")
    return ok


def main_test():
    paper = json.load(open("data/gwy_jiangsu_2025_C.json", encoding="utf-8"))
    m1 = paper["materials"][0]
    q1, q2 = paper["questions"][0], paper["questions"][1]
    expect = ["m1", "m2", "m3", "m4"]

    ok = True

    # 场景1：线上故障复现——旧版 APP 只带 m1，题目 materialIds 也只写 m1
    p1 = {
        "paperId": "gwy_jiangsu_2025_C",
        "gradingSessionId": "session-test-1",
        "materials": [m1],
        "question": {"id": "q1", "type": "SMALL", "title": q1["title"], "materialIds": ["m1"]},
        "answers": {"q1": "考生作答内容"},
        "question_id": "q1",
    }
    ok &= check("旧版 APP 只带 m1", grade_with_capture(p1), expect)

    # 场景2：正常 APP，payload 带齐 m1~m4
    p2 = dict(p1, materials=[m for m in paper["materials"] if m["id"] in expect])
    ok &= check("正常 APP 带 m1~m4", grade_with_capture(p2), expect)

    # 场景3：payload 完全不带材料
    p3 = {
        "paperId": "gwy_jiangsu_2025_C",
        "question": {"id": "q1", "type": "SMALL", "title": q1["title"]},
        "answers": {"q1": "考生作答内容"},
        "question_id": "q1",
    }
    ok &= check("payload 无材料", grade_with_capture(p3), expect)

    # 场景4：第二题只应发 m5，不能串入 m1
    p4 = {
        "paperId": "gwy_jiangsu_2025_C",
        "materials": [m1],
        "question": {"id": "q2", "type": "SMALL", "title": q2["title"], "materialIds": ["m5"]},
        "answers": {"q2": "考生作答内容"},
        "question_id": "q2",
    }
    ok &= check("第二题只发 m5", grade_with_capture(p4), ["m5"], forbid_ids=["m1"])

    print("总体:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main_test())
