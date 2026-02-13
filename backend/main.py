from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import os
import re
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any

app = FastAPI()

# ---------------------------------------------------------
# 1. 跨域配置 (CORS) - 允许前端访问后端
# ---------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_log():
    """启动时打印 data 目录路径及文件，便于 Render 等环境排查试卷是否部署。"""
    data_dir = get_data_dir()
    exists = os.path.isdir(data_dir)
    files = list(os.listdir(data_dir)) if exists else []
    print(f"[Startup] data_dir={data_dir}, exists={exists}, cwd={os.getcwd()}, files={files[:20]}")

# 辅助函数：获取 data 文件夹路径（绝对路径，不依赖 cwd）
def get_data_dir():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "data")


def _load_paper_by_id(paper_id: str):
    """从 data 目录加载试卷，尝试主路径 + cwd/data 备用（兼容 Render 等部署）。"""
    data_dir = get_data_dir()
    for base in [data_dir, os.path.abspath("data")]:
        file_path = os.path.join(base, f"{paper_id}.json")
        if os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"读取试卷失败 {file_path}: {e}")
    print(f"试卷未找到: paper_id={paper_id}, data_dir={data_dir}, cwd={os.getcwd()}, data_dir_exists={os.path.isdir(data_dir)}")
    return None


# ---------------------------------------------------------
# 2. 接口：获取试卷列表 (用于首页展示卡片)
# ---------------------------------------------------------
@app.get("/api/list")
def list_papers():
    data_dir = get_data_dir()
    
    # 如果文件夹不存在，建一个空的，防止报错
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        return []

    papers = []
    
    # 遍历文件夹里的所有文件
    for filename in os.listdir(data_dir):
        if filename.endswith(".json"):
            try:
                file_path = os.path.join(data_dir, filename)
                with open(file_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    
                    # 提取前端首页卡片需要的所有信息
                    papers.append({
                        # 优先用文件里的 id，如果没有，就用文件名(去掉.json)
                        "id": content.get("id", filename[:-5]),
                        "name": content.get("name", "未命名试卷"),
                        "year": content.get("year", 2024),          # 默认 2024
                        "region": content.get("region", "全国"),    # 默认 全国
                        "examType": content.get("examType", "公务员") # 默认 公务员
                    })
            except Exception as e:
                print(f"读取文件 {filename} 出错: {e}")
                continue
                
    return papers


# ---------------------------------------------------------
# 3. 接口：获取单份试卷详情 (用于做题页面)
# 调用示例：/api/paper?id=gwy_jiangsu_2024_A
# ---------------------------------------------------------
@app.get("/api/paper")
def get_paper(id: str):
    data_dir = get_data_dir()
    
    # 尝试找到对应的 json 文件
    file_path = os.path.join(data_dir, f"{id}.json")
    
    # 打印日志方便调试
    print(f"前端请求读取试卷: {file_path}")
    
    if not os.path.exists(file_path):
        # 如果找不到，尝试一下是不是 id 里已经带了 .json (有时候前端会传错)
        if os.path.exists(file_path.replace(".json.json", ".json")):
             file_path = file_path.replace(".json.json", ".json")
        else:
             raise HTTPException(status_code=404, detail=f"试卷文件不存在: {id}")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"试卷解析失败: {str(e)}")


def _parse_score_from_markdown(text: str) -> tuple:
    """从 Gemini 返回的 Markdown 中尝试解析 得分：X/满分Y 或 得分：X/Y。返回 (score, max_score) 或 (None, None)。"""
    if not text:
        return (None, None)
    # 常见写法：得分：15/20、得分：15/满分20、**得分**：15/20
    m = re.search(r"得分[：:\s]*(\d+)\s*[/／]\s*(?:满分)?\s*(\d+)", text, re.IGNORECASE)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (None, None)


def _fallback_grading_result(model_input: dict, message: str, raw: str) -> dict:
    """Gemini 返回无法解析时，返回前端可用的兜底结构。"""
    questions = model_input.get("questions") or []
    per_question = {}
    total_max = 0
    for q in questions:
        qid = q.get("id") or str(len(per_question) + 1)
        maxs = q.get("maxScore") or 100
        total_max += maxs
        per_question[qid] = {
            "score": 0,
            "maxScore": maxs,
            "deductions": [],
            "referenceAnswer": "（模型未返回有效结果）",
        }
    return {
        "score": 0,
        "maxScore": total_max or 100,
        "overallEvaluation": f"【解析异常】{message}",
        "detailedComments": [],
        "perQuestion": per_question,
        "modelRawOutput": raw or "",
    }


