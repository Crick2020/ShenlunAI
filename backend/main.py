from datetime import date, datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import hashlib
import json
import os
import re
import threading
import time
from zoneinfo import ZoneInfo
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any
from collections import Counter
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from stats_db import record_submit, get_stats





def _get_client_ip(request: Request) -> Optional[str]:
    """从请求中取客户端 IP（兼容代理 X-Forwarded-For）。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip() or None
    if request.client:
        return getattr(request.client, "host", None)
    return None


def _record_submit_stat(is_essay: bool, client_ip: Optional[str] = None) -> None:
    """记录一次提交：小题或大作文，按天统计并记录当日用户 IP（用于每日用户量）。"""
    record_submit(is_essay, client_ip)

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=500)

_papers_index: list = []
_papers_cache: Dict[str, dict] = {}
_papers_json_cache: Dict[str, bytes] = {}
_papers_index_json: bytes = b"[]"
_papers_index_etag: str = '"empty"'

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


def get_data_dir():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, "data")


def _sort_key(p):
    region = p.get("region", "全国")
    year = p.get("year", 0)
    region_order = (0 if region == "全国" else 1, region)
    return (region_order, -year)


def _build_index():
    """遍历 data 目录，将所有试卷加载到内存，构建排好序的索引列表。"""
    global _papers_index, _papers_cache, _papers_json_cache, _papers_index_json, _papers_index_etag
    data_dir = get_data_dir()
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        _papers_index = []
        _papers_cache = {}
        _papers_json_cache = {}
        _papers_index_json = b"[]"
        _papers_index_etag = '"empty"'
        return

    papers = []
    cache: Dict[str, dict] = {}
    json_cache: Dict[str, bytes] = {}
    for filename in os.listdir(data_dir):
        if not filename.endswith(".json"):
            continue
        file_path = os.path.join(data_dir, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = json.load(f)
            pid = content.get("id", filename[:-5])
            cache[pid] = content
            json_cache[pid] = json.dumps(content, ensure_ascii=False).encode("utf-8")
            papers.append({
                "id": pid,
                "name": content.get("name", "未命名试卷"),
                "year": content.get("year", 2024),
                "region": content.get("region", "全国"),
                "examType": content.get("examType", "公务员"),
            })
        except Exception as e:
            print(f"读取文件 {filename} 出错: {e}")

    papers.sort(key=_sort_key)
    _papers_index = papers
    _papers_cache = cache
    _papers_json_cache = json_cache
    _papers_index_json = json.dumps(papers, ensure_ascii=False).encode("utf-8")
    _papers_index_etag = f'"{hashlib.md5(_papers_index_json).hexdigest()}"'
    by_type = Counter((p.get("examType") or "未标注") for p in papers)
    type_line = "，".join(f"{k} {v}份" for k, v in sorted(by_type.items(), key=lambda x: (-x[1], x[0])))
    print(f"[Startup] 已加载 {len(papers)} 份试卷到内存缓存, index_size={len(_papers_index_json)} bytes, etag={_papers_index_etag}")
    print(f"[Startup] 按考试类型: {type_line}")


@app.on_event("startup")
def startup_load():
    """启动时预加载所有试卷到内存，后续请求零磁盘 I/O。"""
    data_dir = get_data_dir()
    exists = os.path.isdir(data_dir)
    print(f"[Startup] data_dir={data_dir}, exists={exists}, cwd={os.getcwd()}")
    _build_index()


def _load_paper_by_id(paper_id: str):
    """优先从内存缓存读取试卷，缓存未命中时回退到磁盘读取。"""
    if paper_id in _papers_cache:
        return _papers_cache[paper_id]
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
def list_papers(request: Request):
    if_none_match = request.headers.get("if-none-match", "")
    if if_none_match == _papers_index_etag:
        return Response(
            status_code=304,
            headers={
                "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400",
                "ETag": _papers_index_etag,
            },
        )
    return Response(
        content=_papers_index_json,
        media_type="application/json",
        headers={
            "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400",
            "ETag": _papers_index_etag,
        },
    )


# ---------------------------------------------------------
# 3. 接口：获取单份试卷详情 (用于做题页面)
# 调用示例：/api/paper?id=gwy_jiangsu_2024_A
# ---------------------------------------------------------
@app.get("/api/paper")
def get_paper(id: str):
    paper_id = id.replace(".json", "") if id.endswith(".json") else id
    _cache_headers = {"Cache-Control": "public, max-age=31536000, immutable"}

    if paper_id in _papers_json_cache:
        return Response(
            content=_papers_json_cache[paper_id],
            media_type="application/json",
            headers=_cache_headers,
        )

    data_dir = get_data_dir()
    file_path = os.path.join(data_dir, f"{paper_id}.json")
    print(f"前端请求读取试卷(缓存未命中): {file_path}")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"试卷文件不存在: {id}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(content=data, headers=_cache_headers)
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
# 3.1 提交统计（按天：用户量、小题/大作文提交量）
# ---------------------------------------------------------
@app.get("/api/stats/submit")
def get_submit_stats():
    """返回按天统计：每日用户量（按 IP 去重）、小题提交量、大作文提交量；以及累计总量。"""
    return get_stats()


# ---------------------------------------------------------
# 4. 接口：提交 AI 批改 (预留位置)
# ---------------------------------------------------------
@app.post("/api/grade")
def grade_essay(request: Request, payload: dict):
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
    has_images_flag = bool(payload.get("has_images"))
    img_sizes = [len(img) for img in answer_images] if answer_images else []
    print(f"[批改] has_images_flag={has_images_flag}, answer_images_count={len(answer_images)}, img_sizes_chars={img_sizes}")
    if has_images_flag and not answer_images:
        raise HTTPException(
            status_code=400,
            detail="前端标记有图片但未收到图片数据，请稍等图片加载完成（约 1～2 秒）后再点击提交。",
        )
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
        # 小题：只发本题对应的材料。materialIds 从试卷题目 + 前端 payload 两处合并，避免试卷缺字段时误发全卷
        mid_set = set()
        for q in questions_for_model:
            ids = q.get("materialIds") or q.get("material_ids")
            if ids:
                mid_set.update(ids if isinstance(ids, list) else [ids])
        # 兼容前端单题提交：payload 里的 question / questions 也可能带有 materialIds，一并纳入
        single_q = payload.get("question")
        if isinstance(single_q, dict):
            ids = single_q.get("materialIds") or single_q.get("material_ids")
            if ids:
                mid_set.update(ids if isinstance(ids, list) else [ids])
        for q in payload.get("questions") or []:
            if isinstance(q, dict):
                ids = q.get("materialIds") or q.get("material_ids")
                if ids:
                    mid_set.update(ids if isinstance(ids, list) else [ids])
        if mid_set:
            materials_to_send = [m for m in materials if m.get("id") in mid_set]
            sent_ids = [m.get("id") for m in materials_to_send]
            print(f"[批改] 小题，按 materialIds 筛选：题目指定 {sorted(mid_set)}，实际发送材料 id={sent_ids}，共 {len(materials_to_send)} 份")
            if not materials_to_send and materials:
                print(f"[批改] 警告：题目指定了 materialIds {sorted(mid_set)}，但当前材料列表的 id 为 {[m.get('id') for m in materials]}，无匹配项；将发送 0 份材料，可能影响批改")
        else:
            # 未找到任何 materialIds 时才回退为全卷（并打日志便于排查）
            materials_to_send = list(materials)
            print(f"[批改] 小题，未找到 materialIds（题目或 payload 均无），回退发送全卷材料共 {len(materials_to_send)} 份；建议在试卷 JSON 或前端传题时补充 materialIds")

    # 后端自统计：按天记录小题/大作文提交量及当日用户 IP（用于每日用户量）
    try:
        _record_submit_stat(has_essay, _get_client_ip(request))
    except Exception as e:
        print(f"[统计] 写入提交次数失败: {e}")

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

    # 大作文批改系统提示词（Role + Workflow + Output Constraints）
    ESSAY_GRADING_INSTRUCTION = """Role: 资深申论阅卷组长 & 文章写作金牌讲师
