#!/usr/bin/env python3
"""Remove OCR placeholder markers from sydw_*.json material/question content."""
import json
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

# 图片 OCR 占位（含 markdown / HTML 变体）
_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"<br>\s*\*\*-----\s*End of picture text\s*-----\*\*\s*<br>", re.I), ""),
    (re.compile(r"\*\*-----\s*Start of picture text\s*-----\*\*\s*<br>", re.I), ""),
    (re.compile(r"<br>\s*\*\*-----\s*End of picture text\s*-----\*\*", re.I), ""),
    (re.compile(r"\*\*-----\s*End of picture text\s*-----\*\*", re.I), ""),
    (re.compile(r"\*\*-----\s*Start of picture text\s*-----\*\*", re.I), ""),
    (re.compile(r"----- End of picture text -----", re.I), ""),
    (re.compile(r"----- Start of picture text -----", re.I), ""),
]


def _remove_ocr_leading_garbage(t: str) -> str:
    """句首 OCR 垃圾：一 "一 " 、一 “一 ” 等。"""
    t = re.sub(r"^一\s*[“\"\u201c]\s*一\s*[”\"\u201d]\s*", "", t)
    t = re.sub(r"(\n\n)一\s*[“\"\u201c]\s*一\s*[”\"\u201d]\s*", r"\1", t)
    return t


def _fix_ocr_hyphen_linebreaks(t: str) -> str:
    """OCR 误加的换行+短横线：断字粘连、假列表符；去掉单独成行的页码数字。"""
    if not t:
        return t
    # 单独成行的 1～2 位页码（OCR）
    for _ in range(12):
        prev = t
        t = re.sub(r"\n\n(\d{1,2})\n\n", "\n\n", t)
        if t == prev:
            break
    # 句读后的 "- "：删短横，保留分段
    t = re.sub(r"([。！？；…])\n\s*-\s*", r"\1\n\n", t)
    # 其余换行后的 "- "：多为断字或假项目符号，去掉换行与短横（合并到上一行）
    t = re.sub(r"\n\s*-\s*", "", t)
    # 文首行首短横
    t = re.sub(r"^-\s+", "", t)
    # OCR 残留：…… 段N：
    t = re.sub(r"……\s*段\d+[：:]\s*", "……\n\n", t)
    # 顿号后误分段（删页码/短横后常见）
    for _ in range(8):
        prev = t
        t = re.sub(r"([、])\n\n(?=[\u4e00-\u9fff])", r"\1", t)
        if t == prev:
            break
    t = re.sub(r"\n\n[ \t]+", "\n\n", t)
    t = re.sub(r"\n{4,}", "\n\n\n", t)
    return t