# ---------------------------------------------------------
# 4. 接口：提交 AI 批改 (预留位置)
# ---------------------------------------------------------
@app.post("/api/grade")
def grade_essay(payload: dict):
    print("收到前端提交的答案:", payload)

    # 支持传入 paperId 来从 data 中读取试卷（优先从文件加载，兼容 Render 部署）
    paper = None
    paper_id = payload.get("paperId") or payload.get("id")
    if paper_id:
        paper = _load_paper_by_id(paper_id)
    elif payload.get("user_answer") and not payload.get("answers") and not payload.get("question_id"):
        raise HTTPException(
            status_code=400,
            detail="请求缺少 paperId 和 question_id，无法加载试卷。请重新部署前端（Vercel 等）并刷新页面后再试；前端需传 paperId、question_id、user_answer 或直接传 answers。",
        )

    # 如果前端直接提供了 questions 或 materials，就使用前端的覆盖
    if not paper:
        if payload.get("questions") or payload.get("materials"):
            paper = {
                "id": paper_id or "inline",
                "name": payload.get("paperName", "inline paper"),
                "materials": payload.get("materials", []),
                "questions": payload.get("questions", []),
            }

    # 收集 answers（前端可以只传 question id -> answer 的映射）
    answers = payload.get("answers") or {}
    # 兼容单题提交格式（老格式）
    if not answers and payload.get("question_id") and payload.get("user_answer"):
        answers = { payload.get("question_id"): payload.get("user_answer") }
    # 拍照上传：仅有 answer_images 时也视为有答案，用占位文字满足后续校验
    answer_images: List[str] = payload.get("answer_images") or []
    if answer_images and not answers and payload.get("question_id"):
        answers = { payload.get("question_id"): "（考生上传了作答图片，请根据图片内容批改）" }
    # 或者前端可能发送 question_id(s) 列表（无答案）
    question_ids: List[str] = []
    if answers:
        question_ids = list(answers.keys())
    elif payload.get("question_id"):
        question_ids = [payload.get("question_id")]
    elif payload.get("question_ids"):
        question_ids = payload.get("question_ids")

    # 从 paper 中解析出要发给模型的题目信息（根据 id 匹配）
    questions_for_model: List[Dict[str, Any]] = []
    paper_questions = (paper.get("questions") if paper else []) or []

    def find_question_by_id(qid: str) -> Optional[Dict[str, Any]]:
        for q in paper_questions:
            if not isinstance(q, dict):
                continue
            # 常见的 id 字段名就尝试匹配
            if q.get("id") == qid or q.get("qid") == qid or str(q.get("id")) == str(qid):
                return q
        # 也尝试按索引匹配（用户可能发送 "1" 表示第一题）
        try:
            idx = int(qid) - 1
            if 0 <= idx < len(paper_questions):
                q = paper_questions[idx]
                if isinstance(q, dict):
                    return q
        except Exception:
            pass
        return None

    # 如果没有提供任何 question_ids，但 paper 中有 questions，默认全部批改
    if not question_ids and paper_questions:
        for q in paper_questions:
            if isinstance(q, dict):
                questions_for_model.append(q)
    else:
        for qid in question_ids:
            qobj = find_question_by_id(qid)
            if qobj:
                questions_for_model.append(qobj)
            else:
                # 若试卷中未匹配到，尝试 payload 的 question（单题）或 questions（列表）
                single = payload.get("question")
                if isinstance(single, dict) and (single.get("id") == qid or single.get("qid") == qid):
                    questions_for_model.append(single)
                else:
                    for q in payload.get("questions", []):
                        if isinstance(q, dict) and (q.get("id") == qid or q.get("qid") == qid):
                            questions_for_model.append(q)
                            break

    # 取材料：优先用 payload 中的非空 materials，否则用试卷里的（避免前端传空数组覆盖试卷材料）
    payload_materials = payload.get("materials")
    materials = (payload_materials if payload_materials else (paper.get("materials") if paper else [])) or []
    print(f"[批改] paper_id={paper_id}, paper_loaded={paper is not None}, materials_count={len(materials)}, questions_count={len(questions_for_model)}, answers_keys={list(answers.keys())}")
    if not materials:
        print("警告：材料为空，请检查 data 目录是否有对应试卷 JSON 或前端是否传递 materials")
    # 若材料/题目/答案任一为空，不调用 Gemini，直接返回明确错误（避免模型回复「内容均为空」）
    if not materials or not questions_for_model or not answers:
        detail = []
        if not materials:
            detail.append("材料为空")
        if not questions_for_model:
            detail.append("题目为空")
        if not answers:
            detail.append("答案为空")
        msg = "；".join(detail) + "。请确认：1) 后端 data 目录已部署且含对应试卷 JSON；2) 前端请求带有 paperId 与 answers。"
        raise HTTPException(status_code=400, detail=msg)

    # 根据题目类型与 materialIds 决定发给 Gemini 的材料：大作文发全卷材料，小题只发对应材料
    has_essay = any((q.get("type") or "").upper() == "ESSAY" for q in questions_for_model)
    if has_essay:
        # 大作文必须发全卷材料：优先用后端试卷文件中的完整 materials，避免前端 payload 漏传或截断
        paper_materials = (paper.get("materials") if paper else []) or []
        materials_to_send = list(paper_materials) if paper_materials else list(materials)
        if not materials_to_send and materials:
            materials_to_send = list(materials)
        print(f"[批改] 大作文题，发送材料数: {len(materials_to_send)} (试卷文件: {len(paper_materials)}, payload: {len(materials)})")
    else:
        mid_set = set()
        for q in questions_for_model:
            ids = q.get("materialIds") or q.get("material_ids")
            if ids:
                mid_set.update(ids if isinstance(ids, list) else [ids])
        if mid_set:
            materials_to_send = [m for m in materials if m.get("id") in mid_set]
        else:
            materials_to_send = list(materials)

    # 构造发给模型的简洁上下文（只包含需要的部分）
    model_input = {
        "paperId": paper.get("id") if paper else (paper_id or "unknown"),
        "paperName": paper.get("name") if paper else payload.get("paperName", ""),
        "region": (paper.get("region") if paper else payload.get("region")) or None,
        "materials": materials_to_send,
        "questions": [],
        "answers": answers,
    }

    for q in questions_for_model:
        model_input["questions"].append({
            "id": q.get("id"),
            "title": q.get("title") or q.get("question") or q.get("text") or q.get("stem"),
            "requirements": q.get("requirements") or q.get("要求") or "",
            "maxScore": q.get("maxScore") or q.get("score") or None,
        })

    # 构造 prompt：材料全文发给 Gemini，要求以 Markdown 直接输出（不要求 JSON）
    prompt_lines = []
    if has_essay:
        prompt_lines.append("请以一个资深申论老师的视角，分析这道题目及其材料，给出审题关键点、材料深度解析和作答思路，同时按照本省要求评析用户的答案，评析答案时需要逐段点评，点评好的地方和需要优化的地方，并优化用户作答思路，给出扣分点，并进行打分，然后按照题目要求给出参考答案以及用户的提升建议，同时给出材料的精彩例句，参考答案尽可能使用材料原词。")
    else:
        prompt_lines.append("请以一个资深申论老师的视角，分析这道题目及其材料，给出审题关键点、材料深度解析和作答思路，同时按照本省要求评析用户的答案，并优化用户作答思路，给出扣分点，并进行打分，然后按照题目要求给出参考答案以及用户的提升建议，同时给出材料的精彩例句，参考答案尽可能使用材料原词。")
    region = model_input.get("region")
    if region:
        prompt_lines.append(f"本套试卷的地区（供评分标准参考）：{region}。在评分时，请优先参考该地区公务员申论考试的常见评分要求进行分析。")
    else:
        prompt_lines.append("在评分时，请结合本题材料与一般公务员申论评分逻辑，自行归纳合理的评分尺度。")
    prompt_lines.append("请用 Markdown 格式直接输出你的分析报告（可使用标题、加粗、列表、分段等），不要输出 JSON。报告中请明确写出得分（例如：得分：X/满分Y），便于系统解析。")
    prompt_lines.append("材料（materials）如下（含完整正文，请依据材料原文评分、给出参考答案与扣分点）：")
    prompt_lines.append(json.dumps(materials_to_send, ensure_ascii=False))
    prompt_lines.append("\n题目（questions）如下（每题包含 id、title、requirements、maxScore）：")
    prompt_lines.append(json.dumps(model_input["questions"], ensure_ascii=False))
    if answer_images:
        prompt_lines.append("\n学生答案以图片形式提供，下方有多张图片，请将全部图片均视为同一道题的作答内容，按顺序识别并综合批改。若同时有文字答案则见下方。")
        prompt_lines.append("【图片字数判定规则】根据图片估算字数时，按每行约 25 字计算。若题目有字数要求，而你估算的字数与要求相差超过 30%（过多或过少），则视为字数合适、不扣字数分，并在报告中说明为字数判断误差，不因此扣分。")
        if answers and not (list(answers.values())[0] or "").strip().startswith("（考生上传了作答图片"):
            prompt_lines.append("学生答案（文字补充）：")
            prompt_lines.append(json.dumps(answers, ensure_ascii=False))
    else:
        prompt_lines.append("\n学生答案（answers，键为题目id）：")
        prompt_lines.append(json.dumps(answers, ensure_ascii=False))
    prompt_lines.append("\n请按上述要求，直接输出完整的 Markdown 分析报告。")
    prompt = "\n".join(prompt_lines)

    # 有图片时走多模态接口，否则仅文本
    gemini_raw = call_gemini_system_with_images(prompt, answer_images) if answer_images else call_gemini_system(prompt)
    if gemini_raw:
        body = gemini_raw.strip()
        if not body:
            print("Gemini 返回为空文本")
            return _fallback_grading_result(model_input, "模型未返回内容（可能被截断或安全过滤）", gemini_raw)

        # 不再解析 JSON，直接返回 Markdown 全文；尝试从正文中解析得分供前端列表展示
        score, max_score = _parse_score_from_markdown(body)
        if max_score is None:
            total_max = sum((q.get("maxScore") or 100) for q in (model_input.get("questions") or []))
            max_score = total_max if total_max else 100
        return {
            "content": body,
            "modelRawOutput": body,
            "score": score if score is not None else 0,
            "maxScore": max_score,
            "overallEvaluation": "",
            "detailedComments": [],
            "perQuestion": {},
            "modelAnswer": "",
        }

    # 如果没有可用的 Gemini，则走模拟逻辑：根据 answers 生成每题评分
    # 简单模拟：每题默认分值 100/题数，若有 maxScore 则按 maxScore 分配
    per_question = {}
    total_max = 0
    for q in model_input["questions"]:
        m = q.get("maxScore")
        if m:
            total_max += m
        else:
            total_max += 100

    # 若没有题目信息（paper.questions 为空），则根据 answers 的键生成占位项
    if not model_input["questions"] and answers:
        for idx, qid in enumerate(answers.keys(), start=1):
            per_question[qid] = {
                "score": 80,
                "maxScore": 100,
                "deductions": [{"point": "内容不够具体", "deduct": 20}],
                "referenceAnswer": "（该试卷未提供题目文本，按学生答案生成的模拟参考）",
            }
        return {
            "score": sum(item["score"] for item in per_question.values()),
            "maxScore": len(per_question) * 100,
            "overallEvaluation": "【后端模拟评分】试卷无题目正文，已根据提交的 answers 生成模拟分项。",
            "perQuestion": per_question,
            "detailedComments": [],
        }

    # 普通模拟：按题目逐项生成占位点评
    for q in model_input["questions"]:
        qid = q.get("id") or str(len(per_question) + 1)
        maxs = q.get("maxScore") or 100
        ans = answers.get(qid, "")
        # 简单启发：如果有答案长度 > 50 视为得分较高
        score = int(maxs * (0.8 if len(str(ans)) > 50 else 0.6))
        per_question[qid] = {
            "score": score,
            "maxScore": maxs,
            "deductions": [{"point": "论证不够丰满", "deduct": max(1, int(maxs * 0.2))}],
            "referenceAnswer": f"（模拟参考答案，基于题目 {q.get('title')}）",
        }

    return {
        "score": sum(v["score"] for v in per_question.values()),
        "maxScore": sum(v["maxScore"] for v in per_question.values()),
        "overallEvaluation": "【后端模拟评分】这是一个自动生成的模拟结果，用于在未配置 Gemini 时的占位。",
        "perQuestion": per_question,
        "detailedComments": [],
    }


