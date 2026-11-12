#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""识别官媒评论文章是否具备「申论大作文」结构骨架。

判定目标：明确的总论点 + 三个或若干个**严格分论点**论述 + 结尾（回扣/收束）。
「严格分论点」= 段首是可独立成立的主张句（不是叙事/举例）+ 段内有展开论证
+ 各分论点之间语义不重复 + 分论点分布在首尾之间。
纯规则 + 标准库，不依赖 LLM，供 fetch_sources.py 选文打分与 generate_daily.py 写入 source.structure。

输出可直接放进 daily JSON：
  source.structure = {
    score, essayLike, status(standard|acceptable|weak),
    thesis{paragraph,sentence,signals}, subTheses[], subThesisCount,
    conclusion{paragraph,sentence,signals,titleEcho},
    paragraphCount, charCount, outline[], missing[]
  }
outline 与原文段落一一对应，角色取值为：
  总论点 / 分论点一…分论点十 / 结尾 / 引子 / 论据 / 过渡分析
"""
from __future__ import annotations

import re

CN_NUM = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]

# 总论点：开头段里的明确判断 / 主张句
THESIS_RE = re.compile(
    r"必须|应当|需要|要|离不开|唯有|方能|才能|关键在于|根本在于|核心是|本质在|"
    r"归根到底|说到底|旨在|贵在|重在|决定了|取决于|关乎|关系到|"
    r"是.{2,20}的(?:关键|基础|前提|根本|保障|必然要求|重要|应有之义)"
)
JUDGE_RE = re.compile(r"是|不是.{0,20}而是|并非|在于|意味着|标志着|要求我们")

# 分论点段首的并列 / 递进 / 视角标志
SUBTHESIS_PATTERNS = [
    r"一是", r"二是", r"三是", r"四是", r"其一", r"其二", r"其三",
    r"一方面", r"另一方面", r"首先", r"其次", r"再次", r"第一", r"第二", r"第三",
    r"既要", r"也要", r"更要", r"不仅要", r"而且要", r"不仅是", r"而且是",
    r"既是", r"也是", r"更是", r"不是.{0,14}而是", r"并非.{0,14}而是",
    r"从.{0,10}看", r"就.{0,10}而言", r"于.{0,10}而言", r"在.{0,12}上",
    r"说到底", r"归根结底",
]
SUBTHESIS_RE = re.compile("|".join(f"(?:{p})" for p in SUBTHESIS_PATTERNS))

# 段内展开论证（事例 / 数据 / 递进分析）的标志
EXAMPLE_PATTERNS = [
    r"比如", r"例如", r"以.{1,14}为例", r"数据显示", r"据统计", r"实践中",
    r"近年来", r"正是", r"这说明", r"可见", r"从.{1,12}到", r"一方面",
    r"另一方面", r"与此同时", r"反观", r"事实上",
]
EXAMPLE_RE = re.compile("|".join(f"(?:{p})" for p in EXAMPLE_PATTERNS))

# 结尾：收束 / 号召 / 愿景 / 回扣
CONCLUSION_PATTERNS = [
    r"归根结底", r"归根到底", r"总而言之", r"总之", r"说到底", r"面向未来",
    r"新征程", r"新的起点", r"展望未来", r"由此看来", r"可以说", r"定能",
    r"方能", r"必将", r"才能", r"久久为功", r"行稳致远", r"一步一个脚印",
    r"让我们", r"推动.{0,20}不断", r"让.{0,24}(?:成为|绽放|落地|释放)",
]
CONCLUSION_RE = re.compile("|".join(f"(?:{p})" for p in CONCLUSION_PATTERNS))

SHORT_JUDGE_RE = re.compile(r"是|要|需|应|必须|在于|决定|关系|离不开|才能|并非|不是|应当|让.{0,20}成为|把.{0,20}作为")

# ---------- 严格分论点判定 ----------
# 分论点句必须「亮观点」，以下开头说明这段在讲事实/举例/背景，不是分论点
NARRATIVE_HEAD_RE = re.compile(
    r"^(?:近日|日前|最近|今年以来|近年来|前不久|不久前|去年|今年|上半年|下半年|"
    r"当天|会上|现场|时下|当前|眼下|如今|曾经|过去|记者|据报道|"
    r"数据显示|据统计|例如|比如|以.{1,12}为例|在.{1,16}中|随着|当.{1,16}时|"
    r"从.{1,10}到|一位|有个|这|其|该|另|同时|此外|不过|然而|当然|事实上|"
    r"令人|值得|无独有偶|与此|正因|由此|结果|最终|于是|比如|走进|来到)"
)
# 分论点句式 A：显性并列 / 递进 / 视角标志（段首）
STRICT_MARKER_RE = re.compile(
    r"^(?:一是|二是|三是|四是|其一|其二|其三|其四|第一|第二|第三|第四|"
    r"首先|其次|再次|最后|一方面|另一方面|"
    r"既要|也要|更要|不仅要|而且要|不仅是|而且是|既是|也是|更是|"
    r"从.{1,10}(?:看|来说|来讲)|就.{1,10}而言|于.{1,10}而言|"
    r"在.{1,12}(?:上|方面|层面|维度)|另一个|除了.{1,16}之外|"
    r"说到底|归根结底|归根到底|更进一步|进一层看)"
)
# 分论点句式 B：动宾短语 + 逗号 + 主张句（先锋文汇常见：「察民情，把群众冷暖摸准。」）
TOPIC_COMMA_RE = re.compile(r"^[^，。！？；]{2,14}[，,][^。！？]{4,46}[。！？]")
# 分论点句式 C：段首判断/主张句
STRICT_JUDGE_RE = re.compile(
    r"必须|应当|要|需要|离不开|唯有|方能|才能|关键在于|根本在于|核心在|本质在|"
    r"贵在|重在|取决于|决定了|关乎|关系到|不是.{0,16}而是|并非.{0,16}而是|"
    r"是.{2,20}的(?:关键|基础|前提|根本|保障|必然要求|应有之义|重要)|"
    r"把.{2,20}(?:作为|落到|转化为)|让.{2,20}(?:成为|释放|落地)|"
    r"不能|岂能|不可|应当|应|需|得|应让|要"
)
# 段内展开论证标志（说理 / 事例 / 数据 / 正反对照 / 递进）
EXPAND_RE = re.compile(
    r"比如|例如|以.{1,14}为例|数据显示|据统计|实践中|近年来|正是|这说明|可见|"
    r"从.{1,12}到|一方面|另一方面|与此同时|反观|事实上|因此|所以|因为|"
    r"如果|只有|只要|一旦|即便|无论|不仅|而且|既|也|更|要求|意味着|"
    r"《|》|指出|提出|明确|强调|第一道|第二道|一是|二是|三是|%|％|\d+"
)
# 段首是分论点但全段只是把同一句话换着说，也判不合格（独立性与展开度在代码里算）
QUESTION_RE = re.compile(r"[？?]\s*$")
# 强主张词：即使段落以「不过/当然/同时」这类转折词开头，只要后面亮了观点，仍可作分论点
STRONG_CLAIM_RE = re.compile(
    r"必须|应当|不应|不能|不可|岂能|既要|也要|更要|不仅要|不是.{0,16}而是|"
    r"并非.{0,16}而是|关键在于|根本在于|取决于|决定了|离不开|唯有|方能|才是|"
    r"需要|要求|应当|应|需|贵在|重在|旨在|说到底"
)

# 文末非正文附注（摘编说明、责编、来源标注），不参与结构判定
NON_BODY_RE = re.compile(r"^[（(]?\s*(?:摘编自|摘自|来源[：:]|原标题|责任编辑|注[：:]|编者按)")

# 纯新闻报道 / 会议消息：即便句子像判断句，也不是申论大作文范文
NEWS_TITLE_RE = re.compile(
    r"宣讲|座谈会|会议|举行|召开|出席|会见|调研|考察|访问|开幕|闭幕|发布会|"
    r"通报|名单|公示|获奖|夺冠|签署|启动仪式|走访|慰问|授牌|揭牌|成立大会"
)
NEWS_BODY_RE = re.compile(r"本报讯|记者获悉|新华社|日电|通讯员|本报记者")


def looks_like_news(title: str, paragraphs: list[str]) -> bool:
    if NEWS_TITLE_RE.search(title or ""):
        return True
    head = "".join((p or "")[:120] for p in (paragraphs or [])[:2])
    return bool(NEWS_BODY_RE.search(head))


def first_sentence(paragraph: str, limit: int = 90) -> str:
    m = re.match(r"^[^。！？]{4,}[。！？]", paragraph)
    return (m.group(0) if m else paragraph[:limit]).strip()


def _hits(pattern: re.Pattern, text: str, limit: int = 6) -> list[str]:
    return [m.group(0) for m in pattern.finditer(text)][:limit]


def looks_like_thesis(sentence: str) -> bool:
    if not 8 <= len(sentence) <= 140:
        return False
    return bool(THESIS_RE.search(sentence) or JUDGE_RE.search(sentence))


def is_short_judgement(sentence: str) -> bool:
    s = sentence.strip("「」“”\"『』 ")
    if not 8 <= len(s) <= 90:
        return False
    return bool(SHORT_JUDGE_RE.search(s))


def title_echo(title: str, paragraph: str) -> bool:
    """标题的任意 3 字片段在段中出现，视为回扣标题。"""
    t = re.sub(r"[^\u4e00-\u9fa5]", "", title or "")
    if len(t) < 3:
        return False
    return any(t[i:i + 3] in paragraph for i in range(len(t) - 2))


def _bigrams(text: str) -> set[str]:
    """中文按字 2-gram，用于判断两个分论点是不是在重复同一句话。"""
    t = re.sub(r"[^\u4e00-\u9fa5]", "", text or "")
    return {t[i:i + 2] for i in range(len(t) - 1)}


def similarity(a: str, b: str) -> float:
    x, y = _bigrams(a), _bigrams(b)
    if not x or not y:
        return 0.0
    return len(x & y) / len(x | y)


def _paragraph_expanded(para: str) -> bool:
    """段内是否真的展开了论证，而不是只把分论点句换着说一遍。"""
    if len(para) < 70:
        return False
    sentences = [s for s in re.split(r"[。！？]", para) if len(s.strip()) >= 6]
    if len(sentences) < 2:
        return False
    # 长段落本身即有论证空间；较短段落需出现说理/事例/数据等标志
    return len(para) >= 100 or bool(EXPAND_RE.search(para))


def _subthesis_shape(sentence: str) -> str:
    """返回段首句的分论点句式；空字符串表示不是分论点句。"""
    s = sentence.strip()
    if not 8 <= len(s) <= 80 or QUESTION_RE.search(s):
        return ""
    # 显性并列/递进标志优先（「另一个…」「除了…之外」即便带转折词也是分论点）
    if STRICT_MARKER_RE.search(s):
        return "显性标志"
    strong = bool(STRONG_CLAIM_RE.search(s))
    if NARRATIVE_HEAD_RE.search(s) and not strong:
        # 「随着…」「近年来…」「不过，大家也都明白…」是背景或叙事，不算分论点
        return ""
    if TOPIC_COMMA_RE.match(s):
        head = s.split("，", 1)[0]
        # 「话题短语 + 主张句」是最典型的分论点写法（察民情，把群众冷暖摸准。）
        if 2 <= len(head) <= 14 and not NARRATIVE_HEAD_RE.search(head + "，"):
            return "话题+主张"
    if len(s) <= 60 and (strong or STRICT_JUDGE_RE.search(s)):
        return "段首判断句"
    return ""


def strict_subtheses(paras: list[str], firsts: list[str],
                     skip: set[int] | None = None) -> tuple[list[dict], list[dict]]:
    """严格筛选分论点段。

    返回 (合格分论点, 全部被考察段的诊断)。硬条件：
      1. 位于中间段（不是第 1 段、不是最后 1 段），也不能是总论点/结尾段；
      2. 段首是可独立成立的主张句（排除叙事、举例、疑问）；
      3. 段内有展开论证（≥80 字、≥2 个句子、含说理/事例标志）；
      4. 与已入选的分论点语义不重复（字 2-gram Jaccard < 0.55）。
    """
    skip = skip or set()
    n = len(paras)
    diagnostics: list[dict] = []
    accepted: list[dict] = []
    for i in range(1, max(1, n - 1)):
        para_no = i + 1
        if para_no in skip or i == 0 or i == n - 1:
            continue
        sent = firsts[i]
        shape = _subthesis_shape(sent)
        expanded = _paragraph_expanded(paras[i])
        diag = {
            "paragraph": para_no, "sentence": sent,
            "shape": shape, "expanded": expanded,
            "length": len(paras[i]), "accepted": False, "reason": "",
        }
        if not shape:
            diag["reason"] = "段首不是主张句（叙事/举例/过长/疑问）"
        elif not expanded:
            diag["reason"] = "段内无论证展开"
        else:
            dup = next((a for a in accepted if similarity(sent, a["sentence"]) >= 0.55), None)
            if dup:
                diag["reason"] = f"与第 {dup['paragraph']} 段分论点语义重复"
            else:
                diag["accepted"] = True
                accepted.append({
                    "paragraph": para_no,
                    "sentence": sent,
                    "shape": shape,
                    "signals": [shape],
                    "evidence": _hits(EXPAND_RE, paras[i], 3),
                })
        diagnostics.append(diag)
    return accepted, diagnostics


def _parallel_pattern(subs: list[dict]) -> str:
    """判断分论点之间是并列、递进、辩证还是混合，供讲义讲结构关系用。"""
    shapes = [s.get("shape") for s in subs]
    if len(shapes) < 2:
        return "无"
    if len(set(shapes)) == 1 and shapes[0] in ("显性标志", "话题+主张"):
        return "并列式（句式平行）" if shapes[0] == "话题+主张" else "并列式（显性序号）"
    joined = " ".join(s.get("sentence", "") for s in subs)
    if re.search(r"不仅|而且|既要|更要|从.{0,8}到|上半场|下半场|更进一步", joined):
        return "递进式"
    if re.search(r"不是.{0,12}而是|并非.{0,12}而是|既要|也要|一方面|另一方面", joined):
        return "辩证式"
    return "并列式"


# ---------- 申论大作文「文风」判定 ----------
# 结构达标 ≠ 像申论大作文：时评、随笔、现场评论也常具备「总—分—总」。
# 这里再从标题、开篇、分论点平行度、政论词密度、篇幅五个维度给「申论味」打分（0–100），
# 供选文时优先挑政论文，而非流畅时评。
TITLE_ESSAY_POS_RE = re.compile(
    r"赓续|传承|弘扬|凝聚|激发|培育|构建|完善|推动|深化|强化|夯实|筑牢|激活|释放|"
    r"绘就|谱写|奋力|答好|走好|开启|擘画|彰显|涵养|锻造|坚持|聚焦|锚定|统筹|"
    r"以.{1,14}为|之路|之基|新篇|答卷|篇章|新局|蓝图|根基|底色|动能|引擎|"
    r"格局|体系|机制|治理|现代化|高质量|振兴|共同富裕|新征程|新时代"
)
# 时评/口语/比喻式标题（申论大作文极少这样命题）
TITLE_ESSAY_NEG_RE = re.compile(
    r"[？?]|何以|为何|凭什么|一纸|攒得|心头事|满意事|烟火气|一池春水|追光|绳结|"
    r"之水|不断流|澎湃|更需|不妨|莫让|别让|岂能|吗$|呢$|啊$|呀$|"
    r"也[是需]|更是|又是|才算|才叫|才是|跑出|掂量|解开|拆解|何以|怎样"
)
SCENE_OPEN_RE = re.compile(
    r"沃野|麦浪|稻菽|田间地头|库点|收割机|春耕|秋收|晨曦|清晨|夜幕|走进|来到|日前|近日"
)
POLICY_WORDS = [
    "高质量发展", "以人民为中心", "治理体系", "治理能力", "新发展理念", "钉钉子", "久久为功",
    "担当作为", "为民", "宗旨", "初心", "使命", "新征程", "中国式现代化", "统筹", "机制",
    "体系", "格局", "动能", "效能", "人民立场", "根本", "鲜明", "深刻", "实践", "要求",
    "必须", "坚持", "推动", "落实", "扎实", "持续", "不断", "进一步", "着力", "聚焦",
    "锚定", "把握", "贯彻", "谋划", "推进", "深化", "强化", "夯实", "基础", "保障",
]


def _title_flavor(title: str) -> tuple[int, list[str]]:
    t = (title or "").strip()
    if not t:
        return 0, []
    score, reasons = 0, []
    clauses = [c for c in re.split(r"[，,\s、]+", t) if len(c) >= 4]
    if len(clauses) >= 2:
        score += 10
        reasons.append("双句对仗")
    if TITLE_ESSAY_POS_RE.search(t):
        score += 8
        reasons.append("政论式标题")
    if TITLE_ESSAY_NEG_RE.search(t):
        score -= 14
        reasons.append("时评/口语式标题")
    if re.search(r"[“”\"']", t):
        score -= 6
        reasons.append("引号比喻")
    return max(0, min(20, score)), reasons


def _opening_flavor(firsts: list[str], thesis: dict | None) -> tuple[int, list[str]]:
    score, reasons = 0, []
    if thesis and thesis.get("paragraph") == 1:
        score += 12
        reasons.append("总论点前置")
    elif thesis and thesis.get("paragraph") in (2, 3):
        score += 6
        reasons.append("总论点靠前")
    head = firsts[0] if firsts else ""
    if SCENE_OPEN_RE.search(head) and not THESIS_RE.search(head):
        score -= 8
        reasons.append("场景化开篇")
    return max(0, min(20, score)), reasons


def _subthesis_flavor(subs: list[dict], pattern: str) -> tuple[int, list[str]]:
    k = len(subs)
    score, reasons = 0, []
    if k >= 3:
        score += 10
        reasons.append("分论点≥3")
    elif k == 2:
        score += 4
    shapes = [s.get("shape") for s in subs]
    if k >= 3 and len(set(shapes)) == 1 and shapes[0] in ("显性标志", "话题+主张"):
        score += 10
        reasons.append("分论点句式平行")
    elif k >= 3 and "并列" in (pattern or ""):
        score += 6
    if k == 2 and "递进" in (pattern or ""):
        score -= 4
        reasons.append("仅2个递进分论点")
    return max(0, min(20, score)), reasons


def _register_flavor(text: str) -> int:
    n = len(re.sub(r"\s", "", text or "")) or 1
    hits = sum((text or "").count(w) for w in POLICY_WORDS)
    density = hits / (n / 1000.0)
    return int(round(min(15.0, density * 1.6)))


def _length_flavor(cc: int) -> int:
    if 1000 <= cc <= 1500:
        return 10
    if 900 <= cc < 1000 or 1500 < cc <= 1700:
        return 6
    if 800 <= cc < 900 or 1700 < cc <= 2000:
        return 3
    return 0


def essay_flavor(title: str, paragraphs: list[str], core: dict) -> dict:
    """衡量文章「像不像申论大作文」（0–100）：标题、开篇、分论点平行度、政论词、篇幅。"""
    paras = [p for p in (paragraphs or []) if (p or "").strip()]
    firsts = [first_sentence(p) for p in paras]
    subs = core.get("subTheses") or []
    t_score, t_reason = _title_flavor(title)
    o_score, o_reason = _opening_flavor(firsts, core.get("thesis"))
    s_score, s_reason = _subthesis_flavor(subs, core.get("pattern") or "")
    r_score = _register_flavor("".join(paras))
    l_score = _length_flavor(core.get("charCount") or 0)
    total = t_score + o_score + s_score + r_score + l_score
    value = min(100, int(round(total * 100 / 85)))
    return {
        "value": value,
        "title": t_score, "opening": o_score, "subthesis": s_score,
        "register": r_score, "length": l_score,
        "reasons": t_reason + o_reason + s_reason,
    }


def _analyze_core(paragraphs: list[str], title: str = "", char_count: int | None = None) -> dict:
    paras = [re.sub(r"\s+", " ", (p or "")).strip() for p in (paragraphs or []) if (p or "").strip()]
    n = len(paras)
    if n == 0:
        return {
            "score": 0, "essayLike": False, "status": "weak",
            "thesis": None, "subTheses": [], "subThesisCount": 0,
            "conclusion": None, "paragraphCount": 0,
            "charCount": char_count or 0, "outline": [],
            "missing": ["无正文段落"],
        }
    firsts = [first_sentence(p) for p in paras]
    cc = char_count if char_count is not None else len(re.sub(r"\s", "", "".join(paras)))

    # 1) 总论点：优先在前两段找明确主张句
    thesis = None
    for i in range(min(2, n)):
        signals = _hits(THESIS_RE, firsts[i]) + _hits(JUDGE_RE, firsts[i])
        if looks_like_thesis(firsts[i]) and signals:
            thesis = {"paragraph": i + 1, "sentence": firsts[i], "signals": signals[:5]}
            break
    if thesis is None and title_echo(title, paras[0]) and JUDGE_RE.search(firsts[0]):
        thesis = {"paragraph": 1, "sentence": firsts[0], "signals": ["标题呼应 + 判断句"]}
    if thesis is None:
        # 引子在前、总论点在第 2 段的写法（中经评论等）：短判断句或点题句
        for i in range(min(3, n)):
            sent = firsts[i]
            if len(sent) <= 48 and (JUDGE_RE.search(sent) or re.search(
                    r"答案|关键|根子|在于|取决于|藏|源于|靠的是|说到底", sent)):
                thesis = {"paragraph": i + 1, "sentence": sent,
                          "signals": ["前段短判断句 / 点题句"]}
                break

    # 2) 结尾：最后两段里找收束词或标题回扣（先定出来，分论点不占用首尾段）
    conclusion = None
    for i in range(n - 1, max(n - 3, -1), -1):
        markers = _hits(CONCLUSION_RE, paras[i])
        echo = title_echo(title, paras[i])
        if markers or echo:
            conclusion = {
                "paragraph": i + 1,
                "sentence": firsts[i],
                "signals": markers[:5] or ["标题回扣"],
                "titleEcho": echo,
            }
            break

    # 3) 严格分论点：段首主张句 + 段内展开论证 + 语义互不重复
    skip = {thesis["paragraph"] if thesis else 0,
            conclusion["paragraph"] if conclusion else 0}
    subs, diagnostics = strict_subtheses(paras, firsts, skip)
    pattern = _parallel_pattern(subs)
    rejected = [{"paragraph": d["paragraph"], "reason": d["reason"]}
                for d in diagnostics if not d["accepted"]]

    # 宽松识别结果只用于诊断对照，不参与计数与逐段角色
    loose: list[dict] = []
    for i in range(1, max(1, n - 1)):
        markers = _hits(SUBTHESIS_RE, firsts[i])
        examples = _hits(EXAMPLE_RE, paras[i])
        judge = is_short_judgement(firsts[i])
        if markers or (judge and (examples or len(paras[i]) >= 90)):
            loose.append({"paragraph": i + 1, "sentence": firsts[i]})

    # 4) 结构分（严格分论点为核心权重）
    has_head, has_tail = thesis is not None, conclusion is not None
    k = len(subs)
    in_middle = sum(1 for s in subs if 1 < s["paragraph"] < n)
    parallel = pattern != "无" and k >= 2
    strict_pass = has_head and has_tail and k >= 2 and k == in_middle

    score = 0
    if thesis:
        score += 26
    if k >= 3:
        score += 30 + min(k - 3, 3) * 3
    elif k == 2:
        score += 18
    elif k == 1:
        score += 7
    if conclusion:
        score += 18
        if conclusion["titleEcho"]:
            score += 4
    if parallel:
        score += 8                       # 分论点之间有可讲的结构关系
    if k >= 2 and all(_paragraph_expanded(paras[s["paragraph"] - 1]) for s in subs):
        score += 6                       # 每段都真的展开了论证
    if 6 <= n <= 12:
        score += 9
    elif n == 5 or 13 <= n <= 15:
        score += 4
    if 900 <= cc <= 1600:
        score += 9
    elif 700 <= cc < 900 or 1600 < cc <= 2200:
        score += 4
    if in_middle >= 2:
        score += 6
    score = min(100, score)

    # 「申论味」：结构达标之外，还要求标题/开篇/分论点/政论词/篇幅像大作文
    flavor = essay_flavor(title, paras, {
        "thesis": thesis, "subTheses": subs, "pattern": pattern, "charCount": cc,
    })
    essay_like = strict_pass and score >= 55 and flavor["value"] >= 55
    if essay_like and k >= 3 and score >= 70 and flavor["value"] >= 65:
        status = "standard"
    elif essay_like:
        status = "acceptable"
    else:
        status = "weak"

    strict_checks = {
        "head": has_head,
        "tail": has_tail,
        "subTheses": k,
        "subThesesEnough": k >= 2,
        "independent": True,   # strict_subtheses 已按相似度 0.55 去重
        "expanded": bool(subs) and all(_paragraph_expanded(paras[s["paragraph"] - 1]) for s in subs),
        "inMiddle": k == in_middle,
        "parallel": parallel,
        "paragraphsOk": 6 <= n <= 12,
        "charCountOk": 900 <= cc <= 1600,
    }
    strict = {
        "pass": strict_pass,
        "score": score,
        "subThesisCount": k,
        "pattern": pattern,
        "checks": strict_checks,
        "rejected": rejected,
        "looseSubThesisCount": len(loose),
    }

    missing = []
    if not has_head:
        missing.append("缺明确总论点")
    if k < 2:
        missing.append(f"严格分论点不足（识别到 {k} 个，需 ≥2；宽松口径 {len(loose)} 个）")
    if not has_tail:
        missing.append("缺收束/结尾")
    if not parallel:
        missing.append("分论点之间缺少并列/递进/辩证关系")
    if not strict_checks["expanded"]:
        missing.append("部分分论点段没有展开论证")
    if not 6 <= n <= 12:
        missing.append(f"段落数 {n} 偏少或偏多")
    if not 900 <= cc <= 1600:
        missing.append(f"篇幅 {cc} 字偏离 900–1600")

    # 5) 逐段结构角色（供讲义框架速览表与前端展示）
    sub_by_para = {s["paragraph"]: idx for idx, s in enumerate(subs, start=1)}
    outline: list[str] = []
    for i in range(1, n + 1):
        if thesis and i == thesis["paragraph"]:
            role = "总论点"
        elif conclusion and i == conclusion["paragraph"]:
            role = "结尾"
        elif i in sub_by_para:
            no = sub_by_para[i]
            role = f"分论点{CN_NUM[no - 1]}" if no <= len(CN_NUM) else f"分论点{no}"
        elif i == 1:
            role = "引子"
        elif EXAMPLE_RE.search(paras[i - 1]) and len(paras[i - 1]) >= 80:
            role = "论据"
        else:
            role = "过渡分析"
        outline.append(role)

    return {
        "score": score,
        "essayLike": essay_like,
        "status": status,
        "thesis": thesis,
        "subTheses": subs,
        "subThesisCount": k,
        "conclusion": conclusion,
        "paragraphCount": n,
        "charCount": cc,
        "outline": outline,
        "missing": missing,
        "pattern": pattern,
        "essayFlavor": flavor,
        "strict": strict,
        "looseSubTheses": loose,
    }


def analyze(paragraphs: list[str], title: str = "", char_count: int | None = None) -> dict:
    """对外入口：剥离附注段 → 核心判定 → 还原段号与逐段角色 → 排除新闻报道。"""
    paras = list(paragraphs or [])
    note_idx = {i for i, p in enumerate(paras) if NON_BODY_RE.match((p or "").strip())}
    body = [p for i, p in enumerate(paras) if i not in note_idx]
    core = _analyze_core(body, title, char_count)

    # body 内的 1-based 段号 → 原文的 1-based 段号
    mapping = [i + 1 for i in range(len(paras)) if i not in note_idx]

    def remap(num: int | None) -> int | None:
        return mapping[num - 1] if num and 1 <= num <= len(mapping) else num

    if core.get("thesis"):
        core["thesis"]["paragraph"] = remap(core["thesis"]["paragraph"])
    for sub in core.get("subTheses") or []:
        sub["paragraph"] = remap(sub["paragraph"])
    if core.get("conclusion"):
        core["conclusion"]["paragraph"] = remap(core["conclusion"]["paragraph"])

    # 重新按出现顺序编号分论点，避免「分论点二」开头；附注段标为「附注」
    it = iter(core.get("outline") or [])
    outline: list[str] = []
    sub_no = 0
    kept_sub_paras: set[int] = set()
    for i in range(len(paras)):
        if i in note_idx:
            outline.append("附注")
            continue
        role = next(it, "过渡分析")
        if role.startswith("分论点"):
            sub_no += 1
            role = f"分论点{CN_NUM[sub_no - 1]}" if sub_no <= len(CN_NUM) else f"分论点{sub_no}"
            kept_sub_paras.add(i + 1)
        outline.append(role)
    core["outline"] = outline
    # 计数与逐段角色保持一致：被判为总论点/结尾的段不再重复计入分论点
    core["subThesisCount"] = sub_no
    core["subTheses"] = [s for s in (core.get("subTheses") or [])
                         if s.get("paragraph") in kept_sub_paras]
    core["paragraphCount"] = len(paras)
    if core.get("strict"):
        core["strict"]["subThesisCount"] = sub_no
        core["strict"]["rejected"] = [
            {"paragraph": remap(r["paragraph"]), "reason": r["reason"]}
            for r in core["strict"].get("rejected") or []
        ]
    core["looseSubTheses"] = [
        {"paragraph": remap(s["paragraph"]), "sentence": s["sentence"]}
        for s in (core.get("looseSubTheses") or [])
    ]

    if looks_like_news(title, paras):
        core["score"] = min(core.get("score", 0), 20)
        core["essayLike"] = False
        core["status"] = "weak"
        core["newsReport"] = True
        core["missing"] = (core.get("missing") or []) + ["新闻报道/会议消息，非议论文"]
        if core.get("strict"):
            core["strict"]["pass"] = False
            core["strict"]["score"] = core["score"]
    else:
        core["newsReport"] = False
    return core


def compact(structure: dict | None) -> dict:
    """写进清单文件的精简版，避免 index-recent.json 膨胀。"""
    s = structure or {}
    return {
        "status": s.get("status") or "unknown",
        "score": s.get("score") or 0,
        "subThesisCount": s.get("subThesisCount") or 0,
        "hasThesis": bool(s.get("thesis")),
        "hasConclusion": bool(s.get("conclusion")),
        "strictPass": bool((s.get("strict") or {}).get("pass")),
        "pattern": s.get("pattern") or "无",
        "essayFlavor": (s.get("essayFlavor") or {}).get("value", 0),
    }


def main() -> None:
    """命令行检查：python3 pipeline/article_structure.py --json <抓稿原文.json>"""
    import argparse
    import json

    ap = argparse.ArgumentParser(description="检查文章是否具备申论大作文结构（总论点 + 分论点 + 结尾）")
    ap.add_argument("--json", required=True, help="抓稿 原文-YYYY-MM-DD.json，或单篇 {title,paragraphs} JSON")
    ap.add_argument("--title", help="只看标题包含该关键词的文章")
    args = ap.parse_args()

    with open(args.json, encoding="utf-8") as f:
        data = json.load(f)
    articles = data.get("articles") if isinstance(data, dict) and "articles" in data else [data]
    if args.title:
        articles = [a for a in articles if args.title in (a.get("title") or "")]

    for a in articles:
        st = analyze(a.get("paragraphs") or [], a.get("title") or "", a.get("char_count"))
        strict = st.get("strict") or {}
        print(f"[{st['score']:3d} {st['status']:10s}] "
              f"严格={'PASS' if strict.get('pass') else 'FAIL'} "
              f"总论点={'Y' if st['thesis'] else 'N'} "
              f"分论点={st['subThesisCount']}（宽松 {strict.get('looseSubThesisCount', 0)}） "
              f"结尾={'Y' if st['conclusion'] else 'N'} "
              f"关系={st.get('pattern', '无')} "
              f"新闻={'Y' if st.get('newsReport') else 'N'} | {(a.get('title') or '')[:32]}")
        print("   ", " ".join(st["outline"]))
        if strict.get("rejected"):
            print("    未入选段：", "；".join(
                f"第{r['paragraph']}段 {r['reason']}" for r in strict["rejected"][:6]))
        if st["missing"]:
            print("    待补齐：", "；".join(st["missing"]))


if __name__ == "__main__":
    main()