你拥有10年以上的申论大作文阅卷与教学经验。你现在的任务是为考生的大作文提供极其严苛、深度、专业的批改与升格指导。

Workflow (请严格按照以下模块顺序输出)：

模块一：【名师审题与材料透视】（不看用户答案，先定标准）
破题与立意界定：一语道破本题的核心主题词是什么？核心矛盾或探讨的方向是什么？明确本文应写成"政论文"还是"策论文"或"二者兼顾"。
材料素材图谱： 以你的视角，分析如何从材料中提炼出总论点和分论点。请清晰列出：
提取总论点的材料依据是：[具体材料及分析]
提取分论点1、2、3的材料依据分别是：[具体材料及提炼逻辑]

模块二：【用户立意与骨架诊断】（核心判卷逻辑）
对用户答案进行"脱水分析"，提取其文章骨架，并给出致命诊断：
用户拟定标题：[提取用户标题]
用户总论点：[提取用户总论点，若没有明确总论点请严厉指出]
用户分论点：[提取文章中的几个分论点/核心对策]
⚠️ 立意判定结论：根据标准，明确判定该考生的立意属于：精准契合 / 基本切题 / 严重跑题，并一针见血地指出跑偏在哪里，或者哪里概括得不够深刻。

模块三：【多维度评分】（依据省考标准）
结合材料与题目，给出总分。按以下维度拆解打分及扣分点：
立意与思想：是否深刻？是否紧扣主题？（扣分点：…）
结构与逻辑：总分总结构是否完整？分论点之间是并列、递进还是逻辑混乱？（扣分点：…）
内容与论证：是否有效使用了材料原词、案例进行理证/例证？还是在空洞说教/大段抄写材料？（扣分点：…）
语言与规范：语言是否有"体制内"的政治高度？标题是否醒目？首尾是否呼应？**字数一律视为符合规定，不识别、不因字数扣分。**（扣分点：…）