def _parse_data_url(data_url: str) -> tuple:
    """从 data URL 解析出 mime_type 和 base64 字符串。返回 (mime_type, base64_str)，无法解析时返回 (None, None)。"""
    if not data_url or not isinstance(data_url, str):
        return (None, None)
    s = data_url.strip()
    if s.startswith("data:"):
        # data:image/jpeg;base64,xxxx
        idx = s.find(",")
        if idx == -1:
            return (None, None)
        header = s[5:idx].strip()
        payload = s[idx + 1 :].strip()
        mime = "image/jpeg"
        if ";" in header:
            mime = header.split(";")[0].strip().lower() or mime
        return (mime, payload)
    # 已是纯 base64
    return ("image/jpeg", s)


def call_gemini_system_with_images(prompt: str, image_data_list: List[str]) -> Optional[str]:
    """带图片的多模态调用 Gemini，image_data_list 为 data URL 或 base64 字符串列表。"""
    api_key = os.getenv("GEMINI_API_KEY")
    base_endpoint = os.getenv("GEMINI_ENDPOINT", "https://generativelanguage.googleapis.com")
    if not api_key:
        print("GEMINI not configured (GEMINI_API_KEY missing)")
        return None
    model_name = "gemini-3-flash-preview"
    url = base_endpoint.rstrip("/") + f"/v1beta/models/{model_name}:generateContent?key={api_key}"

    parts: List[Dict[str, Any]] = [{"text": prompt}]
    for data_url in image_data_list:
        mime, b64 = _parse_data_url(data_url)
        if not b64:
            continue
        parts.append({
            "inlineData": {
                "mimeType": mime or "image/jpeg",
                "data": b64,
            }
        })
    if len(parts) <= 1:
        return call_gemini_system(prompt)

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 4096},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
            if not raw or not raw.strip():
                print("Gemini API 返回空 body")
                return None
            try:
                obj = json.loads(raw)
            except Exception:
                return raw
            if obj.get("error"):
                print("Gemini API 错误:", obj.get("error"))
                return None
            candidates = obj.get("candidates") or []
            if not candidates:
                print("Gemini API 无 candidates")
                return None
            first = candidates[0] or {}
            content = first.get("content") or {}
            texts = []
            for p in content.get("parts") or []:
                if isinstance(p, dict) and "text" in p:
                    texts.append(p["text"])
            merged = "\n".join(texts).strip()
            return merged if merged else None
    except Exception as e:
        print("call_gemini_system_with_images failed:", e)
        return None


