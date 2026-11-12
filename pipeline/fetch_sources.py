#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""申论每日精读 · 多官媒聚合抓稿。

来源不再局限于《人民日报》电子版：人民网观点（人民时评/壹时评等）、
人民论坛网评、光明网地评线、中国经济网经点热评、共产党员网先锋文汇
均可作为范文来源。**选文第一标准是 article_structure 的严格分论点判定**，
源与栏目只是次要权重，因此跨源转载、短评、新闻消息都不会被误选。

统一输出与 fetch_rmrb.parse_article() 一致的 article dict，并补充：
  source / sourceName / sourceLabel / sourceWeight / publishedAt / structure

用法：
  python3 pipeline/fetch_sources.py --date 2026-11-12
  python3 pipeline/fetch_sources.py --date 2026-11-12 --lookback 3 --essay-only
  python3 pipeline/fetch_sources.py --sources rmrb,rmlt --out ./素材
"""
from __future__ import annotations

import argparse
import gzip
import html as html_mod
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import article_structure
import fetch_rmrb

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}

# ---------- 源配置 ----------
# container: 正文容器正则；从匹配起点向后取一段 HTML 再抽 <p>，比依赖闭合标签更稳
# url_re: 只保留符合文章 URL 形态的链接
# date_fn: 从 URL 解析发布日期；返回 None 时由文章页 meta 兜底
SOURCES = [
    {
        "id": "rmrb", "name": "人民日报", "weight": 12,
        "kind": "epaper", "column": "人民日报评论",
    },
    {
        "id": "people_opinion", "name": "人民网", "weight": 9,
        "list_urls": ["http://opinion.people.com.cn/",
                      "http://opinion.people.com.cn/GB/8213/49160/index.html"],
        "url_re": r"opinion\.people\.com\.cn/n1/\d{4}/\d{4}/c\d+-\d+\.html",
        "container": r'<div[^>]*class="rm_txt_con"[^>]*>',
        "column": "人民网观点",
    },
    {
        "id": "rmlt", "name": "人民论坛网", "weight": 10,
        "list_urls": ["https://www.rmlt.com.cn/original/"],
        "url_re": r"rmlt\.com\.cn/\d{4}/\d{4}/\d+\.shtml",
        "container": r'<div[^>]*class="article-content[^"]*"[^>]*>',
        "column": "人民论坛网评",
    },
    {
        "id": "gmw", "name": "光明网", "weight": 9,
        "list_urls": ["https://guancha.gmw.cn/", "https://guancha.gmw.cn/node_117767.htm"],
        "url_re": r"gmw\.cn/\d{4}-\d{2}/\d{2}/content_\d+\.htm",
        "container": r'<div[^>]*id="ContentPh"[^>]*>',
        "column": "地评线",
    },
    {
        "id": "ce", "name": "中国经济网", "weight": 10,
        "list_urls": ["http://views.ce.cn/", "http://views.ce.cn/main/jdrp/index.shtml"],
        "url_re": r"views\.ce\.cn/view/\w+/\d{6}/t\d{8}_\d+\.shtml",
        "container": r'<div[^>]*id="(?:article_p|articleText)"[^>]*>',
        "column": "经点热评",
    },
    {
        "id": "12371", "name": "共产党员网", "weight": 8,
        "list_urls": ["https://tougao.12371.cn/wenhui.php?fid=147&typeid=49"],
        "url_re": r"gaojian\.php\?tid=\d+",
        "container": r'<div[^>]*class="word"[^>]*>',
        "column": "先锋文汇",
    },
]
SOURCE_BY_ID = {s["id"]: s for s in SOURCES}

# 申论高频考点词
TOPIC_WORDS = [
    "改革", "基层", "治理", "民生", "群众", "人民", "干部", "作风", "实干", "担当",
    "乡村", "振兴", "农业", "创新", "科技", "人才", "教育", "就业", "消费", "文旅",
    "生态", "绿色", "文化", "文明", "法治", "营商环境", "民营", "数字化", "人工智能",
    "新质生产力", "高质量", "中国式现代化", "安全", "养老", "青年", "社区", "服务",
    "政绩观", "调研", "落实", "机制", "标准", "品牌", "开放", "信心", "活力",
]
TITLE_BONUS_WORDS = ["如何", "何以", "才能", "也是", "让", "把", "以", "从", "看", "更", "不只", "别让", "答卷", "密码", "功夫"]
NARROW_WORDS = [
    "扫黑", "除恶", "专项斗争", "贪污", "判刑", "外交", "出访", "会见", "外军",
    "战争", "军演", "导弹", "疫情", "通报", "处分", "股市", "汇率", "关税战", "球赛", "夺冠",
]
# 栏目前缀：拆出来当 column，标题只留正文
COLUMN_PREFIX_RE = re.compile(
    r"^\s*(人民论坛网评|人民论坛实评|人民时评|人民网评|壹时评|中经评论|光明网评论员|"
    r"地评线|先锋文汇|好评中国[^｜|]{0,12}|河声|经点热评|评论员观察)\s*[|｜:：]\s*"
)
COLON_PREFIX_RE = re.compile(r"^\s*([^：:|｜]{2,10})[：:]\s*")
# 明显的页面噪声段（跳过，不打断正文）
NOISE_RE = re.compile(
    r"^(?:分享|收藏|打印|纠错|请先登录|投稿须知|扫码|点击|"
    r"来源[:：]|原标题|相关新闻|共产党员网|首页|围观|评论|广告|图片来源|制图|"
    r"阅读原文|返回顶部|本文来源|特别声明|免责声明|投稿|登录|注册|字体|大中小|打印本页|关闭)"
)
# 页脚起点：遇到即停止收录，避免把「相关阅读 / 备案号 / 版权声明」当成正文段落
STOP_RE = re.compile(
    r"^(?:关于我们|人民日报社概况|人民日报社.*版权所有|人\s*民\s*网\s*股|"
    r".*版权所有.*Copyright|互联网新闻信息服务许可证|.*举报电话|.*服务邮箱|"
    r".*ICP备\d+|.*许可证.*号|.*网络出版服务许可证|初审|责编|编辑[:：]|"
    r"责任编辑|相关阅读|我要留言|分享到|本网站|网站声明)"
)
SKIP_TITLE_RE = re.compile(
    r"每日推荐|学习金句|增刊推介|征集启事|典型案例征集|^视频$|^直播$|^专题$|"
    r"图片报道|本版责编|^责编|^版面|^广告$|广告服务|更正|启事|导读|投稿|二维码"
)

MAX_ARTICLES_PER_SOURCE = 14


# ---------- 通用 HTTP / 清洗 ----------
def fetch(url: str, timeout: int = 14) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    for enc in ("utf-8", "gb18030"):
        text = raw.decode(enc, errors="replace")
        if text.count("\ufffd") < 15:
            return text
    return raw.decode("utf-8", errors="replace")


def clean_text(raw: str) -> str:
    raw = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", raw, flags=re.S | re.I)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html_mod.unescape(raw)
    raw = raw.replace("\u3000", " ").replace("\xa0", " ").replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", raw).strip()


def normalize_title(title: str) -> tuple[str, str]:
    """拆出栏目前缀，返回 (纯标题, 栏目)。"""
    t = clean_text(title)
    # 部分列表页把发布时间拼在 <a> 文本里，去掉尾部日期串
    t = re.sub(r"\s*\d{4}-\d{1,2}-\d{1,2}.*$", "", t).strip()
    col = ""
    m = COLUMN_PREFIX_RE.match(t)
    if m:
        col = m.group(1).strip()
        t = t[m.end():].strip()
    else:
        m2 = COLON_PREFIX_RE.match(t)
        if m2 and not re.search(r"[，。！？]", m2.group(1)):
            col, t = m2.group(1).strip(), t[m2.end():].strip()
    return t.strip(" |｜"), col


def clean_paragraphs(items: list[str]) -> list[str]:
    out = []
    for p in items:
        p = clean_text(p)
        if STOP_RE.search(p):
            break  # 已到页脚，后面的全是站点信息
        if len(p) < 12 or NOISE_RE.search(p):
            continue
        if re.match(r"^[\d\s\-/年月日:：.。]+$", p):
            continue
        out.append(p)
    return out


def extract_paragraphs(page: str, container: str, window: int = 30000) -> list[str]:
    m = re.search(container, page, re.I)
    block = page[m.start():m.start() + window] if m else page
    return clean_paragraphs(re.findall(r"<p[^>]*>(.*?)</p>", block, re.S))


def date_from_url(url: str) -> str | None:
    patterns = [
        (r"/n1/(\d{4})/(\d{2})(\d{2})/", "%Y%m%d"),
        (r"/(\d{4})/(\d{2})(\d{2})/\d+\.shtml", "%Y%m%d"),
        (r"/(\d{4})-(\d{2})/(\d{2})/content_", "%Y-%m-%d"),
        (r"t(\d{4})(\d{2})(\d{2})_", "%Y%m%d"),
    ]
    for pat, fmt in patterns:
        m = re.search(pat, url)
        if not m:
            continue
        g = m.groups()
        try:
            if fmt == "%Y%m%d":
                return datetime.strptime("".join(g), "%Y%m%d").strftime("%Y-%m-%d")
            return datetime.strptime("-".join(g), "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def date_from_text(text: str) -> str | None:
    """列表页把发布时间拼在 <a> 文本里时（先锋文汇），从文本提取日期。"""
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text or "")
    if m:
        try:
            return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        except ValueError:
            pass
    return None


def date_from_page(page: str) -> str | None:
    for pat in (r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})',
                r"(?:发布时间|发布日期|publishdate)[^0-9]{0,20}(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})"):
        m = re.search(pat, page, re.I)
        if m:
            g = m.groups()
            try:
                return f"{int(g[0]):04d}-{int(g[1]):02d}-{int(g[2]):02d}"
            except (ValueError, IndexError):
                continue
    return None


def absolute_url(href: str, list_url: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        m = re.match(r"(https?://[^/]+)", list_url)
        return (m.group(1) if m else "") + href
    # 相对路径：以列表页目录为基准
    base = list_url.rsplit("/", 1)[0] + "/"
    while href.startswith("../"):
        href = href[3:]
        base = base.rstrip("/").rsplit("/", 1)[0] + "/"
    return base + href.lstrip("/")


# ---------- 列表页 ----------
def list_one(cfg: dict, list_url: str) -> list[tuple[str, str]]:
    try:
        page = fetch(list_url, timeout=14)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] {cfg['id']} 列表页不可达 {list_url}: {exc}", file=sys.stderr)
        return []
    out: list[tuple[str, str]] = []
    for href, title in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
        t = clean_text(title)
        if len(t) < 8 or SKIP_TITLE_RE.search(t):
            continue
        url = absolute_url(href, list_url)
        if cfg.get("url_re") and not re.search(cfg["url_re"], url):
            continue
        out.append((t, url))
    return out


def list_source(cfg: dict) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for lu in cfg.get("list_urls", []):
        for t, u in list_one(cfg, lu):
            if u in seen:
                continue
            seen.add(u)
            pairs.append((t, u))
    # 列表页常把「热门旧文」排在前面；URL 带日期的按日期倒序优先，
    # 不带日期的（如先锋文汇）保留原顺序，避免当天新文被截断掉。
    dated, undated = [], []
    for t, u in pairs:
        d = date_from_url(u)
        (dated if d else undated).append((t, u, d))
    dated.sort(key=lambda x: x[2] or "", reverse=True)
    ordered = dated + undated
    return [(t, u) for t, u, _ in ordered[:MAX_ARTICLES_PER_SOURCE]]


# ---------- 文章页 ----------
def parse_web_article(cfg: dict, raw_title: str, url: str, fallback_date: str) -> dict | None:
    try:
        page = fetch(url, timeout=14)
    except Exception:
        return None
    title, column = normalize_title(raw_title)
    if not title or SKIP_TITLE_RE.search(title):
        return None
    paras = extract_paragraphs(page, cfg.get("container", ""))
    if len(paras) < 4:
        return None
    body = "\n".join(paras)
    author = ""
    m = re.search(r'(?:作者|文/|撰文)[:：\s]{0,6}([\u4e00-\u9fa5·]{2,12})', page)
    if m:
        author = m.group(1)
    pub = (date_from_url(url) or date_from_text(raw_title)
           or date_from_page(page) or fallback_date)
    return {
        "date": pub,
        "page": "",
        "column": column or cfg["column"],
        "title": title,
        "raw_title": raw_title,
        "author": author,
        "url": url,
        "paragraphs": paras,
        "char_count": len(re.sub(r"\s", "", body)),
        "body": body,
        "source": cfg["id"],
        "sourceName": cfg["name"],
        "sourceLabel": f"{cfg['name']}·{column or cfg['column']}",
        "sourceWeight": cfg["weight"],
    }


def collect_rmrb(date: datetime, essay_only: bool) -> list[dict]:
    """人民日报电子版：复用原脚本，补齐多源字段并由聚合器统一重新打分。"""
    try:
        arts = fetch_rmrb.collect(date, essay_only=False)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 人民日报电子版抓取失败：{exc}", file=sys.stderr)
        return []
    for a in arts:
        a.setdefault("source", "rmrb")
        a["sourceName"] = "人民日报"
        a["sourceLabel"] = f"人民日报·{a.get('column') or '评论版'}"
        a["sourceWeight"] = SOURCE_BY_ID["rmrb"]["weight"]
    return arts


# ---------- 打分（严格结构是第一权重） ----------
ESSAY_COLUMN_BONUS = {
    "人民论坛": 6, "人民时评": 6, "评论员观察": 6, "人民论坛网评": 6,
    "中经评论": 6, "经点热评": 5, "地评线": 5, "先锋文汇": 5,
    "大家谈": 4, "新知": 3, "本报评论员": 3, "社论": 3, "人民网观点": 3,
}
SHORT_COMMENT_PENALTY = {
    "今日谈": -5, "微观": -3, "人民锐评": -3, "现场评论": -3, "人民网评": -2,
    "光明微评": -3, "壹时评": -2,
}


def score(article: dict) -> float:
    st = article_structure.analyze(article["paragraphs"], article["title"], article["char_count"])
    article["structure"] = st
    strict = st.get("strict") or {}
    s = float(article.get("sourceWeight") or 5)

    # 结构分是选文的核心，权重远高于来源与栏目
    s += st["score"] * 0.55
    if st["essayLike"]:
        s += 12
    elif st["status"] == "weak":
        s -= 12
    if strict.get("pass"):
        s += 8
    if st.get("pattern") in ("并列式（句式平行）", "并列式（显性序号）", "并列式", "递进式", "辩证式"):
        s += 4
    if st.get("newsReport"):
        s -= 25

    s += ESSAY_COLUMN_BONUS.get(article.get("column"), 0)
    s += SHORT_COMMENT_PENALTY.get(article.get("column"), 0)

    n = article["char_count"]
    if 900 <= n <= 1600:
        s += 8
    elif 700 <= n < 900 or 1600 < n <= 2200:
        s += 3
    elif n < 550 or n > 2600:
        s -= 10

    hits = [w for w in TOPIC_WORDS if w in article["title"] + article["body"]]
    s += min(len(hits), 12) * 0.7
    s += sum(1 for w in TITLE_BONUS_WORDS if w in article["title"]) * 1.1
    if re.search(r"[“”\"']", article["title"]):
        s += 2
    if [w for w in NARROW_WORDS if w in article["title"] + article["body"][:400]]:
        s -= 8
    if len(article["paragraphs"]) < 5:
        s -= 6
    article["topic_hits"] = hits[:12]
    article["structure_score"] = st["score"]
    article["structure_status"] = st["status"]
    article["score"] = round(s, 2)
    return article["score"]


def title_key(title: str) -> str:
    return re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", title or "")


def dedupe(arts: list[dict]) -> list[dict]:
    """跨源转载去重：同标题保留结构分最高的一篇。"""
    best: dict[str, dict] = {}
    for a in arts:
        k = title_key(a["title"])
        if not k:
            continue
        old = best.get(k)
        if not old or (a["structure"]["score"], a.get("sourceWeight", 0)) > (
                old["structure"]["score"], old.get("sourceWeight", 0)):
            best[k] = a
    return list(best.values())


# ---------- 主入口 ----------
def collect(date: datetime, essay_only: bool = False, lookback: int = 0,
            sources: list[str] | None = None) -> list[dict]:
    """抓取 [date-lookback, date] 窗口内多个官媒的候选文章，按严格结构优先排序。

    与 fetch_rmrb.collect() 接口兼容，generate_daily.py 可直接替换调用。
    """
    wanted = date.strftime("%Y-%m-%d")
    window = {(date - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(max(0, lookback) + 1)}
    selected = [s for s in SOURCES if not sources or s["id"] in sources]
    arts: list[dict] = []

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {}
        # 电子版按版面抓，回溯最多 2 期，避免一次跑上百个请求
        epaper_back = min(max(0, lookback), 2)
        for cfg in selected:
            if cfg.get("kind") == "epaper":
                for back in range(epaper_back + 1):
                    day = date - timedelta(days=back)
                    futures[pool.submit(collect_rmrb, day, essay_only)] = cfg["id"]
                continue
            futures[pool.submit(list_source, cfg)] = cfg["id"]

        list_results: dict[str, list[tuple[str, str]]] = {}
        for fut in futures:
            sid = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] {sid} 抓取失败：{exc}", file=sys.stderr)
                res = []
            if sid == "rmrb":
                arts.extend([a for a in (res or []) if a.get("date") in window])
            else:
                list_results[sid] = res or []

    # 网站源：并发抓文章页
    jobs = []
    for sid, pairs in list_results.items():
        cfg = SOURCE_BY_ID[sid]
        for raw_title, url in pairs:
            url_date = date_from_url(url)
            if url_date and url_date not in window:
                continue  # URL 已表明是窗口外的旧文，不必请求
            jobs.append((cfg, raw_title, url, wanted))
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = pool.map(lambda j: parse_web_article(*j), jobs)
        for a in results:
            if not a:
                continue
            # 日期窗口：URL 里能解析出日期的都要落在窗口内
            if a["date"] not in window:
                continue
            arts.append(a)

    # 先打分（写入 structure），再去重：跨源转载要保留结构更完整的那篇
    for a in arts:
        score(a)
    arts = dedupe(arts)
    if essay_only:
        qualified = [a for a in arts if a["structure"]["essayLike"]]
        if qualified:
            arts = qualified
    # 当天达标文章优先；同日再按结构分与综合分排序
    arts.sort(key=lambda a: (
        a["date"] < wanted,
        -int(a["structure"]["essayLike"]),
        -a["structure"]["score"],
        -a["score"],
    ))
    return arts


def pick_date(wanted: datetime) -> datetime:
    """兼容 fetch_rmrb.pick_date()：网站源按日历日期抓，不需要回退报纸期号。"""
    return wanted


def main() -> int:
    ap = argparse.ArgumentParser(description="多官媒聚合抓稿（申论大作文结构优先）")
    ap.add_argument("--date", help="YYYY-MM-DD，默认今天")
    ap.add_argument("--lookback", type=int, default=0, help="向前回溯几天，默认 0")
    ap.add_argument("--sources", help="逗号分隔的源 id，默认全部；可选 " + ",".join(SOURCE_BY_ID))
    ap.add_argument("--essay-only", action="store_true", help="只保留严格结构达标的候选")
    ap.add_argument("--out", help="把候选清单写入该目录")
    ap.add_argument("--top", type=int, default=8, help="打印前 N 篇")
    args = ap.parse_args()

    date = datetime.strptime(args.date, "%Y-%m-%d") if args.date else datetime.now()
    srcs = [x.strip() for x in args.sources.split(",") if x.strip()] if args.sources else None
    arts = collect(date, essay_only=args.essay_only, lookback=args.lookback, sources=srcs)
    print(f"窗口 {date:%Y-%m-%d} 往前 {args.lookback} 天，共 {len(arts)} 篇候选\n")
    print(f"{'分数':>6} {'结构':>4} {'状态':<10} {'分论点':>4} {'日期':<11} 来源 / 标题")
    print("-" * 104)
    for a in arts[:args.top]:
        st = a["structure"]
        print(f"{a['score']:6.2f} {st['score']:4d} {st['status']:<10} {st['subThesisCount']:4d} "
              f"{a['date']:<11} {a['sourceLabel'][:14]:<14} {a['title'][:32]}")
    if arts:
        p = arts[0]
        print("\n=== 首选 ===")
        print(json.dumps({
            "title": p["title"], "source": p["sourceLabel"], "date": p["date"],
            "url": p["url"], "charCount": p["char_count"], "paragraphs": len(p["paragraphs"]),
            "structure": article_structure.compact(p["structure"]),
            "pattern": p["structure"].get("pattern"),
            "outline": p["structure"]["outline"],
        }, ensure_ascii=False, indent=2))
    if args.out:
        out = Path(args.out).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        (out / f"候选-{date:%Y-%m-%d}.json").write_text(
            json.dumps({"date": date.strftime("%Y-%m-%d"), "lookback": args.lookback,
                        "sources": srcs or [s["id"] for s in SOURCES], "articles": arts},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n候选清单已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