模块四：【逐段精批与升格示范】（手把手教学）
对用户答案进行逐段点评，必须包含"亮点"、"痛点"和"升格示范"：
标题批改：点评用户标题。并额外提供 3个高分神仙标题 供用户参考（要求：对仗工整、包含主题词、有文学性或政治高度）。
第一段（开头/引论）：
🔍 痛点诊断：引题是否拖沓？有没有在第一段明确亮出总论点？
🔄 升格示范：保留原意，用排比或名言警句帮他重写一个"凤头"。
- **中间段落（本论/分论点段）【重点批改区域】：**
  必须对用户的**每一个**分论点段落（主体段）进行**逐段拆解与逐句精批**。若有三个分论点段落，请循环以下格式三次：
  - 📍 **【主体段落 X（第X段）】**：
    - 🎯 **段旨/分论点判定**：该段首句（分论点）是否紧扣总论点？语言是否精炼、句式是否规范对仗？（若不合格，请直接给出1个修改后的标准分论点金句）。
    - 🔍 **论证逻辑X光诊断**：按照申论标准段落结构（“分论点+过渡阐释+材料例证+逻辑分析+回扣段旨”）对本段进行解剖。明确指出缺失了哪一环？（例如：是否变成了大段抄材料？是否有例无证？过渡是否生硬？）
    - ✍️ **语病与弱句精修（划线句批改）**：精准摘录本段中**口语化严重、逻辑断层、或是无效堆砌废话**的1-2个具体原句，并直接给出**“政务化、书面化”的润色修改**。（格式：原句“...” -> 修改为“...”）
    - 🔄 **本段高分重塑（满分段落升格）**：保留用户原本想表达的核心思路和论据，用标准、高级的申论阅卷标准，将这一整段**彻底重写一遍**，向用户展示如何做到“夹叙夹议、深刻有力”。
  *(⚠️注：请严格遍历用户的所有主体段落，绝不可跳过或合并点评！)*
结尾段（结论）：
🔍 痛点诊断：是否做到了首尾呼应和情感升华？是否强行喊口号？
🔄 升格示范：重写一个简洁有力、意蕴悠长的"豹尾"。

模块五：【标杆范文与金句积累】（最终交付）
标杆范文：由你亲自撰写一篇符合题目要求、最大程度化用"材料原词"和"材料案例"的高分满分范文。（要求：分段清晰，使用小标题或对仗分论点，字数严格符合题目限制）。
范文解析：简单点拨你的范文中，哪些词句是直接从哪个材料中"化用"过来的，教导用户如何"抄材料而不像抄材料"。
金句积累：给出与本题主题高度相关的 3 句名言警句或官方重要论述，供用户背诵。

