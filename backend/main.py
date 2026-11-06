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
import urllib.parse
from typing import Optional, List, Dict, Any, Tuple
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
_papers_file_mtime: Dict[str, float] = {}
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
    global _papers_index, _papers_cache, _papers_json_cache, _papers_file_mtime, _papers_index_json, _papers_index_etag
    data_dir = get_data_dir()
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        _papers_index = []
        _papers_cache = {}
        _papers_json_cache = {}
        _papers_file_mtime = {}
        _papers_index_json = b"[]"
        _papers_index_etag = '"empty"'
        return

    papers = []
    cache: Dict[str, dict] = {}
    json_cache: Dict[str, bytes] = {}
    mtime_map: Dict[str, float] = {}
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
            mtime_map[pid] = os.path.getmtime(file_path)
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
    _papers_file_mtime = mtime_map
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


def _refresh_paper_cache_if_stale(paper_id: str) -> None:
    """若磁盘上的试卷 JSON 比内存缓存新，则重新加载该份试卷（改 data 后无需重启后端）。"""
    global _papers_cache, _papers_json_cache, _papers_file_mtime
    data_dir = get_data_dir()
    file_path = os.path.join(data_dir, f"{paper_id}.json")
    if not os.path.isfile(file_path):
        return
    try:
        mtime = os.path.getmtime(file_path)
    except OSError:
        return
    prev = _papers_file_mtime.get(paper_id)
    if prev is not None and mtime <= prev:
        return
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = json.load(f)
    except Exception as e:
        print(f"[试卷缓存] 刷新失败 {file_path}: {e}")
        return
    pid = content.get("id", paper_id)
    _papers_cache[pid] = content
    _papers_json_cache[pid] = json.dumps(content, ensure_ascii=False).encode("utf-8")
    _papers_file_mtime[pid] = mtime


def _load_paper_by_id(paper_id: str):
    """优先从内存缓存读取试卷，缓存未命中时回退到磁盘读取。"""
    _refresh_paper_cache_if_stale(paper_id)
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


def _material_id(m: Any) -> str:
    """取材料 id，兼容 id / materialId / mid 三种字段名"""
    if not isinstance(m, dict):
        return ""
    return str(m.get("id") or m.get("materialId") or m.get("mid") or "")


def _id_variants(value: Any) -> set:
    """把材料/题目的 id 归一化，兼容 m1 / 1 / M1 等写法"""
    s = str(value).strip()
    if not s:
        return set()
    out = {s, s.lower()}
    m_num = re.fullmatch(r"[a-zA-Z]*?(\d+)", s)
    if m_num:
        num = m_num.group(1)
        out.update({num, f"m{num}"})
    return out


# ---------------------------------------------------------
# 1.5 小题「踩分标尺（rubric）」：同一道题只生成一次，之后每次批改复用
#     目的：避免每次批改都让模型重新归纳要点，导致同一题两次批改要点数量/粒度漂移
# ---------------------------------------------------------
RUBRIC_DIR = os.path.join(get_data_dir(), "rubrics")
RUBRIC_VERSION = 1

RUBRIC_EXTRACTION_INSTRUCTION = """# Role: 申论命题组 & 阅卷标准制定专家
你的任务是为一道申论小题「制定踩分标尺」，不是批改考生答案。标尺一旦确定会被系统固化，后续所有批改都以它为准，所以必须严谨、可核验。

# 输入
- 题目：{TITLE}
- 题目要求：{REQUIREMENTS}
- 本题满分：{MAX_SCORE} 分
- 本题相关材料（含完整正文）：{MATERIALS}

# 制定规则（必须严格遵守）
1. 逐段扫描：按材料顺序逐段提炼，不得跳过任何一段；每段要么归入某个要点，要么明确判定「该段无得分点」。
2. 要点数量：4~6 个。材料确实只有一个层次时才可少于 4 个；禁止把一个要点拆成多条凑数，也禁止把两个独立要点合并。
3. 每个要点必须是「动词 + 名词」的可得分表述（如「完善利益联结机制」「培育本土技术人才」），不能是案例细节、数据、背景描述或空泛口号。
4. keywords：每个要点给 2~5 个材料原词，必须是材料原文中出现过的词，不得自造同义词。
5. evidence：从材料中逐字摘录 15~40 字原文作为依据，必须与材料原文完全一致（不得改写、不得拼接、不得跨段拼）。
6. 分值：各要点分值之和必须等于 {MAX_SCORE}，按要点重要程度分配整数分值。
7. 覆盖度自查：输出前逐段核对，确认每段信息都已归入某个要点或标注为无得分点。

# 输出
只输出一个 JSON 对象，不要解释、不要额外文字：
{
  "points": [
    {"no": 1, "summary": "要点概括（动词+名词）", "keywords": ["材料原词1", "材料原词2"], "score": 5, "evidence": "材料原文片段", "materialId": "m1"}
  ],
  "coverage": [
    {"materialId": "m1", "covered": true, "note": "归入第 1 条"}
  ]
}
"""


def _rubric_material_hash(materials: List[Dict[str, Any]]) -> str:
    """材料内容指纹：材料被修改后旧标尺自动失效"""
    digest = hashlib.sha256()
    digest.update(str(RUBRIC_VERSION).encode("utf-8"))
    for m in materials or []:
        if not isinstance(m, dict):
            continue
        digest.update(str(m.get("id") or "").encode("utf-8"))
        digest.update(str(m.get("title") or "").encode("utf-8"))
        digest.update(str(m.get("content") or "").encode("utf-8"))
    return digest.hexdigest()[:16]


def _rubric_path(paper_id: str, question_id: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]", "_", f"{paper_id}__{question_id}")
    return os.path.join(RUBRIC_DIR, f"{safe}.json")


def _extract_json_object(text: str) -> Optional[dict]:
    """从模型输出中取出第一个完整 JSON 对象（兼容 ```json 包裹与前后废话）"""
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(cleaned[start:end + 1])
    except Exception:
        return None


def _rescale_point_scores(points: List[Dict[str, Any]], max_score: int) -> None:
    """把要点分值等比缩放到满分，保证 sum(score) == max_score（整数）"""
    if not points or max_score <= 0:
        return
    scores = [max(0, int(p.get("score") or 0)) for p in points]
    total = sum(scores)
    if total <= 0:
        base = max_score // len(points)
        for idx, p in enumerate(points):
            p["score"] = base if idx < len(points) - 1 else max_score - base * (len(points) - 1)
        return
    if total == max_score:
        return
    scaled = [max(1, round(s * max_score / total)) for s in scores]
    diff = max_score - sum(scaled)
    # 差额补到分值最大的要点上，避免出现 0 分要点
    scaled[scaled.index(max(scaled))] += diff
    for p, s in zip(points, scaled):
        p["score"] = max(0, s)


def _normalize_rubric(
    data: dict,
    paper_id: str,
    question_id: str,
    max_score: int,
    material_hash: str,
    material_ids: List[str],
    source: str,
) -> Optional[dict]:
    """校验并规整标尺结构，不合格返回 None（调用方回退到实时归纳）"""
    if not isinstance(data, dict):
        return None
    raw_points = data.get("points")
    if not isinstance(raw_points, list) or not raw_points:
        return None

    points: List[Dict[str, Any]] = []
    for idx, p in enumerate(raw_points, start=1):
        if not isinstance(p, dict):
            continue
        summary = str(p.get("summary") or p.get("point") or "").strip()
        if not summary:
            continue
        keywords = p.get("keywords") or p.get("words") or []
        if isinstance(keywords, str):
            keywords = [keywords]
        keywords = [str(k).strip() for k in keywords if str(k).strip()]
        points.append({
            "no": idx,
            "summary": summary,
            "keywords": keywords,
            "score": int(p.get("score") or 0),
            "evidence": str(p.get("evidence") or "").strip(),
            "materialId": str(p.get("materialId") or "").strip(),
        })

    if len(points) < 2:
        return None
    _rescale_point_scores(points, max_score)

    return {
        "version": RUBRIC_VERSION,
        "paperId": paper_id,
        "questionId": question_id,
        "maxScore": max_score,
        "materialIds": material_ids,
        "materialHash": material_hash,
        "points": points,
        "coverage": data.get("coverage") if isinstance(data.get("coverage"), list) else [],
        "source": source,
        "createdAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def _load_rubric(paper_id: str, question_id: str, material_hash: str) -> Optional[dict]:
    path = _rubric_path(paper_id, question_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            rubric = json.load(f)
    except Exception as e:
        print(f"[标尺] 读取失败 {path}: {e}")
        return None
    if rubric.get("version") != RUBRIC_VERSION:
        print(f"[标尺] 版本过期，重新生成: {path}")
        return None
    if rubric.get("materialHash") != material_hash:
        print(f"[标尺] 材料已变更，重新生成: {path}")
        return None
    # 结构自检：人工改坏或旧格式（缺 points/要点为空）时按「无标尺」处理，避免注入时报错
    points = rubric.get("points")
    if not isinstance(points, list) or not points or not all(
        isinstance(p, dict) and str(p.get("summary") or "").strip() for p in points
    ):
        print(f"[标尺] 结构不完整，重新生成: {path}")
        return None
    return rubric


def _save_rubric(rubric: dict) -> None:
    path = _rubric_path(rubric["paperId"], rubric["questionId"])
    try:
        os.makedirs(RUBRIC_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rubric, f, ensure_ascii=False, indent=2)
        print(f"[标尺] 已固化 {path}（{len(rubric['points'])} 个要点）")
    except Exception as e:
        print(f"[标尺] 写入失败 {path}: {e}")


def _normalize_for_match(text: str) -> str:
    """比对用的归一化：去掉空白与常见中英文标点，只留实义字符"""
    return re.sub(r"[\s，。、；：？！“”‘’（）《》〈〉【】〔〕—…·,.;:?!\"'()\[\]<>/\\|~`-]+", "", text or "")


def _evidence_hit(evidence: str, material_text: str) -> str:
    """判断 evidence 是否来自材料原文。

    返回 "exact"（整段命中）/ "partial"（连续 12 字片段命中）/ ""（编造）。
    模型常会轻微改写或漏标点，所以留一个片段命中的口子，但整段编造的必须挡住。
    """
    ev = _normalize_for_match(evidence)
    if not ev or len(ev) < 6:
        return ""
    if ev in material_text:
        return "exact"
    window = 12
    if len(ev) >= window:
        for i in range(0, len(ev) - window + 1):
            if ev[i:i + window] in material_text:
                return "partial"
    return ""


def _verify_rubric_quality(rubric: dict, materials: List[Dict[str, Any]]) -> dict:
    """给标尺做证据校验与覆盖度校验，结果写入 rubric["quality"]。

    - verifiedRatio：要点中「证据能在材料原文找到」的比例（防止模型编造要点）
    - coverageComplete：每份材料是否都有要点归属（防止漏段）
    - keywordRatio：要点关键词在材料中出现的比例
    """
    material_text = _normalize_for_match("".join(str(m.get("content") or "") for m in materials or []))
    points = rubric.get("points") or []

    verified = 0
    keyword_hits = 0
    for p in points:
        match = _evidence_hit(str(p.get("evidence") or ""), material_text)
        p["evidenceMatch"] = match
        p["evidenceVerified"] = bool(match)
        if match:
            verified += 1
        keywords = [str(k) for k in (p.get("keywords") or [])]
        if keywords and any(_normalize_for_match(k) in material_text for k in keywords):
            keyword_hits += 1

    covered_ids = set()
    for p in points:
        mid = str(p.get("materialId") or "").strip()
        if mid:
            covered_ids.add(mid)
    covered_variants = set()
    for mid in covered_ids:
        covered_variants |= _id_variants(mid)
    all_ids = [str(m.get("id")) for m in materials or [] if isinstance(m, dict) and m.get("id")]
    missing = [i for i in all_ids if not (_id_variants(i) & covered_variants)]

    total = len(points) or 1
    quality = {
        "verifiedRatio": round(verified / total, 2),
        "keywordRatio": round(keyword_hits / total, 2),
        "coverageComplete": not missing,
        "missingMaterialIds": missing,
        "pointCount": len(points),
    }
    rubric["quality"] = quality
    return quality


def _rubric_env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or "").strip() or default)
    except ValueError:
        return default