def call_gemini_system(prompt: str) -> Optional[str]:
    """尝试调用 Google Gemini 接口，返回模型生成的文本（或 None 表示未调用/失败）。"""
    api_key = os.getenv("GEMINI_API_KEY")
    # 对于 Google AI Studio，推荐使用 https://generativelanguage.googleapis.com 作为基础地址
    base_endpoint = os.getenv("GEMINI_ENDPOINT", "https://generativelanguage.googleapis.com")
    if not api_key:
        print("GEMINI not configured (GEMINI_API_KEY missing)")
        return None

    # 这里按照 Google AI Studio 的 REST API 规范调用 Gemini 3 Pro（当前为 preview 模型）
    # 文档地址可参考：https://ai.google.dev/gemini-api/docs
    # 如果后续正式版 model name 有变，可以只改下面这一行。
    model_name = "gemini-3-flash-preview"
    url = base_endpoint.rstrip('/') + f"/v1beta/models/{model_name}:generateContent?key={api_key}"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 4096,
        },
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            if not raw or not raw.strip():
                print("Gemini API 返回空 body")
                return None
            try:
                obj = json.loads(raw)
            except Exception:
                return raw

            if obj.get("error"):
                print("Gemini API 错误:", obj.get("error"))
                return None

            candidates = obj.get("candidates") or []
            if not candidates:
                print("Gemini API 无 candidates，原始响应:", raw[:500])
                return None

            first = candidates[0] or {}
            content = first.get("content") or {}
            parts = content.get("parts") or []
            texts = []
            for p in parts:
                if isinstance(p, dict) and "text" in p:
                    texts.append(p["text"])
            merged = "\n".join(texts).strip()
            if not merged:
                print("Gemini 候选内容无文本，可能被安全过滤。finishReason:", first.get("finishReason"))
                return None
            return merged
    except Exception as e:
        print("call_gemini_system failed:", e)
        return None