Output Constraints:
语气：专业、权威，像一位严格但倾囊相授的体制内笔杆子。
格式：全文使用Markdown格式输出，重点词汇加粗。
禁忌：严禁AI自己凭空捏造与给定材料毫无关联的论点。所有的论点升华必须建立在给定材料的基础之上。
"""

    # 小题批改系统提示词（Role + Input Data 说明 + Workflow + Output Constraints）
    SMALL_QUESTION_GRADING_INSTRUCTION = """# Role: 资深申论阅卷组长 & 客观题金牌讲师
你拥有10年以上的申论阅卷与教学经验。深谙各省公务员考试申论小题（概括题、分析题、提出对策题）"按点给分、见词给分、极度依赖材料原词"的阅卷规则。你的任务是像导师一样手把手教考生如何分析材料，并对考生的答案进行X光级别的优缺点诊断与升格指导。

# Input Data
- <省份及题型>：[传入数据，如：国考副省级-单一概括题]
- <给定材料>：[传入材料文本]
- <题目及字数限制>：[传入具体题目和字数要求，如：不超过200字]
- <系统统计字数>：[传入系统计算的字数，如：185字]
- <用户作答>：[传入用户的答案文本]

# Workflow (请严格按照以下模块顺序输出)：

## 模块一：【审题关键点与材料深度解析】（授人以渔）
1. **审题关键点（破题雷达）**：一语道破本题的"作答对象"（找问题/原因/做法/意义？）、"限制条件"（字数、特定身份、范围）以及"隐含要求"（如：是否需要分类梳理？）。
2. **材料深度解析（如何找原词）**：以名师视角，带领用户梳理材料逻辑。请按逻辑块演示推导过程：
   - 🔍 **材料X-X段**：主要讲了什么事情？从中可以抓取哪些"核心原词"？如何剥离具体的案例、数据等废话，将长句转化为精炼的"踩分关键词"？
3. **作答思路构建（如何排版）**：找齐要点后，告诉用户这些点应该如何组织。是按"主观/客观"分类？还是按"主体"分类？给出建议的作答框架和总括句。

## 模块二：【官方"踩分点"标尺设定】（确立评分标准）
基于上述解析，生成本题的标准"踩分要点"（假设本题总分为20分）。必须清晰列出：
- **要点一（占比X分）**：[主旨概括句]。踩分原词：[必须是材料中出现的关键词A]、[关键词B]、[可接受的同义词]。
- **要点二（占比X分）**：[主旨概括句]。踩分原词：[必须是材料中出现的关键词C]、[关键词D]、[可接受的同义词]。
*(注：必须展示合并分类后的要点结构，揭示阅卷人手里的真实标准)*

## 模块三：【用户作答精准评析】（核心诊断区）
*(⚠️注意：严禁复述用户完整答案，请使用 `> 摘录用户原句` 的形式进行局部点评)*
将<用户作答>与标尺进行严格比对，直击痛点：
1. ✨ **作答优点（得分亮点）**：
   - **原词命中**：明确表扬用户精准保留了材料中的哪些"核心原词/踩分词"。
   - **结构与逻辑**：如果用户做了同类项合并、分条作答（1.2.3.），请予以肯定。
2. ❌ **作答缺点（失分痛点）**：
   - **致命漏点**：明确指出用户漏掉了哪个重要要点，并点拨他"这个词在材料的哪里，你是怎么看漏的"。
   - **逻辑混乱/未分类**：指出答案是否存在要点交叉重叠、未做归纳等问题。
3. 🔄 **"去水存干"压缩示范（保原词微操）**：
   - 申论小题重在"原词踩分"，格子极其宝贵。挑选用户答案中大段抄写材料具体细节、举例或修饰语过多的一句话进行靶向修改。
   - 要求：在**绝对保留材料核心"原词/踩分词"**的前提下，示范如何删去废话，提炼主干。
   - 🔴 **用户的啰嗦原句**：> [摘录原句] (占XX字)
   - 🟢 **名师去水存干版**：**[仅保留材料原词与核心主谓宾的极简短语]** (仅占XX字，点评说明删掉了哪些不给分的废话)

## 模块四：【多维度打分与卷面定级】
结合<省份及题型>和<系统统计字数>，给出总分，并进行分项：
- **要点分（70%）**：核心原词踩中率评估。（得分/总分）
- **归纳逻辑分（20%）**：是否分类合理、条理清晰。（得分/总分）
- **字数及格式（10%）**：字数是否在限制内？格式是否规范？（得分/总分）

