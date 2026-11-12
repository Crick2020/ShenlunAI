#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""人民日报每日申论精读 · 抓稿脚本（已移植入仓库，路径全部参数化）

从人民日报电子版（paper.people.com.cn）抓取指定日期的评论类文章，
按"申论范文"选文标准打分，输出当日最值得精读的一篇及全部候选清单。

用法：
  python3 fetch_rmrb.py                         # 抓当天（当天未上线则自动回退最近一期）
  python3 fetch_rmrb.py --date 2026-11-10      # 抓指定日期
  python3 fetch_rmrb.py --out ./素材            # 把原文与候选清单写到目录
  python3 fetch_rmrb.py --top 3                # 打印前 3 篇候选的完整原文

输出文件：
  素材/原文-YYYY-MM-DD.json  全部候选 + 选中文章的完整正文（结构化）
  素材/原文-YYYY-MM-DD.md    选中文章的可读版（供 AI 或人直接精读）

generate_daily.py 会直接 import 本模块的 collect() / pick_date()，
无需经由命令行与中间文件。
"""

import argparse
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

BASE = "https://paper.people.com.cn/rmrb/pc"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 评论类栏目权重：越接近"可拆解成申论范文"的短评，权重越高
COLUMN_WEIGHT = {
    "人民论坛": 12, "人民时评": 12, "今日谈": 11, "微观": 11,
    "人民锐评": 9, "评论员观察": 8, "现场评论": 8, "大家谈": 8,
    "新知": 7, "金台随笔": 6, "本报评论员": 6, "社论": 5,
    "人民网评": 6, "来论": 3, "读者来信": 2,
}

# 申论 / 面试高频考点词，命中越多越值得精读
TOPIC_WORDS = [
    "改革", "基层", "治理", "民生", "群众", "人民", "干部", "作风", "实干", "担当",
    "乡村", "振兴", "农业", "创新", "科技", "人才", "教育", "就业", "消费", "文旅",
    "生态", "绿色", "文化", "文明", "法治", "营商环境", "民营", "数字化", "人工智能",
    "新质生产力", "高质量", "中国式现代化", "安全", "养老", "青年", "社区", "服务",
    "政绩观", "调研", "落实", "机制", "标准", "品牌", "开放", "信心", "活力",
]

# 更适合拆成「总论点 + 若干分论点 + 结尾」的长篇议论文栏目
ESSAY_COLUMN_BONUS = {
    "人民论坛": 8, "人民时评": 8, "评论员观察": 7, "大家谈": 6,
    "新知": 5, "本报评论员": 5, "社论": 4, "金台随笔": 3,
}
# 短评 / 一事一议 / 驳论栏目，结构常不规整，降权（结构分高仍可被选中）
SHORT_COMMENT_PENALTY = {
    "今日谈": -6, "微观": -3, "人民锐评": -3, "现场评论": -3, "人民网评": -2,
}

TITLE_BONUS_WORDS = ["如何", "何以", "才能", "也是", "让", "把", "以", "从", "看", "更", "不只", "别让", "量", "答卷", "密码", "功夫", "文章"]

# 过于专门的领域（专项斗争、涉外、案件通报等），可迁移到申论写作的角度少，降权
NARROW_WORDS = [
    "扫黑", "除恶", "专项斗争", "贪污", "腐败", "违纪", "案件", "犯罪嫌疑人", "判刑",
    "外交", "出访", "会见", "外军", "战争", "军演", "导弹", "疫情", "通报", "处分",
    "股市", "汇率", "关税战", "球赛", "夺冠",
]

# 明显不是文章的版面条目
SKIP_TITLE = re.compile(r"图片报道|本版责编|责编|版面|广告|更正|启事|导读|投稿|二维码|本版")


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def clean_text(raw):
    raw = re.sub(r"<script.*?</script>|<style.*?</style>", "", raw, flags=re.S | re.I)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html_mod.unescape(raw)
    raw = raw.replace("\u3000", " ").replace("\xa0", " ").replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", raw).strip()


def parse_node(date, page_no):
    """返回该版面 news-list 中的 (标题, 文章URL) 列表"""
    url = f"{BASE}/layout/{date:%Y%m}/{date:%d}/node_{page_no:02d}.html"
    try:
        page = fetch(url, timeout=15)
    except Exception:
        return []
    block = re.search(r'<ul class="news-list">(.*?)</ul>', page, re.S)
    if not block:
        return []
    out = []
    for href, title in re.findall(r'<a\s+href="([^"]*content_\d+\.html)"[^>]*>(.*?)</a>', block.group(1), re.S):
        title = clean_text(title)
        if not title or SKIP_TITLE.search(title):
            continue
        if href.startswith("../../../"):
            href = f"{BASE}/content/{date:%Y%m}/{date:%d}/" + href.split("/")[-1]
        elif href.startswith("http"):
            pass
        else:
            href = f"{BASE}/layout/{date:%Y%m}/{date:%d}/" + href.split("/")[-1]
        out.append((title, href, page_no))
    return out


def parse_article(title, url, page_no, date):
    try:
        page = fetch(url)
    except Exception:
        return None
    m = re.search(r"<!--enpcontent-->(.*?)<!--/enpcontent-->", page, re.S)
    if not m:
        return None
    paras = [clean_text(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", m.group(1), re.S)]
    paras = [p for p in paras if p]
    if not paras:
        return None

    prop = re.search(r"<!--enpproperty(.*?)/enpproperty-->", page, re.S)
    author = ""
    if prop:
        a = re.search(r"<author>(.*?)</author>", prop.group(1), re.S)
        author = clean_text(a.group(1)) if a else ""
    if not author:
        sec = re.search(r'<p class="sec">(.*?)</p>', page, re.S)
        if sec:
            author = clean_text(re.sub(r"<span.*?</span>", "", sec.group(1), flags=re.S))

    col = re.search(r"[（(]([^（）()]{2,8})[)）]\s*$", title)
    column = col.group(1).strip() if col else ""
    clean_title = re.sub(r"[（(][^（）()]{2,8}[)）]\s*$", "", title).strip()
    body = "\n".join(paras)
    return {
        "date": date.strftime("%Y-%m-%d"),
        "page": f"第 {page_no:02d} 版",
        "column": column,
        "title": clean_title,
        "raw_title": title,
        "author": author,
        "url": url,
        "paragraphs": paras,
        "char_count": len(re.sub(r"\s", "", body)),
        "body": body,
    }


def score(article):
    """综合分 = 栏目 + 申论大作文结构（第一权重）+ 篇幅 + 考点词 + 标题 - 窄领域。"""
    s = 0.0
    column = article["column"]
    s += COLUMN_WEIGHT.get(column, 1)
    n = article["char_count"]
    paras = article["paragraphs"]

    # 结构识别：总论点 + 若干分论点 + 结尾，是选文的核心标准
    st = article_structure.analyze(paras, article["title"], n)
    article["structure"] = st
    s += st["score"] * 0.30
    if st["essayLike"]:
        s += 8
    elif st["status"] == "weak":
        s -= 10
    if st.get("newsReport"):
        s -= 20

    s += ESSAY_COLUMN_BONUS.get(column, 0)
    s += SHORT_COMMENT_PENALTY.get(column, 0)

    # 大作文篇幅 1000–1600 字最理想
    if 1000 <= n <= 1600:
        s += 8
    elif 900 <= n < 1000 or 1600 < n <= 2000:
        s += 4
    elif n < 600 or n > 2400:
        s -= 8

    hits = [w for w in TOPIC_WORDS if w in article["title"] + article["body"]]
    s += min(len(hits), 12) * 0.8
    s += sum(1 for w in TITLE_BONUS_WORDS if w in article["title"]) * 1.2
    if "（" in article["raw_title"] or "(" in article["raw_title"]:
        s += 1
    if re.search(r"[“”\"']", article["title"]):
        s += 2  # 标题含比喻/引号，通常是好范文
    narrow = [w for w in NARROW_WORDS if w in article["title"] + article["body"][:400]]
    if narrow:
        s -= 7
    if len(paras) < 5:
        s -= 6
    article["narrow_hits"] = narrow
    article["topic_hits"] = hits[:12]
    article["structure_score"] = st["score"]
    article["structure_status"] = st["status"]
    article["score"] = round(s, 2)
    return article["score"]


def collect(date, essay_only: bool = False):
    """抓取并打分；essay_only=True 时只保留结构达标（总论点+≥2分论点+结尾）的候选。"""
    with ThreadPoolExecutor(max_workers=8) as pool:
        pages = list(pool.map(lambda p: parse_node(date, p), range(1, 21)))
    items = [x for page in pages for x in page]
    # 去重（同一篇文章可能在多个版面的导航里出现）
    seen = set()
    items = [x for x in items if not (x[1] in seen or seen.add(x[1]))]
    with ThreadPoolExecutor(max_workers=8) as pool:
        arts = list(pool.map(lambda t: parse_article(t[0], t[1], t[2], date), items))
    comment_pages = ("第 04 版", "第 05 版", "第 09 版")
    arts = [a for a in arts if a and (
        a["column"] in COLUMN_WEIGHT
        or (not a["column"] and a["page"] in comment_pages and 500 <= a["char_count"] <= 2000)
    )]
    for a in arts:
        score(a)
    # 新闻报道 / 会议消息不是议论文，直接排除
    arts = [a for a in arts if not a.get("structure", {}).get("newsReport")]
    if essay_only:
        qualified = [a for a in arts if a.get("structure", {}).get("essayLike")]
        if qualified:
            arts = qualified
    arts.sort(key=lambda a: (-a["score"], -a.get("structure", {}).get("score", 0)))
    return arts


def pick_date(wanted):
    """当天报纸未上线时，回退到最近一期（最多 4 天）"""
    for back in range(5):
        d = wanted - timedelta(days=back)
        try:
            page = fetch(f"{BASE}/layout/{d:%Y%m}/{d:%d}/node_05.html", timeout=12)
        except Exception:
            continue
        if "news-list" in page and "content_" in page:
            return d
    raise RuntimeError("最近 5 天的人民日报电子版均无法访问")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD，默认今天；当天未上线自动回退最近一期")
    ap.add_argument("--out", help="输出目录，写入 JSON 与 Markdown 原文")
    ap.add_argument("--top", type=int, default=1, help="打印前 N 篇完整原文，默认 1")
    ap.add_argument("--pick", help="改选文章：标题中包含该文字的候选优先作为当日精读篇目")
    ap.add_argument("--essay-only", action="store_true",
                    help="只保留结构达标（总论点 + ≥2 分论点 + 结尾）的候选")
    args = ap.parse_args()

    wanted = datetime.strptime(args.date, "%Y-%m-%d") if args.date else datetime.now()
    date = pick_date(wanted)
    arts = collect(date, essay_only=args.essay_only)
    if not arts:
        print(json.dumps({"error": "未抓到评论类文章", "date": date.strftime("%Y-%m-%d")}, ensure_ascii=False))
        sys.exit(2)

    if args.pick:
        match = next((a for a in arts if args.pick in a["title"]), None)
        if match:
            arts.remove(match)
            arts.insert(0, match)
            arts[0]["picked_by"] = "manual"
        else:
            print(f"[warn] 未找到标题含「{args.pick}」的候选，沿用自动选文", file=sys.stderr)

    result = {
        "requested_date": wanted.strftime("%Y-%m-%d"),
        "paper_date": date.strftime("%Y-%m-%d"),
        "picked": arts[0],
        "candidates": [
            {**{k: a[k] for k in ("title", "column", "page", "author", "char_count", "score", "url")},
             "structureStatus": a.get("structure", {}).get("status"),
             "structureScore": a.get("structure", {}).get("score")}
            for a in arts
        ],
        "articles": arts,
    }

    if args.out:
        out = Path(args.out).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        (out / f"原文-{date:%Y-%m-%d}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        a = arts[0]
        lines = [
            f"# {a['title']}", "",
            f"- 来源：《人民日报》{a['date']} {a['page']}" + (f"（{a['column']}）" if a["column"] else ""),
            f"- 作者：{a['author'] or '未署名'}",
            f"- 全文约 {a['char_count']} 字，共 {len(a['paragraphs'])} 段",
            f"- 原文链接：{a['url']}", "", "---", "", "## 原文", "",
        ]
        lines += [p + "\n" for p in a["paragraphs"]]
        (out / f"原文-{date:%Y-%m-%d}.md").write_text("\n".join(lines), encoding="utf-8")

    summary = {
        "paper_date": result["paper_date"],
        "picked": {k: arts[0][k] for k in ("title", "column", "page", "author", "char_count", "score", "url")},
        "structure": {k: arts[0]["structure"][k] for k in
                      ("status", "score", "subThesisCount", "missing", "outline")},
        "candidates": result["candidates"][:12],
    }
    if args.top > 1:
        summary["top_bodies"] = [{k: a[k] for k in ("title", "paragraphs")} for a in arts[:args.top]]
    else:
        summary["paragraphs"] = arts[0]["paragraphs"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