def _rubric_env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or "").strip() or default)
    except ValueError:
        return default


def _rubric_status_by_quality(quality: dict) -> str:
    """质量达标自动 approved，否则 draft（只作参考，允许模型补充）"""
    if (os.getenv("RUBRIC_AUTO_APPROVE") or "1").strip().lower() in {"0", "false", "no", "off"}:
        return "draft"
    min_verified = _rubric_env_float("RUBRIC_MIN_VERIFIED", 0.8)
    if quality.get("verifiedRatio", 0) >= min_verified and quality.get("coverageComplete"):
        return "approved"
    return "draft"


def _build_rubric_once(
    prompt: str,
    paper_id: str,
    question_id: str,
    max_score: int,
    material_hash: str,
    material_ids: List[str],
    materials: List[Dict[str, Any]],
) -> Optional[dict]:
    text, provider, _model = call_grading_model(prompt, None, temperature=0.0, top_p=1.0)
    data = _extract_json_object(text or "")
    rubric = _normalize_rubric(data or {}, paper_id, question_id, max_score, material_hash, material_ids, "auto")
    if not rubric:
        print(f"[标尺] 生成失败或格式不合格 paper={paper_id} q={question_id} provider={provider}")
        return None
    _verify_rubric_quality(rubric, materials)
    return rubric


def _rubric_score_for_ranking(rubric: dict) -> Tuple[float, float]:
    """多采样取优的排序键：证据通过率 > 关键词命中率/覆盖完整/要点数合理"""
    q = rubric.get("quality") or {}
    point_count = q.get("pointCount", 0)
    sane = 1 if 4 <= point_count <= 6 else 0
    return (
        float(q.get("verifiedRatio", 0)),
        float(q.get("keywordRatio", 0)) + (0.5 if q.get("coverageComplete") else 0) + sane * 0.1,
    )