def _clean_ocr_noise(t: str) -> str:
    """清理 OCR 常见噪声：错位的「一」、空格断字、空引号等。"""
    t = _remove_ocr_leading_garbage(t)
    # 先处理整句级替换（顺序：长的、具体的优先）
    literal_pairs = [
        ("企业政策服务 点通 平 台", "企业政策服务“一点通”平台"),
        ("一 “一 ” 为进 步", "为进一步"),
        ('一 "一 " 为进 步', "为进一步"),
        ("一 “” 为进 步", "为进一步"),
        ("一 “ ” 为进 步", "为进一步"),
        ("重 “一 ” 一 要力量", "重要力量"),
        ("“一 ” 一 一 为了体验", "为了体验"),
        ("部 “一 ” 门", "部门"),
        ("发 一 现", "发现"),
        ("可 “一 以在平台上", "可以在平台上"),
        ("点 通”", "一点通”"),
        ("平台 一 才通知我，说 周之内", "平台才通知我，说一周之内"),
        ("“一 ” 观众丙", "观众丙"),
        ("就 一 能了解", "就能了解"),
        ("但 “一 ” 是之前", "但是之前"),
        ("留 一 心观察", "留心观察"),
        ("我 “一 ” 们会及时", "我们会及时"),
        ("“一 ” 节目录制结束后", "节目录制结束后"),
        ("65 一 万次", "65万次"),
        ("运行 年多", "运行一年多"),
        ("渠 一 道", "渠道"),
        ("落到实 一 处", "落到实处"),
        ("统 办理", "统一办理"),
        ("丰富 一 一 的工作经验", "丰富的工作经验"),
        ("再就业去向 般", "再就业去向一般"),
        ("这样 来，", "这样一来，"),
        ("点通 平 台", "一点通平台"),
        ("该 “ ” 模式", "该模式"),
        ("后顾之 ‘ ’ ‘ ’ ” 忧", "后顾之忧"),
        # 恢复「一点通」名称与常见断字（2025_10 等材料）
        ("企业政策服务 一点通平台，", "企业政策服务“一点通”平台，"),
        ("重要力量。 一点通平台全面", "重要力量。“一点通”平台全面"),
        ("重要力量。 点通 平台全面", "重要力量。“一点通”平台全面"),
        ("为了体验 一点通平台", "为了体验“一点通”平台"),
        ("查找 些文件", "查找一些文件"),
        ("发现了 些问题", "发现了一些问题"),
        ("公司在 一点通平台注册", "公司在“一点通”平台注册"),
        ("我们公司在 一点通平台注册", "我们公司在“一点通”平台注册"),
        ("政策都集中在 起", "政策都集中在一起"),
        ("前段时间 一 有个", "前段时间有个"),
        ("更细 些？", "更细一些？"),
        ("我们的 一点通”平台", "我们的“一点通”平台"),
        ("咱们市有个 一点通平台", "咱们市有个“一点通”平台"),
        ("都有 一点通平台的海报", "都有“一点通”平台的海报"),
        ("持续关注支持 一点通平台。", "持续关注支持“一点通”平台。"),
        ("对企业政策服务 一点通平台进行迭代", "对企业政策服务“一点通”平台进行迭代"),
        ("中心准备对企业政策服务 一点通平台进行迭代", "中心准备对企业政策服务“一点通”平台进行迭代"),
        ("干 巴巴的", "干巴巴的"),
        ("又很宏 观", "又很宏观"),
        ("具体何操作", "具体如何操作"),
        ("不用专门跑 趟", "不用专门跑一趟"),
        ("让高校学生看到专员岗 一 位对自身", "让高校学生看到专员岗位对自身"),
        ("为进一步扩大 支企服务专员 制度", "为进一步扩大“支企服务专员”制度"),
        ("资源 一送到企业", "资源一一送到企业"),
        ("发现 些地方确实有", "发现有些地方确实有"),
        ("消防安全方面 一 的问题", "消防安全方面的问题"),
    ]
    for old, new in literal_pairs:
        t = t.replace(old, new)

    # 正则：多轮收敛
    for _ in range(5):
        prev = t
        # 残余 「一」+ 弯引号 碎片
        t = re.sub(r"[“\"]\s*一\s*[”\"]", "", t)
        t = re.sub(r"^一\s+[“\"]\s*[”\"]\s*", "", t)
        t = re.sub(r"(\n\n)一\s+[“\"]\s*[”\"]\s*", r"\1", t)
        t = re.sub(r"进 步", "进一步", t)
        t = re.sub(r"点通 平台", "一点通平台", t)
        t = re.sub(r"专 员", "专员", t)
        t = re.sub(r"环 节", "环节", t)
        t = re.sub(r"中 心还", "中心还", t)
        t = re.sub(r"中 心邀请", "中心邀请", t)
        t = re.sub(r"中 心负责人", "中心负责人", t)
        t = re.sub(r"中 心对", "中心对", t)
        t = re.sub(r"中 心准备", "中心准备", t)
        t = re.sub(r"中 心宽敞", "中心宽敞", t)
        t = re.sub(r"中 心将", "中心将", t)
        t = re.sub(r"中 心在线上", "中心在线上", t)
        t = re.sub(r"中 心职能", "中心职能", t)
        t = re.sub(r"中 心及时", "中心及时", t)
        t = re.sub(r"中 心知道后", "中心知道后", t)
        t = re.sub(r"中 心迅速", "中心迅速", t)
        t = re.sub(r"中 心还定期", "中心还定期", t)
        t = re.sub(r"中 心服务", "中心服务", t)
        t = re.sub(r"企服务中 心", "企服务中心", t)
        t = re.sub(r"服务中 心综合", "服务中心综合", t)
        t = re.sub(r"服务中 心拟", "服务中心拟", t)
        t = re.sub(r"服务中 心在前期", "服务中心在前期", t)
        t = re.sub(r"服务中 心还是", "服务中心还是", t)
        t = re.sub(r"服务中 心向", "服务中心向", t)
        t = re.sub(r"服务中 心要", "服务中心要", t)
        t = re.sub(r"服务中 心将", "服务中心将", t)
        t = re.sub(r"服务中 心可以", "服务中心可以", t)
        t = re.sub(r"服务中 心负责", "服务中心负责", t)
        t = re.sub(r"服务中 心收到", "服务中心收到", t)
        t = re.sub(r"服务中 心组织", "服务中心组织", t)
        t = re.sub(r"服务中 心邀请", "服务中心邀请", t)
        t = re.sub(r"服务中 心对", "服务中心对", t)
        t = re.sub(r"服务中 心宽敞", "服务中心宽敞", t)
        t = re.sub(r"服务中 心知道", "服务中心知道", t)
        t = re.sub(r"服务中 心迅速", "服务中心迅速", t)
        t = re.sub(r"服务中 心还", "服务中心还", t)
        t = re.sub(r"服务中 心服务", "服务中心服务", t)
        t = re.sub(r"融媒中 心", "融媒体中心", t)
        t = re.sub(r"工信局提出，根 据", "工信局提出，根据", t)
        t = re.sub(r"大数 据", "大数据", t)
        t = re.sub(r"专 做球阀", "专做球阀", t)
        t = re.sub(r"研产销 体化", "研产销一体化", t)
        t = re.sub(r"产 一 业创新", "产业创新", t)
        t = re.sub(r"每 处细节", "每处细节", t)
        t = re.sub(r"评 一 审", "评审", t)
        t = re.sub(r"开展了 次专题", "开展了一次专题", t)
        t = re.sub(r"服 一 一 务平台", "服务平台", t)
        t = re.sub(r"这 称号", "这一称号", t)
        t = re.sub(r"唯 获 得", "唯一获得", t)
        t = re.sub(r"专 一 做球阀", "专做球阀", t)
        t = re.sub(r"是 家长期", "是一家长期", t)
        t = re.sub(r"第 时间", "第一时间", t)
        if t == prev:
            break
    # 「点」「通」被空格拆开
    t = re.sub(r"点\s+通", "点通", t)
    # 残余 “一 ” 碎片（多轮）
    for _ in range(8):
        prev = t
        t = re.sub(r"[“\"]\s*一\s*[”\"]", "", t)
        if t == prev:
            break
    # 合并因删除产生的多余空格（保留换行）
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r" \n", "\n", t)
    return t


