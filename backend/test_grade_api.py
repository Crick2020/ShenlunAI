#!/usr/bin/env python3
"""测试 /api/grade 接口：图片上传相关逻辑（has_images 与 answer_images 校验）。"""
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"


def post_grade(payload: dict):
    """POST /api/grade，返回 (status_code, body_dict 或 error_message)。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/grade",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return (resp.status, json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            detail = json.loads(body)
        except Exception:
            detail = body
        return (e.code, detail)
    except Exception as e:
        return (-1, str(e))


def test_has_images_but_empty_answer_images():
    """前端标记有图片但未传 answer_images 时应返回 400。"""
    payload = {
        "paperId": "gwy_guojia_2023_Dishiji",
        "question_id": "q1",
        "has_images": True,
        "answer_images": [],
        "answers": {"q1": "（考生上传了作答图片，请根据图片内容批改）"},
        "materials": [{"id": "m1", "title": "材料1", "content": "测试材料"}],
        "question": {"id": "q1", "title": "测试题", "requirements": "无", "maxScore": 10},
    }
    status, body = post_grade(payload)
    assert status == 400, f"期望 400，得到 {status}: {body}"
    detail = body.get("detail", "") if isinstance(body, dict) else str(body)
    assert "未收到图片" in detail or "图片" in detail, f"期望错误信息含图片相关提示: {detail}"
    print("[OK] has_images=true 且 answer_images=[] 正确返回 400")


def test_no_images_normal_submit():
    """无图片、正常文字答案时应能通过校验（可能因缺材料/题目在后一步报错，但不应在图片校验处 400）。"""
    payload = {
        "paperId": "gwy_guojia_2023_Dishiji",
        "question_id": "q1",
        "has_images": False,
        "answers": {"q1": "这是一段文字答案"},
        "materials": [{"id": "m1", "title": "材料1", "content": "测试材料内容"}],
        "question": {"id": "q1", "title": "测试题", "requirements": "无", "maxScore": 10},
    }
    status, body = post_grade(payload)
    # 不应是“前端标记有图片但未收到”的 400
    if status == 400:
        detail = body.get("detail", "") if isinstance(body, dict) else str(body)
        assert "未收到图片" not in detail, f"无图片提交不应触发图片校验 400: {detail}"
    print(f"[OK] has_images=false 时未触发图片校验 400 (status={status})")


def main():
    print("正在连接后端", BASE, "...")
    try:
        urllib.request.urlopen(f"{BASE}/api/list", timeout=3)
    except Exception as e:
        print("请先启动后端: cd backend && uvicorn main:app --reload --port 8000")
        raise SystemExit(1) from e

    test_has_images_but_empty_answer_images()
    test_no_images_normal_submit()
    print("\n全部通过。")


if __name__ == "__main__":
    main()