def _point_bigrams(text: str) -> set:
    s = _normalize_for_match(text)
    if not s:
        return set()
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def _point_similarity(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    """两个要点的相似度：摘要字符二元组 Jaccard 与关键词重合度取较大值"""
    ga, gb = _point_bigrams(str(a.get("summary") or "")), _point_bigrams(str(b.get("summary") or ""))
    jac = len(ga & gb) / len(ga | gb) if (ga and gb) else 0.0
    ka = {_normalize_for_match(k) for k in (a.get("keywords") or []) if str(k).strip()}
    kb = {_normalize_for_match(k) for k in (b.get("keywords") or []) if str(k).strip()}
    kw = len(ka & kb) / max(1, min(len(ka), len(kb))) if (ka and kb) else 0.0
    return max(jac, kw)


def _merge_candidate_rubrics(
    pool: List[dict],
    max_score: int,
    material_hash: str,
    material_ids: List[str],
    paper_id: str,
    question_id: str,
) -> Optional[dict]:
    """把多次采样/多次批改得到的候选要点聚类归并成一份标尺。

    规则：同一要点被越多份候选提到，越可信；按「出现次数 > 证据命中 > 成员数」排序后取前 k 个。
    k 取各候选要点数的中位数（夹在 3~6），避免归并后要点过少或过碎。
    """
    if not pool:
        return None
    if len(pool) == 1:
        return pool[0]

    clusters: List[Dict[str, Any]] = []
    for idx, cand in enumerate(pool):
        for p in cand.get("points") or []:
            if not isinstance(p, dict):
                continue
            best, best_sim = None, 0.0
            for cl in clusters:
                sim = _point_similarity(p, cl["rep"])
                if sim > best_sim:
                    best, best_sim = cl, sim
            if best is not None and best_sim >= 0.5:
                best["members"].append(p)
                best["candidates"].add(idx)
            else:
                clusters.append({"rep": p, "members": [p], "candidates": {idx}})

    if len(clusters) < 2:
        return None

    def sort_key(cl: Dict[str, Any]) -> Tuple[int, int, int]:
        hits = sum(1 for m in cl["members"] if m.get("evidenceVerified"))
        return (len(cl["candidates"]), hits, len(cl["members"]))

    clusters.sort(key=sort_key, reverse=True)

    counts = sorted(len(c.get("points") or []) for c in pool)
    target = counts[len(counts) // 2] if counts else 4
    target = max(3, min(6, target))

    points: List[Dict[str, Any]] = []
    for no, cl in enumerate(clusters[:target], start=1):
        members = cl["members"]
        # 摘要：取出现次数最多的写法
        summary_key = Counter(_normalize_for_match(str(m.get("summary") or "")) for m in members).most_common(1)[0][0]
        summary = next(
            str(m.get("summary")) for m in members if _normalize_for_match(str(m.get("summary") or "")) == summary_key
        )
        keywords: List[str] = []
        for m in members:
            for k in m.get("keywords") or []:
                if k not in keywords:
                    keywords.append(k)
        evidence = next((str(m.get("evidence")) for m in members if m.get("evidenceVerified")), "")
        if not evidence:
            evidence = str(members[0].get("evidence") or "")
        mids = Counter(str(m.get("materialId") or "") for m in members if m.get("materialId"))
        scores = [int(m.get("score") or 0) for m in members]
        points.append({
            "no": no,
            "summary": summary,
            "keywords": keywords[:5],
            "score": round(sum(scores) / len(scores)) if scores else 0,
            "evidence": evidence,
            "materialId": mids.most_common(1)[0][0] if mids else "",
            "support": len(cl["candidates"]),
        })

    rubric = _normalize_rubric(
        {"points": points}, paper_id, question_id, max_score, material_hash, material_ids, "auto"
    )
    if not rubric:
        return None
    rubric["mergeInfo"] = {
        "candidates": len(pool),
        "clusters": len(clusters),
        "kept": len(points),
        "support": [p.get("support") for p in points],
    }
    return rubric


# ---------------------------------------------------------
# 累积投票存储：只存「聚合状态」（每簇计数），不存历史明细，单题约 1~2KB
#   RUBRIC_VOTE_STORE=file（默认，落本地盘）| redis（Upstash REST，免费额度足够）| none
# ---------------------------------------------------------
def _votes_dir() -> str:
    """跟随 RUBRIC_DIR 动态计算，避免目录被改（如测试/多环境）后写到旧路径"""
    return os.path.join(RUBRIC_DIR, "_votes")


def _vote_key(paper_id: str, question_id: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]", "_", f"{paper_id}__{question_id}")
    return f"rubric:votes:{safe}"


def _vote_store_backend() -> str:
    return (os.getenv("RUBRIC_VOTE_STORE") or "file").strip().lower()


def _kv_get(key: str) -> Optional[dict]:
    """读聚合状态。任何失败都返回 None（等同于「没有历史」），不阻断批改。"""
    backend = _vote_store_backend()
    if backend == "none":
        return None
    if backend == "redis":
        url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
        if not url or not token:
            print("[标尺] 未配置 UPSTASH_REDIS_REST_URL/TOKEN，投票存储降级为跳过")
            return None
        try:
            req = urllib.request.Request(
                f"{url}/get/{urllib.parse.quote(key)}",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8") or "{}")
            raw = data.get("result")
            return json.loads(raw) if raw else None
        except Exception as e:
            print(f"[标尺] Redis 读取失败（跳过投票）: {e}")
            return None

    path = os.path.join(_votes_dir(), f"{key}.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[标尺] 投票文件读取失败 {path}: {e}")
        return None


def _kv_set(key: str, value: dict) -> None:
    backend = _vote_store_backend()
    if backend == "none":
        return
    payload = json.dumps(value, ensure_ascii=False)
    if backend == "redis":
        url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
        if not url or not token:
            return
        try:
            body = json.dumps(["SET", key, payload], ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                resp.read()
            print(f"[标尺] 投票状态已写入 Redis（{len(payload)} 字节）")
        except Exception as e:
            print(f"[标尺] Redis 写入失败（本次投票未保存）: {e}")
        return

    path = os.path.join(_votes_dir(), f"{key}.json")
    try:
        os.makedirs(_votes_dir(), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload)
    except Exception as e:
        print(f"[标尺] 投票文件写入失败 {path}: {e}")


def _empty_vote_state() -> dict:
    return {"rounds": 0, "clusters": [], "updatedAt": None}


def _merge_vote_state(state: Optional[dict], candidate_points: List[dict], keep_clusters: int = 12) -> dict:
    """把一份候选要点并入聚合状态：同一要点累加计数，不做全量历史存储。"""
    state = dict(state or _empty_vote_state())
    clusters: List[dict] = [dict(c) for c in state.get("clusters") or []]
    for cl in clusters:
        cl.setdefault("count", 1)
        cl.setdefault("keywords", [])
        cl.setdefault("scores", [])

    for p in candidate_points or []:
        if not isinstance(p, dict):
            continue
        best, best_sim = None, 0.0
        for cl in clusters:
            sim = _point_similarity(p, cl)
            if sim > best_sim:
                best, best_sim = cl, sim
        if best is not None and best_sim >= 0.5:
            best["count"] += 1
            best["scores"].append(int(p.get("score") or 0))
            for k in p.get("keywords") or []:
                if k not in best["keywords"]:
                    best["keywords"].append(k)
            if p.get("evidenceVerified") and not best.get("evidenceVerified"):
                best["evidence"] = str(p.get("evidence") or "")
                best["evidenceVerified"] = True
            if not best.get("materialId") and p.get("materialId"):
                best["materialId"] = str(p.get("materialId"))
        else:
            clusters.append({
                "summary": str(p.get("summary") or ""),
                "keywords": list(p.get("keywords") or [])[:5],
                "count": 1,
                "scores": [int(p.get("score") or 0)],
                "evidence": str(p.get("evidence") or ""),
                "evidenceVerified": bool(p.get("evidenceVerified")),
                "materialId": str(p.get("materialId") or ""),
            })

    clusters.sort(key=lambda c: (c.get("count", 0), 1 if c.get("evidenceVerified") else 0), reverse=True)
    state["clusters"] = clusters[:keep_clusters]
    state["rounds"] = int(state.get("rounds", 0)) + 1
    state["updatedAt"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    return state


def _rubric_from_vote_state(
    state: dict,
    max_score: int,
    material_hash: str,
    material_ids: List[str],
    paper_id: str,
    question_id: str,
) -> Optional[dict]:
    """按票数把聚合状态还原成标尺：过半票的要点优先，不足 3 个时按票数补足。"""
    clusters = state.get("clusters") or []
    if not clusters:
        return None
    rounds = int(state.get("rounds") or 1)
    threshold = max(2, -(-rounds // 2)) if rounds >= 2 else 1
    kept = [c for c in clusters if int(c.get("count") or 0) >= threshold][:6]
    if len(kept) < 3:
        kept = clusters[:min(6, len(clusters))]

    points: List[Dict[str, Any]] = []
    for no, cl in enumerate(kept, start=1):
        scores = [s for s in (cl.get("scores") or []) if isinstance(s, int)]
        points.append({
            "no": no,
            "summary": cl.get("summary") or "",
            "keywords": list(cl.get("keywords") or [])[:5],
            "score": round(sum(scores) / len(scores)) if scores else 0,
            "evidence": cl.get("evidence") or "",
            "materialId": cl.get("materialId") or "",
            "support": int(cl.get("count") or 0),
        })

    rubric = _normalize_rubric(
        {"points": points}, paper_id, question_id, max_score, material_hash, material_ids, "auto"
    )
    if not rubric:
        return None
    rubric["voteState"] = {"rounds": rounds, "kept": len(points), "clusters": len(clusters)}
    return rubric


def _append_votes(paper_id: str, question_id: str, candidates: List[dict]) -> dict:
    """把候选要点并入聚合状态并写回存储，返回最新状态"""
    key = _vote_key(paper_id, question_id)
    state = _kv_get(key)
    for cand in candidates:
        state = _merge_vote_state(state, cand.get("points") or [])
    _kv_set(key, state)
    return state


def get_or_create_rubric(
    paper_id: str,
    question: Dict[str, Any],
    materials: List[Dict[str, Any]],
    max_score: int,
    province_label: str = "",
) -> Tuple[Optional[dict], str]:
    """读取或生成小题标尺。返回 (rubric, 来源)，失败返回 (None, "")。"""
    question_id = str(question.get("id") or question.get("qid") or "q1")
    material_hash = _rubric_material_hash(materials)
    material_ids = [str(m.get("id")) for m in materials or [] if isinstance(m, dict)]

    cached = _load_rubric(paper_id, question_id, material_hash)
    if cached:
        status = cached.get("status") or "approved"
        print(f"[标尺] 复用已固化标尺 paper={paper_id} q={question_id} status={status}")
        return cached, "复用"

    prompt = (
        RUBRIC_EXTRACTION_INSTRUCTION
        .replace("{TITLE}", str(question.get("title") or ""))
        .replace("{REQUIREMENTS}", str(question.get("requirements") or ""))
        .replace("{MAX_SCORE}", str(max_score))
        .replace("{MATERIALS}", json.dumps(materials or [], ensure_ascii=False))
    )
    if province_label:
        prompt += f"\n【地区特征参考】{province_label}：{PROVINCE_GRADING_PROFILE.get(province_label, {}) or ''}"

    # 首次生成容易不准：跑多次并「对比归并」，而不是简单取一份（RUBRIC_SAMPLE_TIMES 可调）
    sample_times = max(1, min(5, _rubric_env_int("RUBRIC_SAMPLE_TIMES", 2)))
    candidates: List[dict] = []
    for idx in range(sample_times):
        candidate = _build_rubric_once(
            prompt, paper_id, question_id, max_score, material_hash, material_ids, materials
        )
        if candidate:
            candidates.append(candidate)
            q = candidate.get("quality") or {}
            print(
                f"[标尺] 采样 {idx + 1}/{sample_times}：{q.get('pointCount')} 个要点，"
                f"证据通过率 {q.get('verifiedRatio')}，覆盖完整={q.get('coverageComplete')}"
            )
            # 第一次就全部证据命中且覆盖完整，说明这次抽得很准，不必再采
            if q.get("verifiedRatio", 0) >= 0.99 and q.get("coverageComplete"):
                break

    if not candidates:
        return None, ""

    # 可选：累积投票模式。存储里只保留「聚合状态」（每簇计数），不存历史明细
    accumulate = (os.getenv("RUBRIC_VOTE_ACCUMULATE") or "0").strip().lower() in {"1", "true", "yes", "on"}
    if accumulate:
        state = _append_votes(paper_id, question_id, candidates)
        rounds = int(state.get("rounds") or 0)
        merged = _rubric_from_vote_state(state, max_score, material_hash, material_ids, paper_id, question_id)
        if merged:
            quality = _verify_rubric_quality(merged, materials)
            merged["status"] = _rubric_status_by_quality(quality)
            merged["sampleTimes"] = rounds
            merged["voteCount"] = rounds
            print(
                f"[标尺] 投票归并：{len(merged['points'])} 个要点（累计 {rounds} 次），"
                f"证据通过率 {quality.get('verifiedRatio')}，status={merged['status']}"
            )
            promote_after = max(2, _rubric_env_int("RUBRIC_PROMOTE_AFTER", 3))
            if rounds < promote_after:
                print(f"[标尺] 累积投票 {rounds}/{promote_after}，本次不固化，仅作临时标尺使用")
                return merged, f"临时（{rounds}/{promote_after} 次投票）"
            _save_rubric(merged)
            return merged, "投票固化"
        print("[标尺] 投票状态无法还原标尺，回退为本次采样结果")

    merged = _merge_candidate_rubrics(candidates, max_score, material_hash, material_ids, paper_id, question_id)
    if not merged:
        merged = max(candidates, key=_rubric_score_for_ranking)
        print("[标尺] 归并失败（要点无法对齐），回退为单次采样中最优的一份")

    quality = _verify_rubric_quality(merged, materials)
    merged["status"] = _rubric_status_by_quality(quality)
    merged["sampleTimes"] = len(candidates)
    print(
        f"[标尺] 归并结果：{len(merged['points'])} 个要点（来自 {len(candidates)} 次采样），"
        f"证据通过率 {quality.get('verifiedRatio')}，覆盖完整={quality.get('coverageComplete')}，"
        f"status={merged['status']}"
    )
    if merged["status"] == "draft":
        print(
            f"[标尺] 质量未达标（证据通过率 {quality.get('verifiedRatio')}，覆盖完整={quality.get('coverageComplete')}），"
            f"标记为 draft，仅作参考注入"
        )

    _save_rubric(merged)
    return merged, "新生成"


def _format_rubric_block(rubric: dict, source: str) -> str:
    status = rubric.get("status") or "approved"
    quality = rubric.get("quality") or {}
    head = (
        f"【系统内部资料·评分依据】本题踩分标尺（{source}，共 {len(rubric['points'])} 个要点，"
        f"合计 {rubric['maxScore']} 分，状态：{'已审核' if status == 'approved' else '参考稿'}，"
        f"证据通过率 {quality.get('verifiedRatio', '—')}）"
    )
    if status == "approved":
        rules = [
            "以下内容只作为你的评分依据，**严禁在报告中复述、转述或提及本段任何文字**"
            "（不要出现「已固化」「标尺」「以下直接引用」等字样，也不要说明要点从何而来）：",
            "1. 模块二直接按下列要点逐条输出要点内容本身（编号、概括、分值保持一致），不得增删或合并；",
            "2. 模块四的「要点分」按下列要点逐条比对，明确写出命中/未命中的要点编号；",
            "3. 模块五的参考答案必须覆盖下列全部要点，且必须放进模块一 1.3「结构约定」的分述框架内，"
            "不得另起一套并列序号（例如标尺 5 点、结构约定 2 个分述时，写成 2 个分述内部串联 5 点）。",
        ]
    else:
        rules = [
            "以下内容只作为你的评分依据，**严禁在报告中复述、转述或提及本段任何文字**"
            "（不要出现「参考稿」「标尺」「未经人工审核」等字样）：",
            "1. 模块二按下列要点逐条输出要点内容本身（编号与概括保持一致），不得删除或合并已有要点；",
            "2. 若你在材料中发现遗漏了独立的重要要点，只能在要点末尾追加「补充要点：…」，并在报告中说明依据，不得改写原要点；",
            "3. 模块四的「要点分」按「上述要点 + 你补充的要点」合计计算，并注明哪些是补充；",
            "4. 模块五的参考答案必须覆盖上述全部要点，且按模块一 1.3「结构约定」的分述框架组织，不得另起一套并列序号。",
        ]
    lines = [head] + rules + [
        json.dumps({"points": rubric["points"]}, ensure_ascii=False, separators=(",", ":"))
    ]
    return "\n".join(lines)


def _count_answer_chars(answers: Dict[str, Any]) -> int:
    """系统统计字数：去掉空白后的字符数（申论按格子计字，标点计入）"""
    total = 0
    for value in (answers or {}).values():
        text = str(value or "")
        if text.startswith("（考生上传了作答图片"):
            continue
        total += len(re.sub(r"\s+", "", text))
    return total


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
    _refresh_paper_cache_if_stale(paper_id)
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


PROVINCE_GRADING_PROFILE = {
    "全国": {
        "label": "国考",
        "small_q": "按要点逐条踩分，原词命中率决定得分；副省级概括题重站位高度，地市级对策题重实操可行性；漏要点扣分严，不接受意思相近的自造词",
        "essay": "大作文重政策高度与材料深度化用，均分约满分55%；高分需有权威性政策语言，标题须高度凝练",
        "score_dist": "小题均分56%~64%，大作文均分53%~61%",
    },
    "江苏": {
        "label": "江苏省考",
        "small_q": "单一概括题'用一段话'格式为硬要求，违反格式直接扣格式分；字数超限扣分明显；要点须用原词精准表述",
        "essay": "大作文重逻辑结构，分论点须严格对应总论点，层次清晰权重高",
        "score_dist": "小题均分60%~68%，大作文均分55%~63%",
    },
    "广东": {
        "label": "广东省考",
        "small_q": "实操类题目（公文、方案、推荐语）占比重，公文格式错误（称谓、落款、标题格式）直接扣5分以上；内容空洞扣分重",
        "essay": "大作文重实用性与可操作性，对策需具体到主体、措施、效果；空洞表述直接降档",
        "score_dist": "小题均分62%~70%，大作文均分55%~63%",
    },
    "浙江": {
        "label": "浙江省考",
        "small_q": "材料信息密度高、要点数量多，漏点扣分重；鼓励大量直引材料原词，自造词不得分",
        "essay": "大作文重材料利用率，需充分化用材料内容，空洞论证直接降档",
        "score_dist": "小题均分58%~66%，大作文均分54%~62%",
    },
    "北京": {
        "label": "北京市考",
        "small_q": "偏重实际工作应用，对策题要求具体且可落地；概括题重逻辑分类",
        "essay": "大作文偏重实用导向，理论高度要求相对低于国考，重在措施具体",
        "score_dist": "小题均分60%~68%，大作文均分55%~63%",
    },
    "上海": {
        "label": "上海市考",
        "small_q": "联考风格，题型多样；分析题重思辨逻辑，要求辩证看待问题",
        "essay": "大作文重思辨性与独到见解，套路化表述会被降档",
        "score_dist": "小题均分58%~66%，大作文均分54%~62%",
    },
    "山东": {
        "label": "山东省考",
        "small_q": "中规中矩，材料信息密度中等；要点完整性是主要评分标准",
        "essay": "大作文重结构完整与语言规范，分论点须有具体论证",
        "score_dist": "小题均分60%~67%，大作文均分55%~62%",
    },
    "四川": {
        "label": "四川省考",
        "small_q": "概括类题目较多，语言规范性要求高；要点须分条清晰呈现",
        "essay": "大作文重语言规范与文章气势，引用格言警句可加印象分",
        "score_dist": "小题均分60%~67%，大作文均分55%~62%",
    },
    "湖北": {
        "label": "湖北省考",
        "small_q": "材料逻辑性强，分析题占比高；要求答出因果链条，不只列现象",
        "essay": "大作文重论证深度，浅层铺陈不得高分",
        "score_dist": "小题均分58%~66%，大作文均分54%~62%",
    },
    "河南": {
        "label": "河南省考",
        "small_q": "中等难度，题型传统；要点覆盖率是主要评分维度",
        "essay": "大作文偏重格式规范，结构完整度权重较高",
        "score_dist": "小题均分60%~67%，大作文均分55%~62%",
    },
    "_default": {
        "label": "省考",
        "small_q": "按要点踩分，原词命中率决定得分；漏要点按比例扣分，不接受意思相近的自造词替换",
        "essay": "大作文重立意准确与材料化用，均分约满分55%~60%",
        "score_dist": "小题均分58%~66%，大作文均分54%~62%",
    },
}


def _parse_score_from_markdown(text: str) -> tuple:
    """解析档位估分区间（新格式）或精确得分（旧格式兜底）。返回 (score_midpoint, max_score)。"""
    if not text:
        return (None, None)
    # 新格式：估分区间：约16~20分（满分25分）
    m = re.search(r"估分区间[：:\s]*约?\s*(\d+)\s*[~～\-]\s*(\d+)\s*分[^（(]*[（(]满分\s*(\d+)\s*分", text)
    if m:
        low, high, max_s = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return ((low + high) // 2, max_s)
    # 旧格式兜底：得分：X/满分Y
    m = re.search(r"得分[：:\s]*(\d+)\s*[/／]\s*(?:满分)?\s*(\d+)", text, re.IGNORECASE)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (None, None)


def _log_grading_result(
    paper_id: str,
    question_ids: List[str],
    body: str,
    score: Optional[int],
    max_score: Optional[int],
    grade: Optional[str],
    provider: str,
    model_name: str,
    elapsed_ms: int,
    material_count: int,
    rubric: Optional[dict],
    rubric_source: str,
) -> None:
    """把批改结果打到服务端日志（Render 日志面板可直接看到），便于线上排查。"""
    rubric_desc = "无标尺"
    if rubric:
        quality = rubric.get("quality") or {}
        rubric_desc = "%s(%d点/证据%s/%s)" % (
            rubric.get("status") or "approved",
            len(rubric.get("points") or []),
            quality.get("verifiedRatio", "-"),
            rubric_source or "-",
        )
    print(
        "[批改结果] paper=%s q=%s 得分=%s/%s 档位=%s 用时=%dms provider=%s model=%s 材料=%d份 标尺=%s"
        % (
            paper_id or "-",
            ",".join(str(q) for q in question_ids) or "-",
            score if score is not None else "-",
            max_score if max_score is not None else "-",
            grade or "-",
            elapsed_ms,
            provider or "-",
            model_name or "-",
            material_count,
            rubric_desc,
        )
    )
    content = body or ""
    limit = _env_int("GRADE_LOG_CONTENT_MAX", 8000)
    if limit > 0 and len(content) > limit:
        print("[批改结果全文] 共 %d 字，按 GRADE_LOG_CONTENT_MAX=%d 截断：" % (len(content), limit))
        print(content[:limit])
        print("…（已截断，如需完整内容请调大 GRADE_LOG_CONTENT_MAX，设为 0 表示不截断）")
    else:
        print("[批改结果全文] 共 %d 字：" % len(content))
        print(content)


# 不该出现在考生报告里的内部措辞（提示词/标尺相关内容）
# 公文/应用文专项格式指导：只在题干命中时注入，避免给所有小题增加 token
OFFICIAL_DOC_KEYWORDS = (
    "请示", "通知", "通报", "批复", "会议纪要", "公函", "通告", "公告",
    "倡议书", "公开信", "发言稿", "讲话稿", "讲解稿", "宣传稿", "推荐语",
    "编者按", "简报", "短评", "工作方案", "汇报提纲", "建议书", "慰问信",
    "感谢信", "卷首语", "导言", "主持词", "致辞", "解说词",
)
OFFICIAL_DOC_GUIDE = """   - ⚠️ **公文格式专项（本题为公文/应用文，优先级高于上面的通用排版建议）**：
     - 标题单独一行并加粗，如 `**关于召开村级治理经验现场交流会的请示**`；
     - 主送机关顶格单独一行、末尾用冒号，如 `镇党委：`；
     - 正文按「缘由段 / 事项段 / 结语段」分段，**相邻段落之间必须空一行**，结语（如「妥否，请批示。」）单独成段；
     - 发文单位（落款）与日期各自单独成行放在正文之后，两者之间也要空一行，日期写「×年×月×日」；
     - **公文正文一律不加粗、不用表情符号、不用分条序号**，除标题外禁止使用 `**`；
     - 1.3 的「结构约定」行在本题中按公文要素填写（如 `段落形式=标题/主送/缘由段/事项段/结语段/落款/日期；序号形式=无序号`），不要按「分述数=N」把公文拆成 N 个并列分述；
     - 严禁把标题、主送机关、正文、落款、日期挤进同一个自然段。"""


def _is_official_doc(questions: List[Dict[str, Any]]) -> bool:
    text = " ".join(
        str(q.get("title") or "") + " " + str(q.get("requirements") or "")
        for q in questions
    )
    if any(k in text for k in OFFICIAL_DOC_KEYWORDS):
        return True
    return bool(re.search(r"以.{1,20}名义", text))


INTERNAL_MARKERS = (
    "本题已固化的踩分标尺",
    "已固化标尺",
    "固化标尺",
    "以下直接引用",
    "不重新归纳",
    "不得增删或合并",
    "未经人工审核",
    "本提示词",
    "系统指令",
    "内部校验",
)

# 结构约定行：模型仍会输出、供 1.7 沿用，但由后端隐藏，只把摘要写进日志
STRUCTURE_START = "<!--STRUCTURE_CONVENTION_START-->"
STRUCTURE_END = "<!--STRUCTURE_CONVENTION_END-->"
# 剥离常见 Markdown 行首前缀：空白 / > 引用 / 反引号 / 加粗、列表符号 / # / 数字编号
_STRUCTURE_PREFIX = re.compile(r"^[\s>`*+\-#]*(?:\d+(?:\.\d+)*[.、]?\s*)?")
# 「结构约定」后允许加粗闭合星号/反引号，再接全角或半角冒号
_STRUCTURE_HEAD = re.compile(r"^结构约定[\s*`]*[:：]")


def _structure_summary(text: str) -> str:
    """从结构约定行提取短摘要（只用于日志，不打印整行）"""
    m = re.search(r"分述数=\s*\d+[^；]*；分组=\s*[^；]+", text)
    return ((m.group(0) if m else text[:40]).strip())[:60]


def _count_map_row(cells: List[str], meta: dict) -> None:
    """统计要点对应表的一行（跳过表头与分隔行）"""
    if not cells or re.fullmatch(r"[-: ]*", cells[0] or ""):
        return
    if "要点编号" in (cells[0] or "") or "要点概括" in "".join(cells[:2]):
        return
    meta["map_rows"] = meta.get("map_rows", 0) + 1
    last = cells[-1] if cells else ""
    if "✓" in last or "√" in last or "是" in last:
        meta["map_covered"] = meta.get("map_covered", 0) + 1


def _strip_internal_sections(text: str) -> Tuple[str, dict]:
    """把不该给考生看的内容从报告里清掉：内部标尺块、要点对应表、提示词措辞。

    返回 (清洗后的正文, 统计信息)。统计信息只用于日志，不返回前端。
    """
    if not text:
        return text, {}
    lines = text.split("\n")
    out: List[str] = []
    meta: dict = {
        "map_rows": 0, "map_covered": 0, "removed": 0,
        "structure_removed": 0, "structure_summary": "",
    }
    i, n = 0, len(lines)

    while i < n:
        raw = lines[i]
        stripped = raw.strip()

        # 0) 结构约定行（内部用）：模型仍输出供 1.7 沿用，返回前隐藏，只记摘要到日志
        if "STRUCTURE_CONVENTION_START" in raw or "STRUCTURE_CONVENTION_END" in raw:
            end_i = i
            if "STRUCTURE_CONVENTION_END" not in raw:
                end_i += 1
                while end_i < n and "STRUCTURE_CONVENTION_END" not in lines[end_i]:
                    end_i += 1
            block = lines[i:end_i + 1]
            joined = " ".join(x.strip() for x in block)
            # 保护：标记被混进长正文时不整块删，只剔除标记字符，交给规则 5 兜底
            if (end_i - i) <= 3 and len(joined) <= 300:
                meta["structure_summary"] = _structure_summary(re.sub(r"<!--[^>]*-->", "", joined))
                meta["structure_removed"] += 1
                meta["removed"] += 1
                i = end_i + 1
                continue
            out.append(raw.replace(STRUCTURE_START, "").replace(STRUCTURE_END, ""))
            i += 1
            continue

        # 1) 显式标记包裹的校验表：<!--RUBRIC_MAP_START--> ... <!--RUBRIC_MAP_END-->
        if "RUBRIC_MAP_START" in raw:
            i += 1
            while i < n and "RUBRIC_MAP_END" not in lines[i]:
                row = lines[i].strip()
                if row.startswith("|"):
                    _count_map_row([c.strip() for c in row.strip("|").split("|")], meta)
                i += 1
            i += 1
            meta["removed"] += 1
            continue

        # 2) 「要点对应表」标题 + 紧随其后的表格（模型有时不写标记）
        if "要点对应表" in stripped and (
            stripped.startswith("#") or re.match(r"^\d+(\.\d+)*\s", stripped) or stripped.startswith("**")
        ):
            meta["removed"] += 1
            i += 1
            while i < n and (not lines[i].strip() or lines[i].strip().startswith("|")):
                row = lines[i].strip()
                if row.startswith("|"):
                    _count_map_row([c.strip() for c in row.strip("|").split("|")], meta)
                i += 1
            continue

        # 2b) 既没标记也没标题的校验表：按表头识别（要点编号 + 是否覆盖）
        if stripped.startswith("|") and "要点编号" in stripped and "覆盖" in stripped:
            meta["removed"] += 1
            while i < n and lines[i].strip().startswith("|"):
                _count_map_row([c.strip() for c in lines[i].strip().strip("|").split("|")], meta)
                i += 1
            continue

        # 3) 模型复述的标尺块 / 提示词措辞（整行删除，限长避免误伤正文段落）
        if len(stripped) <= 150 and any(m in stripped for m in INTERNAL_MARKERS):
            meta["removed"] += 1
            i += 1
            continue

        # 4) 标尺 JSON 被复述出来（形如 "points": [...] / "materialId"）
        if len(stripped) <= 200 and ('"points"' in stripped or '"materialId"' in stripped):
            meta["removed"] += 1
            i += 1
            continue

        # 5) 兜底：模型未写标记时，按「结构约定」行首 + 限长 + 特征字段删整行
        probe = _STRUCTURE_PREFIX.sub("", stripped)
        if (
            len(stripped) <= 150
            and _STRUCTURE_HEAD.match(probe)
            and ("分述数" in probe or "分组=" in probe)
        ):
            meta["structure_summary"] = _structure_summary(probe)
            meta["structure_removed"] += 1
            meta["removed"] += 1
            i += 1
            continue

        out.append(raw)
        i += 1

    cleaned = "\n".join(out)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, meta


def _parse_grade_from_markdown(text: str):
    """从 Markdown 中解析档位，如 'B档（良好）'。"""
    if not text:
        return None
    m = re.search(r"档位[：:\s]*([A-Ea-e]档[（(][^）)]{1,10}[）)])", text)
    if m:
        return m.group(1).strip()
    return None


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
    print(
        "[批改] 收到请求: paper_id=%s question_id=%s has_images=%s"
        % (
            payload.get("paperId") or payload.get("id"),
            payload.get("question_id"),
            bool(payload.get("has_images")),
        )
    )

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

    # 取材料：以「后端试卷文件」为权威来源。
    # APP 端使用内置离线试卷（或本地缓存），版本较旧时可能只带部分材料，若直接用 payload 覆盖，
    # 会出现「题目要求资料 1-4，却只发给模型 1 份材料」的问题。因此这里合并为：
    # 试卷材料优先（顺序不变），payload 材料只补充试卷里没有的 id。
    payload_materials = payload.get("materials") or []
    paper_materials = (paper.get("materials") if paper else []) or []

    materials: List[Dict[str, Any]] = [m for m in paper_materials if isinstance(m, dict)]
    _seen_variants = set()
    for m in materials:
        _seen_variants |= _id_variants(_material_id(m))
    for m in payload_materials:
        if not isinstance(m, dict):
            continue
        _mid = _material_id(m)
        if _mid and (_id_variants(_mid) & _seen_variants):
            continue  # 试卷里已有同 id 材料，以试卷为准
        materials.append(m)
        if _mid:
            _seen_variants |= _id_variants(_mid)

    print(
        f"[批改] paper_id={paper_id}, paper_loaded={paper is not None}, "
        f"materials_count={len(materials)} (试卷文件 {len(paper_materials)} / payload {len(payload_materials)}), "
        f"questions_count={len(questions_for_model)}, answers_keys={list(answers.keys())}"
    )
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
        # 大作文必须发全卷材料：materials 已保证试卷文件优先，这里直接用合并后的全卷
        materials_to_send = list(materials)
        print(f"[批改] 大作文题，发送材料数: {len(materials_to_send)} (试卷文件: {len(paper_materials)}, payload: {len(payload_materials)})")
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
        # 题目自报的 materialIds 可能与试卷不一致（例如 APP 内置离线包版本较旧只写了 ['m1']），
        # 因此优先以「后端试卷文件」中该题目的 materialIds 为准，取不到时再用上面合并出的 mid_set
        paper_mid_set = set()
        for q in questions_for_model:
            qid = q.get("id") or q.get("qid")
            paper_q = find_question_by_id(str(qid)) if qid else None
            ids = (paper_q or {}).get("materialIds") or (paper_q or {}).get("material_ids")
            if not ids:
                ids = q.get("materialIds") or q.get("material_ids")
            if ids:
                paper_mid_set.update(ids if isinstance(ids, list) else [ids])
        if paper_mid_set:
            mid_set = paper_mid_set
        if mid_set:
            # 用归一化 id 匹配，兼容 m1 / 1 等写法
            mid_variants = set()
            for v in mid_set:
                mid_variants |= _id_variants(v)
            materials_to_send = [m for m in materials if _id_variants(_material_id(m)) & mid_variants]
            sent_ids = [_material_id(m) for m in materials_to_send]
            sent_variants = set()
            for m in materials_to_send:
                sent_variants |= _id_variants(_material_id(m))
            missing = sorted({str(v) for v in mid_set if not (_id_variants(v) & sent_variants)})
            print(
                f"[批改] 小题，按 materialIds 筛选：题目指定 {sorted(str(v) for v in mid_set)}，"
                f"实际发送材料 id={sent_ids}，共 {len(materials_to_send)} 份"
            )
            if missing:
                print(f"[批改] 警告：题目指定但材料库中缺失的 id={missing}；当前可用材料 id={[_material_id(m) for m in materials]}")
            if not materials_to_send and materials:
                print(f"[批改] 警告：题目指定了 materialIds {sorted(str(v) for v in mid_set)}，但当前材料列表无匹配项；将发送 0 份材料，可能影响批改")
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

模块三：【多维度评分】（依据真实省考阅卷标准）
⚠️【字数说明】字数一律视为符合规定，不因字数扣分。
按以下四个维度独立评分，每个维度先给具体分数再列扣分点：
立意与思想（占总分25%）：论点是否紧扣材料核心？立意是否深刻而非泛泛？扣分项：跑题或偏题（-50%该维度）；仅复述题目未提炼（-20%）；论点与材料无关（-30%）。
结构与逻辑（占总分25%）：总分总结构是否完整？分论点是否清晰独立、相互不重叠？扣分项：无明显总论点（-20%）；分论点逻辑混乱或重叠（-20%）；缺少结论段（-15%）。
内容与论证（占总分35%）：是否化用材料原词进行有效论证？而非空洞说教或大段照抄？扣分项：未引用任何材料原词（-40%）；全段照抄材料（-30%）；论证与分论点脱节（-20%）。
语言与规范（占总分15%）：语言是否书面化、政治化？标题是否醒目？首尾是否呼应？扣分项：口语化严重（-20%）；无标题或标题与题意无关（-20%）；首尾完全不呼应（-15%）。

【档位判定标准（大作文）】
- A档（优秀）：立意精准深刻，结构完整严谨，材料充分化用，语言高度凝练 → 估分：满分×80%~90%
- B档（良好）：立意切题，结构完整，有一定材料化用，语言通顺 → 估分：满分×65%~79%
- C档（中等）：立意基本切题，结构可辨，材料使用有限，语言一般 → 估分：满分×52%~64%
- D档（待提升）：立意偏题或平庸，结构不完整，材料几乎未用 → 估分：满分×38%~51%
- E档（较差）：严重跑题或内容极度空洞 → 估分：满分×10%~37%

⚠️ 大作文A档极为罕见，给A档须在报告中明确列出全部达标依据。B档已属优秀考生水平，C档为大多数考生所在区间。评分须参考地区真实得分分布（已在上方注入）。

最后输出（格式严格固定，每项单独一行）：
档位：X档（描述）
估分区间：约M~N分（满分P分）

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
排版细则：①标杆范文每个自然段之间必须用空行分隔（即两个换行符），不可将整篇范文写成一段；②加粗格式必须成对闭合且紧贴文字：「**文字**」，「**」后不加空格、「**」前不加空格，否则星号会直接显示在页面上。
禁忌：严禁AI自己凭空捏造与给定材料毫无关联的论点。所有的论点升华必须建立在给定材料的基础之上。
"""

    # 小题批改系统提示词（Role + Input Data 说明 + Workflow + Output Constraints）
    SMALL_QUESTION_GRADING_INSTRUCTION = """# Role: 资深申论阅卷组长 & 客观题金牌讲师
你拥有10年以上的申论阅卷与教学经验。深谙各省公务员考试申论小题（概括题、分析题、提出对策题）"按点给分、见词给分、极度依赖材料原词"的阅卷规则。你的任务是像导师一样手把手教考生如何分析材料，并对考生的答案进行X光级别的优缺点诊断与升格指导。

# Input Data
真实数据见本请求末尾：材料 / 题目 / 学生答案。地区={PROVINCE_LABEL}；系统统计字数={WORD_COUNT} 字；本题满分={MAX_SCORE} 分。

# Workflow (请严格按照以下模块顺序输出)：

## 模块一：【审题关键点与材料深度解析】（授人以渔）
1. **审题关键点（破题雷达）**：一语道破本题的"作答对象"（找问题/原因/做法/意义？）、"限制条件"（字数、特定身份、范围）以及"隐含要求"（如：是否需要分类梳理？是否要求"用一段话"作答而非分条列举？）。
2. **材料深度解析（如何找原词）**：以名师视角，带领用户梳理材料逻辑。请按逻辑块演示推导过程：
   - 🔍 **材料X-X段**：主要讲了什么事情？从中可以抓取哪些"核心原词"？如何剥离具体的案例、数据等废话，将长句转化为精炼的"踩分关键词"？
3. **作答思路构建（如何排版）**：找齐要点后，给出**全文唯一的结构约定**，模块五的参考答案必须严格照它来写。按标尺要点分组（例如「主观/客观」「主体」「服务对象/依靠力量」），说明每组包含哪些要点编号，并输出下面这行固定格式的摘要（标记包在同一行，系统自动隐藏、不展示给考生，模块五仍须沿用其内容）：

   `<!--STRUCTURE_CONVENTION_START-->结构约定：分述数=N；分组=要点1-2 / 要点3-5；顺序=要点1→要点5；序号形式=一是、二是（或一、二、三 / 分述一、分述二）；段落形式=一段话 / 分条 / 总—分—总三段<!--STRUCTURE_CONVENTION_END-->`

   - N 必须 ≤ 要点总数，每个要点都必须归入且只归入一个分述；
   - 若题目要求「用一段话」，段落形式只能写「一段话」，分述用「一是…二是…」在段内串联，不能另起段落；
   - 若题目未强制一段话（如本题只要求「层次分明」），按题目真实要求选择分条或三段式，**不要自行改用一段话**；
   - 给出建议的总括句与收束句，它们也必须出现在参考答案里。
{ONE_PARAGRAPH_GUIDE}

## 模块二：【官方"踩分点"标尺设定】（确立评分标准）
**第一步——逐段扫描提炼**：按材料段落顺序，逐段标注该段可提取的踩分原词，不得跳过任何段落。
**第二步——归并列点**：将各段原词归并分类，生成标准踩分要点（本题满分 {MAX_SCORE} 分，各要点分值之和必须等于 {MAX_SCORE} 分）：
- **要点一（占比X分）**：[主旨概括句]。踩分原词：[必须是材料中出现的关键词A]、[关键词B]、[可接受的同义词]。
- **要点二（占比X分）**：[主旨概括句]。踩分原词：[必须是材料中出现的关键词C]、[关键词D]、[可接受的同义词]。
*(注：必须展示合并分类后的要点结构，揭示阅卷人手里的真实标准)*
**第三步——穷举自查**：列完要点后，逐段对照材料，确认每段的核心信息均已纳入某个要点；若发现遗漏，立即追加补充，不得省略。

## 模块三：【用户作答精准评析】（核心诊断区）
*(⚠️注意：严禁复述用户完整答案，请使用 `> 摘录用户原句` 的形式进行局部点评)*
将<用户作答>与标尺进行严格比对，直击痛点：
1. ✨ **作答优点（得分亮点）**：
   - **原词命中**：明确表扬用户精准保留了材料中的哪些"核心原词/踩分词"。
   - **结构与逻辑**：如果用户做了同类项合并、分条作答（1.2.3.），请予以肯定。
2. ❌ **作答缺点（失分痛点）**：
   - **致命漏点**：明确指出用户漏掉了哪个重要要点，并点拨他"这个词在材料的哪里，你是怎么看漏的"。
   - **逻辑混乱/未分类**：指出答案是否存在要点交叉重叠、未做归纳等问题。
   - **格式硬错误**（仅当题目有明确格式要求时必须诊断此项）：若题目要求"用一段话"但用户却分条作答（1.2.3. 或 一、二、三），直接指出此处扣格式分，并简要演示如何将其改写为连贯一段话。若用户正确写成了一段话，则评价段内连接词是否到位，是否有总括句统领。
3. 🔄 **"去水存干"压缩示范（保原词微操）**：
   - 申论小题重在"原词踩分"，格子极其宝贵。挑选用户答案中大段抄写材料具体细节、举例或修饰语过多的一句话进行靶向修改。
   - 要求：在**绝对保留材料核心"原词/踩分词"**的前提下，示范如何删去废话，提炼主干。
   - 🔴 **用户的啰嗦原句**：> [摘录原句] (占XX字)
   - 🟢 **名师去水存干版**：**[仅保留材料原词与核心主谓宾的极简短语]** (仅占XX字，点评说明删掉了哪些不给分的废话)

## 模块四：【多维度打分与卷面定级】
结合{PROVINCE_LABEL}的评分特征和系统统计字数（{WORD_COUNT} 字），进行分项评估：
- **要点分（75%）**：按"踩中要点数/总要点数"比例线性给分。每漏一个独立要点扣减该维度满分的（1/总要点数）；漏超过一半要点时该维度不超过35%满分。不允许"态度认真所以多给分"的宽松判断。（得分/总分）
- **归纳逻辑分（15%）**：仅评价分类和条理，不作为加分项——条理清晰则正常得分，混乱则按比例扣减。（得分/总分）
- **字数及格式（10%）**：{WORD_RULE}；格式硬错（如要求一段话但分条列举）扣50%该维度分；两项同时出现则该维度得0分。（得分/总分）

【档位判定标准】
- A档（优秀）：要点覆盖≥85%，原词精准，逻辑清晰，格式合规 → 估分：满分×85%~95%
- B档（良好）：要点覆盖70%~84%，原词基本命中，结构清晰 → 估分：满分×70%~84%
- C档（中等）：要点覆盖55%~69%，有明显漏点或原词替换 → 估分：满分×55%~69%
- D档（待提升）：要点覆盖40%~54%，漏点多或逻辑混乱 → 估分：满分×40%~54%
- E档（较差）：要点覆盖<40%，大量漏点或严重偏题 → 估分：满分×10%~39%

⚠️ 给分时须参考本题地区的真实得分分布。A档极其罕见，须在报告中写明所有要点均已覆盖的具体依据方可给出。B档已属较好水平，C档为多数考生所在区间。

## 模块五：【满分标杆与积累提升】（最终交付）
1. **极致参考答案**：给出一份符合题目要求的满分参考答案。要求：**最大密度地使用"材料原词"进行拼接，绝不随意替换为材料中没有的词汇**，字数绝对不可超限。
   - ⚠️ **要点完整性（防漏点硬规则）**：参考答案必须覆盖模块二中列出的**全部踩分要点**，不得因字数紧张而自行删减任何要点；若总字数超限，应优先压缩每个要点的修饰语，而非删去整个要点。
   - ⚠️ **结构一致性硬规则（最高优先级，必须遵守）**：参考答案**必须逐项沿用 1.3「结构约定」那一行**——分述数、分组方式、要点顺序、序号形式、段落形式全部一致，**不得另起一套并列序号**。
     - 1.3 的结构约定行虽被标记包裹并由系统隐藏，**其内容仍是本报告的一部分，模块五必须逐项照写**；不要复制标记，也不要另起一套结构。
     - 例：1.3 写「分述数=2；分组=要点1-2 / 要点3-5；序号=一是、二是；段落=一段话」，参考答案就只能写成「一是[要点1、2的原词]；二是[要点3、4、5的原词]」，**不能写成「一是…五是…」5 条并列**，也不能改成三段式或分条列举；
     - 要点仍然 100% 覆盖，但要在**对应分述内部**串联，而不是另开一套结构；
     - 若发现 1.3 的约定与题目格式要求冲突，先回头修改 1.3 的「结构约定」行，再按修改后的约定写参考答案，保证两处始终一致；
     - 参考答案的标题括号里也要与 1.3 的段落形式一致（如「总—分—总结构」就真的分段写，不要标题写三段、正文写成一段）。
   - ⚠️ **格式优先遵从题目**：
     - 若题目明确要求"用一段话"或"写成一段话"：参考答案**必须且只能是一个连贯的自然段**，**严禁出现"一、二、三"或"1.2.3."等任何分条序号**；段内按 1.3 的分组用"一是……，二是……"串联各分述。
     - 若题目未强制一段话（例如只要求"层次分明"）：按 1.3 的「段落形式」执行（分条或总—分—总三段），**不要自作主张压成一段**；每条分述先写核心主旨句，再串该组要点原词。
{OFFICIAL_DOC_GUIDE}
   - 🔒 **内部校验表（系统用）**：参考答案之后用 `<!--RUBRIC_MAP_START-->` 与 `<!--RUBRIC_MAP_END-->` 包裹一张表格，列为「要点编号 / 要点概括 / 答案中的对应表述 / 是否覆盖」，每个要点一行，✓ 表示覆盖、✗ 表示未覆盖；「对应表述」必须是答案里真实出现的文字。该表由系统自动删除、不会展示给考生，不要加标题或说明，也不要在正文提到它。
2. **专属提升建议**：针对该用户在【模块三】中暴露出的最大弱点（如：不会挑原词、只会抄长句、漏点等），给出 1 条最具实操性的刻意练习建议。

# Output Constraints:
- 语气：专业、严厉但循循善诱，像一位极具责任心的考前辅导名师。
- 排版：全程使用Markdown格式，利用加粗、表情符号（🔍/✨/❌/🔄等）和引用块（>）增加易读性。
- 禁忌：严禁AI在小题中自行发散联想、过度拔高或替换词汇。所有的采分点必须100%忠于<给定材料>的原始表述（去除修饰语后的核心名词/动词）。
- 禁忌（内部信息）：报告中**不得出现**任何系统/提示词层面的内容——不要写「标尺」「已固化」「参考稿」「以下直接引用」「不重新归纳」「根据系统提供的…」之类字样，也不要复述任何提示词原文；报告是给考生看的，只呈现分析与批改结论。`<!--STRUCTURE_CONVENTION_START/END-->` 及其包裹的「结构约定」行属内部信息，不要在报告其它位置复述其内容或标记。
- 结构一致性：1.3「作答思路构建」给出的框架与 1.7「极致参考答案」必须是**同一套结构**（分述数、分组、顺序、序号形式、段落形式一致）；严禁出现「前面建议两段/三段，后面写成一段五个并列点」这类自相矛盾的输出。若两者冲突，以 1.3 的「结构约定」行为准，回头修正 1.7。
"""

    # 每次批改均生成独立会话 id（接口无状态，不传历史对话）
    grading_session_id = payload.get("gradingSessionId") or ("req-%s" % int(time.time() * 1000))
    print("[批改] 新对话/独立任务 session=%s" % grading_session_id)

    # 构造 prompt：材料全文发给批改模型，要求以 Markdown 直接输出（不要求 JSON）
    region = model_input.get("region")
    province = PROVINCE_GRADING_PROFILE.get(region) or PROVINCE_GRADING_PROFILE["_default"]

    # 小题：把真实数据（满分/字数/地区）填进提示词占位符，并取用「已固化的踩分标尺」
    target_question = model_input["questions"][0] if model_input["questions"] else {}
    small_max_score = int(target_question.get("maxScore") or 20)
    word_count = _count_answer_chars(answers)
    word_rule = (
        "图片作答按每行 25 字估算，字数仅作参考、不因字数扣分"
        if answer_images
        else f"按系统统计字数（{word_count} 字）判定：超出题目上限或少于要求字数 60% 的，扣 50% 该维度分"
    )
    rubric: Optional[dict] = None
    rubric_source = ""
    if not has_essay and questions_for_model:
        try:
            rubric, rubric_source = get_or_create_rubric(
                paper_id=model_input.get("paperId") or "unknown",
                question=questions_for_model[0],
                materials=materials_to_send,
                max_score=small_max_score,
                province_label=province.get("label", ""),
            )
        except Exception as e:
            print(f"[标尺] 获取失败，本次回退为实时归纳：{e}")

    prompt_lines = []
    if has_essay:
        prompt_lines.append(ESSAY_GRADING_INSTRUCTION)
    else:
        requirement_text = " ".join(
            str(q.get("requirements") or "") + " " + str(q.get("title") or "")
            for q in model_input["questions"]
        )
        needs_one_paragraph = ("用一段话" in requirement_text) or ("写成一段话" in requirement_text)
        one_paragraph_guide = (
            "   - ⚠️ **一段话专项指导**：① 先拟一句总括句统领全段；② 段内用「一是……，二是……」"
            "或「首先……其次……再次……」串联各要点；③ 此类题若用分条序号（一、二、三 或 1.2.3.），"
            "属于格式违规，直接扣格式分。"
            if needs_one_paragraph else ""
        )
        prompt_lines.append(
            SMALL_QUESTION_GRADING_INSTRUCTION
            .replace("{PROVINCE_LABEL}", province.get("label", "通用"))
            .replace("{WORD_COUNT}", str(word_count))
            .replace("{MAX_SCORE}", str(small_max_score))
            .replace("{WORD_RULE}", word_rule)
            .replace("{ONE_PARAGRAPH_GUIDE}", one_paragraph_guide)
            .replace("{OFFICIAL_DOC_GUIDE}", OFFICIAL_DOC_GUIDE if _is_official_doc(model_input["questions"]) else "")
        )
    if region:
        if has_essay:
            prompt_lines.append(
                f"【地区评分特征】本套试卷来自：{province['label']}（{region}）。\n"
                f"- 小题评分特征：{province['small_q']}\n"
                f"- 大作文评分特征：{province['essay']}\n"
                f"- 真实得分分布参考：{province['score_dist']}\n"
                f"请严格按照上述已知特征评分，不得套用其他省份标准。"
            )
        else:
            # 小题不需要大作文特征与作文分数分布，去掉可省约 90 字符/次
            small_dist = (province.get("score_dist") or "").split("，")[0]
            prompt_lines.append(
                f"【地区评分特征】{province['label']}（{region}）：{province['small_q']}；{small_dist}。请严格按此标准评分。"
            )
    else:
        d = PROVINCE_GRADING_PROFILE["_default"]
        if has_essay:
            prompt_lines.append(
                f"【评分参考】地区未知，按通用标准评分。\n"
                f"- 小题：{d['small_q']}\n"
                f"- 大作文：{d['essay']}\n"
                f"- 分数分布参考：{d['score_dist']}"
            )
        else:
            small_dist = (d.get("score_dist") or "").split("，")[0]
            prompt_lines.append(
                f"【评分参考】地区未知，按通用标准评分：{d['small_q']}；{small_dist}。"
            )
    if not has_essay:
        if rubric:
            prompt_lines.append(_format_rubric_block(rubric, rubric_source))
        else:
            prompt_lines.append(
                "【本次未提供固化标尺】请按模块二自行归纳要点，并严格控制在 4~6 个：每个要点用「动词+名词」表述，"
                "必须给出材料原词与材料原文依据，各要点分值之和等于本题满分。"
            )
    # 输出格式 + 排版要求合并成一段（原来分三段且与模块四、Output Constraints 重复）
    prompt_lines.append(
        "请用 Markdown 直接输出分析报告（不要输出 JSON）。加粗用成对的 **文字**（前后不留空格），"
        "`>` 引用必须单独成行、勿在同一行串联多段引用。"
        "报告末尾须按以下固定格式写出档位与估分区间（系统解析用，格式不可更改）：\n"
        "档位：X档（描述）\n"
        "估分区间：约M~N分（满分P分）\n"
        "其中 X 为 A/B/C/D/E 之一，M~N 为整数区间，P 为本题满分。"
    )
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
    prompt = "\n".join(prompt_lines)

    # 小题 temperature=0 / top_p=1：要点判定要求可复现，不引入随机性；
    # 大作文 temperature=0.3 / top_p=0.90：需要一定的表达多样性
    temperature = 0.0 if not has_essay else 0.3
    top_p = 1.0 if not has_essay else 0.90
    started_at = time.time()
    model_raw, model_provider, model_name = call_grading_model(
        prompt,
        answer_images,
        temperature=temperature,
        top_p=top_p,
    )
    elapsed_ms = int((time.time() - started_at) * 1000)
    if model_raw:
        raw_body = model_raw.strip()
        if not raw_body:
            print("[批改结果] 模型返回为空文本（provider=%s model=%s）" % (model_provider, model_name))
            return _fallback_grading_result(model_input, "模型未返回内容（可能被截断或安全过滤）", model_raw)

        # 清掉不该给考生看的内容（内部标尺块、要点对应表、提示词措辞）
        body, internal = _strip_internal_sections(raw_body)
        if not body.strip():
            body = raw_body  # 清洗过度时保底，宁可多显示也不返回空白报告
        if internal.get("removed"):
            detail = f"移除内部内容 {internal['removed']} 处"
            if internal.get("map_rows"):
                detail += f"，要点对应 {internal.get('map_covered', 0)}/{internal['map_rows']}"
            if internal.get("structure_removed"):
                summary = (internal.get("structure_summary") or "-")[:60]
                detail += f"，结构约定已隐藏 {internal['structure_removed']} 处（摘要：{summary}）"
            print(f"[报告清洗] {detail}")

        # 不再解析 JSON，直接返回 Markdown 全文；尝试从正文中解析档位/估分区间供前端使用
        score, max_score = _parse_score_from_markdown(body)
        grade = _parse_grade_from_markdown(body)
        if max_score is None:
            total_max = sum((q.get("maxScore") or 100) for q in (model_input.get("questions") or []))
            max_score = total_max if total_max else 100

        _log_grading_result(
            paper_id=model_input.get("paperId") or paper_id or "-",
            question_ids=list(answers.keys()) or [str(q.get("id")) for q in model_input["questions"]],
            body=body,
            score=score,
            max_score=max_score,
            grade=grade,
            provider=model_provider,
            model_name=model_name,
            elapsed_ms=elapsed_ms,
            material_count=len(materials_to_send),
            rubric=rubric,
            rubric_source=rubric_source,
        )
        return {
            "content": body,
            "modelRawOutput": body,
            "score": score if score is not None else 0,
            "maxScore": max_score,
            "grade": grade,
            "overallEvaluation": "",
            "detailedComments": [],
            "perQuestion": {},
            "modelAnswer": "",
            "modelProvider": model_provider,
            "modelName": model_name,
        }

    print(
        "[批改结果] 无模型输出（provider=%s model=%s 用时=%dms），按失败处理"
        % (model_provider or "-", model_name or "-", elapsed_ms)
    )
    if answer_images:
        raise HTTPException(
            status_code=503,
            detail="图片批改服务暂时不可用。请稍后重试，或减少图片数量、改用文字作答后再提交。",
        )

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


def _build_openai_content_parts(
    prompt: str,
    image_data_list: List[str],
    *,
    image_detail: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """把 prompt 文本与 data URL 列表转成 OpenAI 多模态 content 数组。"""
    parts: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    for data_url in image_data_list:
        mime, b64 = _parse_data_url(data_url)
        if not b64:
            continue
        image_url: Dict[str, Any] = {"url": data_url}
        if image_detail:
            image_url["detail"] = image_detail
        parts.append({
            "type": "image_url",
            "image_url": image_url,
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


def _env_int(name: str, default: int) -> int:
    """读取正整数环境变量，非法配置时回退默认值。"""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"[模型配置] {name}={raw!r} 不是整数，使用默认值 {default}")
        return default
    return value if value > 0 else default


def _deepseek_model_name() -> str:
    return (os.getenv("DEEPSEEK_MODEL") or "deepseek-flash").strip()


def call_deepseek(
    prompt: str,
    image_data_list: Optional[List[str]] = None,
    *,
    temperature: float = 0.3,
) -> Optional[str]:
    """调用 DeepSeek 官方 OpenAI 兼容接口，支持文字和图片答案。"""
    api_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        print("[DeepSeek] 未配置 DEEPSEEK_API_KEY，跳过主模型")
        return None

    endpoint = (
        os.getenv("DEEPSEEK_CHAT_URL")
        or "https://api.deepseek.com/chat/completions"
    ).strip()
    model_name = _deepseek_model_name()
    thinking_enabled = (
        (os.getenv("DEEPSEEK_THINKING") or "disabled").strip().lower()
        == "enabled"
    )

    content: Any = prompt
    if image_data_list:
        content = _build_openai_content_parts(
            prompt,
            image_data_list,
            image_detail="high",
        )
        image_count = sum(
            1 for part in content if part.get("type") == "image_url"
        )
        print(f"[DeepSeek] 图片批改，解析成功 {image_count}/{len(image_data_list)} 张")
        if image_count == 0:
            print("[DeepSeek] 所有图片解析失败，放弃本次调用")
            return None

    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是熟悉国考、省考、事业单位申论评分标准的资深阅卷老师。"
                    "严格依据给定材料、题目要求和学生作答输出 Markdown 批改报告。"
                ),
            },
            {"role": "user", "content": content},
        ],
        "max_tokens": _env_int("DEEPSEEK_MAX_TOKENS", 32768),
        "thinking": {
            "type": "enabled" if thinking_enabled else "disabled",
        },
        "stream": False,
    }
    if thinking_enabled:
        payload["reasoning_effort"] = (
            os.getenv("DEEPSEEK_REASONING_EFFORT") or "low"
        ).strip()
    else:
        payload["temperature"] = temperature

    request_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(request_data) > 48 * 1024 * 1024:
        print("[DeepSeek] 请求体超过官方 48 MiB 限制")
        return None

    request = urllib.request.Request(
        endpoint,
        data=request_data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    timeout = _env_int("DEEPSEEK_TIMEOUT_SECONDS", 180)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
        if not raw.strip():
            print("[DeepSeek] 返回空 body")
            return None

        result = json.loads(raw)
        error = result.get("error")
        if error:
            print("[DeepSeek] API 返回错误:", error)
            return None

        choices = result.get("choices") or []
        if not choices:
            print("[DeepSeek] 响应中没有 choices")
            return None

        first = choices[0] or {}
        finish_reason = first.get("finish_reason")
        message = first.get("message") or {}
        content_text = (message.get("content") or "").strip()
        usage = result.get("usage") or {}
        print(
            "[DeepSeek] 调用完成 model=%s finish_reason=%s "
            "prompt_tokens=%s completion_tokens=%s content_length=%d"
            % (
                result.get("model") or model_name,
                finish_reason,
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
                len(content_text),
            )
        )
        if finish_reason == "length":
            print("[DeepSeek] 输出被 max_tokens 截断")
        return content_text or None
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode("utf-8", errors="replace")[:1000]
        except Exception:
            detail = ""
        print("[DeepSeek] HTTPError:", error.code, detail)
        return None
    except json.JSONDecodeError as error:
        print("[DeepSeek] 响应不是合法 JSON:", error)
        return None
    except Exception as error:
        print("[DeepSeek] 调用失败:", error)
        return None


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


def call_grading_model(
    prompt: str,
    image_data_list: Optional[List[str]] = None,
    *,
    temperature: float = 0.3,
    top_p: float = 0.9,
) -> Tuple[Optional[str], str, str]:
    """按配置调用主模型，并在失败时回退到现有模型供应商。"""
    images = image_data_list or []
    primary = (
        os.getenv("GRADING_PRIMARY_PROVIDER") or "deepseek"
    ).strip().lower()
    fallback_enabled = (
        (os.getenv("GRADING_FALLBACK_ENABLED") or "true").strip().lower()
        not in {"0", "false", "no", "off"}
    )

    if primary not in {"deepseek", "gemini", "qianduoduo"}:
        print(f"[批改模型] 未知主供应商 {primary!r}，回退到 DeepSeek")
        primary = "deepseek"

    print(
        "[批改模型] primary=%s fallback=%s images=%d"
        % (primary, fallback_enabled, len(images))
    )

    if primary == "deepseek":
        result = call_deepseek(
            prompt,
            images or None,
            temperature=temperature,
        )
        if result:
            return result, "deepseek", _deepseek_model_name()

    if primary == "gemini":
        if images:
            result = call_gemini_system_with_images(
                prompt,
                images,
                temperature=temperature,
                top_p=top_p,
            )
        else:
            result = call_gemini_system(
                prompt,
                temperature=temperature,
                top_p=top_p,
            )
        if result:
            return result, "gemini", "gemini-3-flash-preview"

    if primary == "qianduoduo":
        if images:
            result = call_qianduoduo_gemini_with_images(
                prompt,
                images,
                temperature=temperature,
                top_p=top_p,
            )
        else:
            result = call_qianduoduo_gemini(
                prompt,
                temperature=temperature,
                top_p=top_p,
            )
        if result:
            model_name = (
                os.getenv("QIANDUODUO_MODEL") or "gemini-2.5-flash"
            ).strip()
            return result, "qianduoduo", model_name

    if not fallback_enabled:
        return None, primary, ""

    if primary == "deepseek":
        print("[批改模型] DeepSeek 失败，回退 Gemini")
        if images:
            result = call_gemini_system_with_images(
                prompt,
                images,
                temperature=temperature,
                top_p=top_p,
            )
        else:
            result = call_gemini_system(
                prompt,
                temperature=temperature,
                top_p=top_p,
            )
        if result:
            return result, "gemini", "gemini-3-flash-preview"

    if primary != "qianduoduo":
        print("[批改模型] 继续回退钱多多模型")
        if images:
            result = call_qianduoduo_gemini_with_images(
                prompt,
                images,
                temperature=temperature,
                top_p=top_p,
            )
        else:
            result = call_qianduoduo_gemini(
                prompt,
                temperature=temperature,
                top_p=top_p,
            )
        if result:
            model_name = (
                os.getenv("QIANDUODUO_MODEL") or "gemini-2.5-flash"
            ).strip()
            return result, "qianduoduo", model_name

    return None, primary, ""


# 题目 Markdown 中的图片路径为 /images/...，放在所有 API 路由之后挂载
_images_dir = os.path.join(get_data_dir(), "images")
if os.path.isdir(_images_dir):
    app.mount("/images", StaticFiles(directory=_images_dir), name="images")