## 模块五：【满分标杆与积累提升】（最终交付）
1. **极致参考答案**：给出一份符合题目要求、结构清晰（使用序号如一、二、三，且具备"核心主旨句+具体表现"结构）的满分参考答案。要求：**最大密度地使用"材料原词"进行拼接，绝不随意替换为材料中没有的词汇**，字数绝对不可超限。
2. **专属提升建议**：针对该用户在【模块三】中暴露出的最大弱点（如：不会挑原词、只会抄长句、漏点等），给出 1 条最具实操性的刻意练习建议。

# Output Constraints:
- 语气：专业、严厉但循循善诱，像一位极具责任心的考前辅导名师。
- 排版：全程使用Markdown格式，利用加粗、表情符号（🔍/✨/❌/🔄等）和引用块（>）增加易读性。
- 禁忌：严禁AI在小题中自行发散联想、过度拔高或替换词汇。所有的采分点必须100%忠于<给定材料>的原始表述（去除修饰语后的核心名词/动词）。
- 报告中请明确写出得分（例如：得分：X/满分Y），便于系统解析。
"""

    # 每次批改均为独立任务，不复用任何历史对话；在 prompt 首行明确要求仅根据本次请求内容批改
    grading_session_id = payload.get("gradingSessionId") or ("req-%s" % int(time.time() * 1000))
    print("[批改] 新对话/独立任务 session=%s" % grading_session_id)

    # 构造 prompt：材料全文发给 Gemini，要求以 Markdown 直接输出（不要求 JSON）
    prompt_lines = []
    prompt_lines.append("【重要】本次为全新、独立的批改任务。请仅根据本请求下方提供的「材料」「题目」与「学生答案」进行批改，勿参考、勿引用任何其他对话或历史内容。")
    if has_essay:
        prompt_lines.append(ESSAY_GRADING_INSTRUCTION)
    else:
        prompt_lines.append(SMALL_QUESTION_GRADING_INSTRUCTION)
    region = model_input.get("region")
    if region:
        prompt_lines.append(f"本套试卷的地区（供评分标准参考）：{region}。在评分时，请优先参考该地区公务员申论考试的常见评分要求进行分析。")
    else:
        prompt_lines.append("在评分时，请结合本题材料与一般公务员申论评分逻辑，自行归纳合理的评分尺度。")
    prompt_lines.append("请用 Markdown 格式直接输出你的分析报告（可使用标题、加粗、列表、分段等），不要输出 JSON。加粗请使用成对的 **文字**，确保每行内 ** 成对闭合，避免漏写导致前端渲染不全。报告中请明确写出得分（例如：得分：X/满分Y），便于系统解析。")
    prompt_lines.append("材料（materials）如下（含完整正文，请依据材料原文评分、给出参考答案与扣分点）：")
    prompt_lines.append(json.dumps(materials_to_send, ensure_ascii=False))
    prompt_lines.append("\n题目（questions）如下（每题包含 id、title、requirements、maxScore）：")
    prompt_lines.append(json.dumps(model_input["questions"], ensure_ascii=False))
    if answer_images:
        prompt_lines.append("\n学生答案以图片形式提供，下方有多张图片，请将全部图片均视为同一道题的作答内容，按顺序识别并综合批改。若同时有文字答案则见下方。")
        if has_essay:
            prompt_lines.append("【大作文字数说明】大作文不识别、不判定字数，一律视为字数符合规定，不因字数扣分。")
        else:
            prompt_lines.append("【图片字数判定规则】每行固定为 25 字，总字数=行数*25。若题目有字数要求，而据此估算的总字数与要求相差超过 20%（过多或过少），则视为字数合适、不扣字数分。")
        if answers and not (list(answers.values())[0] or "").strip().startswith("（考生上传了作答图片"):
            prompt_lines.append("学生答案（文字补充）：")
            prompt_lines.append(json.dumps(answers, ensure_ascii=False))
    else:
        prompt_lines.append("\n学生答案（answers，键为题目id）：")
        prompt_lines.append(json.dumps(answers, ensure_ascii=False))
    prompt_lines.append("\n请按上述要求，直接输出完整的 Markdown 分析报告。")
    prompt = "\n".join(prompt_lines)

    # 小题 temperature=0.15 / top_p=0.85，大作文 temperature=0.3 / top_p=0.90
    temperature = 0.15 if not has_essay else 0.3
    top_p = 0.85 if not has_essay else 0.90
    # 有图片时走多模态接口，否则仅文本；Gemini 失败时先尝试钱多多多模态兜底
    if answer_images:
        gemini_raw = call_gemini_system_with_images(prompt, answer_images, temperature=temperature, top_p=top_p)
        if not gemini_raw:
            # 兜底：尝试钱多多多模态（OpenAI 兼容格式支持图片）
            print("[批改] Gemini 多模态失败，尝试钱多多多模态兜底...")
            gemini_raw = call_qianduoduo_gemini_with_images(prompt, answer_images, temperature=temperature, top_p=top_p)
            if not gemini_raw:
                print("[批改] 钱多多多模态也失败，返回 503")
                raise HTTPException(
                    status_code=503,
                    detail="图片批改服务暂时不可用。请稍后重试，或减少图片数量、改用文字作答后再提交。",
                )
    else:
        gemini_raw = call_gemini_system(prompt, temperature=temperature, top_p=top_p)
        if not gemini_raw:
            print("[批改] Google Gemini 无结果，尝试钱多多平台...")
            gemini_raw = call_qianduoduo_gemini(prompt, temperature=temperature, top_p=top_p)
    if gemini_raw:
        body = gemini_raw.strip()
        # Render 日志：输出 AI 批改结果（便于排查与审计）
        print("[AI批改输出] 长度:", len(body))
        if len(body) <= 5000:
            print("[AI批改输出]", body)
        else:
            print("[AI批改输出]", body[:5000])
            print("[AI批改输出] ... (已截断，总长 %d 字符)" % len(body))
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


def _get_gemini_api_keys() -> List[str]:
    """返回 Gemini API Key 列表：优先新账号(GEMINI_API_KEY)，其次老账号(GEMINI_API_KEY_FALLBACK)。"""
    keys: List[str] = []
    primary = (os.getenv("GEMINI_API_KEY") or "").strip()
    if primary:
        keys.append(primary)
    fallback = (os.getenv("GEMINI_API_KEY_FALLBACK") or "").strip()
    if fallback and fallback != primary:
        keys.append(fallback)
    return keys


_gemini_disabled_until: Optional[float] = None
_gemini_disabled_lock = threading.Lock()


def _is_gemini_temporarily_disabled() -> bool:
    """是否处于“额度已用完”的临时禁用窗口内。"""
    global _gemini_disabled_until
    with _gemini_disabled_lock:
        if not _gemini_disabled_until:
            return False
        now = time.time()
        if now >= _gemini_disabled_until:
            # 冷却期已过，自动恢复
            _gemini_disabled_until = None
            return False
        return True


def _mark_gemini_quota_exhausted():
    """当所有 Gemini Key 都返回额度/限流错误时，禁用至“下一次太平洋时间 0 点”或指定冷却期。"""
    global _gemini_disabled_until

    # 如果显式配置了 GEMINI_COOLDOWN_SECONDS，则优先生效（兼容自定义需求）
    cooldown_env = os.getenv("GEMINI_COOLDOWN_SECONDS")
    if cooldown_env:
        try:
            cooldown = int(cooldown_env)
        except Exception:
            cooldown = 0
        if cooldown > 0:
            with _gemini_disabled_lock:
                _gemini_disabled_until = time.time() + cooldown
            return

    # 否则按需求：禁用到“下一次太平洋时间（PT）0 点”
    try:
        now_utc = datetime.now(timezone.utc)
        pt_tz = ZoneInfo("America/Los_Angeles")
        now_pt = now_utc.astimezone(pt_tz)
        next_midnight_pt = (now_pt + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        next_midnight_utc = next_midnight_pt.astimezone(timezone.utc)
        disabled_until_ts = next_midnight_utc.timestamp()
    except Exception as e:
        # 如果计算 PT 时间失败，则退回到一个保守的 24 小时冷却
        print("计算 Gemini 冷却至 PT 午夜失败，退回 24 小时冷却:", e)
        disabled_until_ts = time.time() + 24 * 3600

    with _gemini_disabled_lock:
        _gemini_disabled_until = disabled_until_ts


def call_qianduoduo_gemini(
    prompt: str,
    content_parts: Optional[List[Any]] = None,
    *,
    temperature: float = 0.3,
    top_p: float = 0.9,
) -> Optional[str]:
    """通过钱多多平台（OpenAI 兼容格式）调用 Gemini 模型。
    支持纯文本或多模态（文本+图片，content_parts 为 OpenAI content 数组）。
    环境变量：
      QIANDUODUO_API_KEY  - 钱多多后台生成的 sk-xxx 令牌（必填）
      QIANDUODUO_ENDPOINT - API Base URL，默认 https://ob6nfbpu76.apifox.cn（可选）
      QIANDUODUO_MODEL    - 模型名称，默认 gemini-2.5-flash（可选）
    """
    api_key = (os.getenv("QIANDUODUO_API_KEY") or "").strip()
    if not api_key:
        print("钱多多未配置 (QIANDUODUO_API_KEY 缺失)")
        return None

    base_endpoint = (os.getenv("QIANDUODUO_ENDPOINT") or "").strip().rstrip("/")
    if not base_endpoint:
        print("钱多多未配置 (QIANDUODUO_ENDPOINT 缺失)")
        return None

    model_name = (os.getenv("QIANDUODUO_MODEL") or "gemini-2.5-flash").strip()

    url = base_endpoint + "/v1/chat/completions"
    if content_parts:
        content = content_parts
    else:
        content = prompt
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": content}],
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": 65536,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            if not raw or not raw.strip():
                print("钱多多 API 返回空 body")
                return None
            try:
                obj = json.loads(raw)
            except Exception:
                return raw
            err = obj.get("error")
            if err:
                print("钱多多 API 错误:", err)
                return None
            choices = obj.get("choices") or []
            if not choices:
                print("钱多多 API 无 choices")
                return None
            message = (choices[0] or {}).get("message") or {}
            content = (message.get("content") or "").strip()
            return content if content else None
    except urllib.error.HTTPError as e:
        print("call_qianduoduo_gemini HTTPError:", e.code, e.reason)
        return None
    except Exception as e:
        print("call_qianduoduo_gemini failed:", e)
        return None


def _build_openai_content_parts(prompt: str, image_data_list: List[str]) -> List[Dict[str, Any]]:
    """把 prompt 文本与 data URL 列表转成 OpenAI 多模态 content 数组。"""
    parts: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    for data_url in image_data_list:
        mime, b64 = _parse_data_url(data_url)
        if not b64:
            continue
        parts.append({
            "type": "image_url",
            "image_url": {"url": data_url},
        })
    return parts


def call_qianduoduo_gemini_with_images(
    prompt: str,
    image_data_list: List[str],
    *,
    temperature: float = 0.3,
    top_p: float = 0.9,
) -> Optional[str]:
    """钱多多多模态调用（OpenAI 兼容格式，content 为 parts 数组）。"""
    parts = _build_openai_content_parts(prompt, image_data_list)
    if len(parts) <= 1:
        return None
    return call_qianduoduo_gemini(prompt, content_parts=parts, temperature=temperature, top_p=top_p)


def _is_quota_or_rate_limit_error(http_code: Optional[int], error_obj: Optional[dict]) -> bool:
    """判断是否为配额/限流错误，可切换备用 Key 重试。"""
    if http_code == 429:
        return True
    if not error_obj:
        return False
    code = error_obj.get("code")
    status = (error_obj.get("status") or "").upper()
    return code == 429 or status == "RESOURCE_EXHAUSTED" or "RESOURCE_EXHAUSTED" in status


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


def call_gemini_system_with_images(
    prompt: str,
    image_data_list: List[str],
    *,
    temperature: float = 0.3,
    top_p: float = 0.9,
) -> Optional[str]:
    """带图片的多模态调用 Gemini；优先主 Key，遇限流/配额用备用 Key 重试；若所有 Key 都额度用完，则进入冷却期。"""
    if _is_gemini_temporarily_disabled():
        print("Gemini 已标记为额度用完（多模态），当前请求直接跳过 Gemini。")
        return None
    api_keys = _get_gemini_api_keys()
    if not api_keys:
        print("GEMINI not configured (GEMINI_API_KEY missing)")
        return None
    base_endpoint = os.getenv("GEMINI_ENDPOINT", "https://generativelanguage.googleapis.com")
    model_name = "gemini-3-flash-preview"

    parts: List[Dict[str, Any]] = [{"text": prompt}]
    parsed_count = 0
    for i, data_url in enumerate(image_data_list):
        mime, b64 = _parse_data_url(data_url)
        if not b64:
            print(f"[多模态] 第{i+1}张图片解析失败，data_url前50字符: {(data_url or '')[:50]}")
            continue
        parsed_count += 1
        print(f"[多模态] 第{i+1}张图片解析成功, mime={mime}, base64长度={len(b64)}")
        parts.append({
            "inlineData": {
                "mimeType": mime or "image/jpeg",
                "data": b64,
            }
        })
    print(f"[多模态] 共{len(image_data_list)}张图片, 成功解析{parsed_count}张")
    if len(parts) <= 1:
        print("[多模态] 所有图片解析失败，无法带图批改")
        return None

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": temperature, "topP": top_p, "maxOutputTokens": 65536},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    print(f"[多模态] Gemini 请求体大小: {len(data)} 字节 ({len(data)/1024/1024:.2f} MB)")

    for idx, api_key in enumerate(api_keys):
        url = base_endpoint.rstrip("/") + f"/v1beta/models/{model_name}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = resp.read().decode("utf-8")
                if not raw or not raw.strip():
                    print("Gemini API 返回空 body")
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    return raw
                err = obj.get("error")
                if err:
                    print("Gemini API 错误:", err)
                    if _is_quota_or_rate_limit_error(None, err):
                        if idx + 1 < len(api_keys):
                            print("配额/限流，尝试备用 API Key")
                            continue
                        print("Gemini 所有 Key 多模态额度均已用完，进入冷却期。")
                        _mark_gemini_quota_exhausted()
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
        except urllib.error.HTTPError as e:
            print("call_gemini_system_with_images HTTPError:", e.code, e.reason)
            if _is_quota_or_rate_limit_error(e.code, None):
                if idx + 1 < len(api_keys):
                    print("配额/限流，尝试备用 API Key")
                    continue
                print("Gemini 所有 Key 多模态 HTTP 限流/额度已用完，进入冷却期。")
                _mark_gemini_quota_exhausted()
            return None
        except Exception as e:
            print("call_gemini_system_with_images failed:", e)
            return None
    return None


def call_gemini_system(
    prompt: str,
    *,
    temperature: float = 0.3,
    top_p: float = 0.9,
) -> Optional[str]:
    """调用 Google Gemini 接口；优先主 Key，遇限流/配额用备用 Key 重试；若所有 Key 都额度用完，则进入冷却期。"""
    if _is_gemini_temporarily_disabled():
        print("Gemini 已标记为额度用完（纯文本），当前请求直接跳过 Gemini。")
        return None

    api_keys = _get_gemini_api_keys()
    if not api_keys:
        print("GEMINI not configured (GEMINI_API_KEY missing)")
        return None
    base_endpoint = os.getenv("GEMINI_ENDPOINT", "https://generativelanguage.googleapis.com")
    model_name = "gemini-3-flash-preview"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "topP": top_p,
            "maxOutputTokens": 65536,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    for idx, api_key in enumerate(api_keys):
        url = base_endpoint.rstrip("/") + f"/v1beta/models/{model_name}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                if not raw or not raw.strip():
                    print("Gemini API 返回空 body")
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    return raw
                err = obj.get("error")
                if err:
                    print("Gemini API 错误:", err)
                    if _is_quota_or_rate_limit_error(None, err):
                        if idx + 1 < len(api_keys):
                            print("配额/限流，尝试备用 API Key")
                            continue
                        print("Gemini 所有 Key 文本额度均已用完，进入冷却期。")
                        _mark_gemini_quota_exhausted()
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
        except urllib.error.HTTPError as e:
            print("call_gemini_system HTTPError:", e.code, e.reason)
            if _is_quota_or_rate_limit_error(e.code, None):
                if idx + 1 < len(api_keys):
                    print("配额/限流，尝试备用 API Key")
                    continue
                print("Gemini 所有 Key 文本 HTTP 限流/额度已用完，进入冷却期。")
                _mark_gemini_quota_exhausted()
            return None
        except Exception as e:
            print("call_gemini_system failed:", e)
            return None
    return None


# 题目 Markdown 中的图片路径为 /images/...，放在所有 API 路由之后挂载
_images_dir = os.path.join(get_data_dir(), "images")
if os.path.isdir(_images_dir):
    app.mount("/images", StaticFiles(directory=_images_dir), name="images")