def _collapse_cjk_internal_spaces(t: str) -> str:
    """去掉文段内汉字与汉字之间、字母数字与汉字之间的多余空格（OCR 断字）。"""
    # 不合并换行：仅空格与制表符与全角空格
    gap = r"[ \t\u3000]+"
    cjk = r"[\u4e00-\u9fff\u3001-\u303f\uff01-\uffee]"
    for _ in range(50):
        prev = t
        t = re.sub(rf"({cjk})({gap})({cjk})", r"\1\3", t)
        t = re.sub(rf"([A-Za-z0-9])({gap})({cjk})", r"\1\3", t)
        t = re.sub(rf"({cjk})({gap})([A-Za-z0-9])", r"\1\3", t)
        if t == prev:
            break
    return t


def _strip_markdown_headers(t: str) -> str:
    """去掉材料中的 Markdown 标题符号 ##（OCR/转录残留，前端不需要）。保留【】小标题文字。"""
    for _ in range(5):
        prev = t
        t = re.sub(r"(?m)^\s*#+\s*-\s*", "", t)
        t = re.sub(r"(?m)^\s*#+\s+", "", t)
        t = re.sub(r"\n\s*#+\s*-\s*", "\n\n", t)
        t = re.sub(r"\n\s*#+\s+", "\n\n", t)
        t = re.sub(r"\n+#+\s*$", "", t)
        t = re.sub(r"#+\s*$", "", t)
        t = re.sub(r"(?m)^\s*#+\s*$", "", t)
        if t == prev:
            break
    t = re.sub(r"\n{4,}", "\n\n\n", t)
    return t


def _strip_markdown_images(t: str) -> str:
    """删除 Markdown 图片占位 `![](/images/...)`；兼容无闭合括号、路径被截断的 OCR 残留。"""
    prev = None
    while prev != t:
        prev = t
        t = re.sub(r"\n*!\[[^\]]*\]\(/images/[^)]+\)", "", t)
        t = re.sub(r"\n*!\[[^\]]*\]\(/images/\s*", "", t)
    # 删图后「：」与残留 # 粘连时，勿再写回 ##（避免与去标题逻辑冲突）
    t = t.replace("：##", "：\n\n")
    return t


def _strip_pdf_page_footers(t: str) -> str:
    """去掉 PDF/OCR 单独成行的页脚，如：第3页，共13页、第3页，共1 3页、· 第4页，共13页。"""
    for _ in range(30):
        prev = t
        t = re.sub(
            r"(?m)^[·•\s\u00b7]*第\s*\d+\s*页\s*，\s*共\s*[\d\s]+\s*页\s*$",
            "",
            t,
        )
        if t == prev:
            break
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t


def _clean_string(s: str) -> str:
    t = s
    for pat, repl in _SUBS:
        t = pat.sub(repl, t)
    # 单独成行、被截断的试卷标题（常见于图注残留）
    t = re.sub(
        r"(?m)^\s*20\d{2}年.+全国事业单位联考[^。\n]*（[^）\n]*_\s*\.\.\.\s*$",
        "",
        t,
    )
    t = re.sub(r"(?m)^\s*—20\d{2}年）》。\s*$", "", t)
    t = _fix_ocr_hyphen_linebreaks(t)
    t = _clean_ocr_noise(t)
    t = _strip_markdown_headers(t)
    t = _strip_markdown_images(t)
    t = _strip_pdf_page_footers(t)
    t = _collapse_cjk_internal_spaces(t)
    # 合并多余空行
    t = re.sub(r"\n{4,}", "\n\n\n", t)
    t = re.sub(r"(<br>\s*){3,}", "<br><br>", t)
    return t.strip()


def _walk(obj):
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k == "content" and isinstance(v, str):
                obj[k] = _clean_string(v)
            else:
                _walk(v)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item)


def main() -> int:
    files = sorted(DATA.glob("sydw_*.json"))
    if not files:
        print("No sydw_*.json found", file=sys.stderr)
        return 1
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        _walk(data)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.write("\n")
        print("OK", fp.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
