"""小题标尺（rubric）固化 + 质量门禁测试。

覆盖：
1. 首次批改：好标尺（证据全部来自材料原文）→ 一次采样即通过，status=approved，注入「强制执行」措辞。
2. 同题二次批改：复用文件，不再调模型生成标尺。
3. 材料变更：旧标尺失效并重建。
4. 编造证据：质量不达标 → status=draft，注入「参考稿」措辞，且会多采样一次。
5. 多采样取优：第一次给坏标尺、第二次给好标尺 → 选中证据通过率高的那份。
6. 分值归一：要点分值之和不等于满分时自动缩放。
7. 模型返回非 JSON：安全回退为实时归纳，不落盘。
8. 审核脚本：--approve 把 draft 升级为 approved。

运行（需先安装 fastapi）：cd backend && python3 test_rubric_flow.py
"""
import json
import os
import shutil
import sys
import tempfile
import urllib.parse

import main as backend

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
import review_rubrics  # noqa: E402

GOOD_RUBRIC = json.dumps({
    "points": [
        {"no": 1, "summary": "培育农村职业经理人队伍", "keywords": ["农村职业经理人", "乡村CEO"], "score": 5,
         "evidence": "在H市Y区活跃着一批农村职业经理人", "materialId": "m1"},
        {"no": 2, "summary": "发展观鸟等乡村新业态", "keywords": ["观鸟", "新职业"], "score": 5,
         "evidence": "婺源去年接待游客逾70万人次", "materialId": "m2"},
        {"no": 3, "summary": "推广植保无人机等新技术", "keywords": ["植保无人机"], "score": 5,
         "evidence": "为250亩稻田施肥", "materialId": "m3"},
        {"no": 4, "summary": "培育民宿管家提升服务品质", "keywords": ["民宿管家"], "score": 5,
         "evidence": "小孟希望有一天能够拿到最高等级证书", "materialId": "m4"},
    ],
    "coverage": [],
}, ensure_ascii=False)

BAD_RUBRIC = json.dumps({
    "points": [
        {"no": 1, "summary": "完善乡村治理体系", "keywords": ["治理"], "score": 10,
         "evidence": "这段材料里根本没有这句话", "materialId": "m1"},
        {"no": 2, "summary": "推动城乡融合", "keywords": ["融合"], "score": 10,
         "evidence": "同样是编造的句子", "materialId": "m2"},
    ],
    "coverage": [],
}, ensure_ascii=False)

REPORT = """## 模块四：【多维度打分与卷面定级】
要点一命中，要点二未命中。
档位：C档（中等）
估分区间：约11~13分（满分20分）"""


class FakeModel:
    """rubric_payloads 按顺序返回；耗尽后重复最后一个"""

    def __init__(self, rubric_payloads=None):
        self.rubric_payloads = list(rubric_payloads or [GOOD_RUBRIC])
        self.last = None
        self.calls = []

    def __call__(self, prompt, image_data_list=None, *, temperature=0.3, top_p=0.9):
        self.calls.append({"prompt": prompt, "temperature": temperature, "top_p": top_p})
        if "制定踩分标尺" in prompt:
            payload = self.rubric_payloads.pop(0) if self.rubric_payloads else self.last
            self.last = payload
            return payload or "", "fake", "fake-model"
        return REPORT, "fake", "fake-model"

    def rubric_calls(self):
        return [c for c in self.calls if "制定踩分标尺" in c["prompt"]]

    def grade_calls(self):
        return [c for c in self.calls if "制定踩分标尺" not in c["prompt"]]


def build_payload(materials):
    paper = json.load(open("data/gwy_jiangsu_2025_C.json", encoding="utf-8"))
    q = paper["questions"][0]
    return {
        "paperId": "gwy_jiangsu_2025_C",
        "materials": materials,
        "question": {"id": q["id"], "type": q["type"], "title": q["title"], "requirements": q.get("requirements", "")},
        "answers": {q["id"]: "考生作答：" + "乡村新职业带动增收" * 20},
        "question_id": q["id"],
    }


def read_rubric(tmp, rid="gwy_jiangsu_2025_C__q1"):
    path = os.path.join(tmp, f"{rid}.json")
    return json.load(open(path, encoding="utf-8")) if os.path.isfile(path) else None


def main_test():
    paper = json.load(open("data/gwy_jiangsu_2025_C.json", encoding="utf-8"))
    mats = [m for m in paper["materials"] if m["id"] in ("m1", "m2", "m3", "m4")]

    tmp = tempfile.mkdtemp(prefix="rubrics-")
    original_dir, original_call = backend.RUBRIC_DIR, backend.call_grading_model
    backend.RUBRIC_DIR = tmp
    ok = True

    def run(model, payload=None):
        backend.call_grading_model = model
        backend.grade_essay(request=None, payload=payload or build_payload(mats))

    try:
        # 1) 首次批改：好标尺一次通过
        fake = FakeModel([GOOD_RUBRIC])
        run(fake)
        rubric = read_rubric(tmp)
        grade_prompt = fake.grade_calls()[0]["prompt"]
        cond1 = (
            len(fake.rubric_calls()) == 1
            and rubric is not None
            and rubric["status"] == "approved"
            and rubric["quality"]["verifiedRatio"] == 1.0
            and rubric["quality"]["coverageComplete"] is True
            and "严禁在报告中复述" in grade_prompt
            and "培育农村职业经理人队伍" in grade_prompt
            and fake.rubric_calls()[0]["temperature"] == 0.0
            and fake.grade_calls()[0]["temperature"] == 0.0
        )
        print(f"[{'通过' if cond1 else '失败'}] 首次批改生成达标标尺并标记 approved")
        ok &= cond1

        # 2) 二次批改：复用，不再生成
        fake2 = FakeModel([GOOD_RUBRIC])
        run(fake2)
        cond2 = len(fake2.rubric_calls()) == 0 and len(fake2.calls) == 1
        print(f"[{'通过' if cond2 else '失败'}] 同题二次批改复用标尺（模型调用 {len(fake2.calls)} 次）")
        ok &= cond2

        # 3) 材料变更：重建（直接调用 get_or_create_rubric，避开试卷文件的权威材料）
        fake3 = FakeModel([GOOD_RUBRIC])
        backend.call_grading_model = fake3
        changed = [dict(m) for m in mats]
        changed[0]["content"] = changed[0]["content"] + "（材料更新）"
        backend.get_or_create_rubric(
            paper_id="gwy_jiangsu_2025_C", question=paper["questions"][0], materials=changed, max_score=20
        )
        cond3 = len(fake3.rubric_calls()) >= 1
        print(f"[{'通过' if cond3 else '失败'}] 材料变更后重建标尺（生成 {len(fake3.rubric_calls())} 次）")
        ok &= cond3

        # 4) 编造证据：draft + 多采样
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        fake4 = FakeModel([BAD_RUBRIC])
        run(fake4)
        rubric4 = read_rubric(tmp)
        prompt4 = fake4.grade_calls()[0]["prompt"]
        cond4 = (
            rubric4 is not None
            and rubric4["status"] == "draft"
            and rubric4["quality"]["verifiedRatio"] == 0.0
            and len(fake4.rubric_calls()) == 2  # 未达标 → 再采一次
            and "参考稿" in prompt4
            and "补充要点" in prompt4
        )
        print(f"[{'通过' if cond4 else '失败'}] 编造证据 → draft + 采样 {len(fake4.rubric_calls())} 次")
        ok &= cond4

        # 5) 多采样取优：先坏后好
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        fake5 = FakeModel([BAD_RUBRIC, GOOD_RUBRIC])
        run(fake5)
        rubric5 = read_rubric(tmp)
        cond5 = (
            rubric5 is not None
            and rubric5["quality"]["verifiedRatio"] == 1.0
            and rubric5["status"] == "approved"
            and len(fake5.rubric_calls()) == 2
        )
        print(f"[{'通过' if cond5 else '失败'}] 多采样取优（选中证据通过率 {rubric5['quality']['verifiedRatio'] if rubric5 else 'N/A'}）")
        ok &= cond5

        # 6) 分值归一
        bad_scores = json.loads(GOOD_RUBRIC)
        bad_scores["points"][0]["score"] = 99
        norm = backend._normalize_rubric(bad_scores, "p", "q1", 20, "hash", ["m1"], "auto")
        cond6 = norm is not None and sum(p["score"] for p in norm["points"]) == 20
        print(f"[{'通过' if cond6 else '失败'}] 要点分值自动归一到满分（合计 {sum(p['score'] for p in norm['points']) if norm else 'N/A'}）")
        ok &= cond6

        # 7) 模型返回非 JSON → 回退
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        fake7 = FakeModel(["抱歉，我无法完成"])
        run(fake7)
        cond7 = os.listdir(tmp) == [] and len(fake7.grade_calls()) == 1
        print(f"[{'通过' if cond7 else '失败'}] 标尺生成失败时回退为实时归纳（未落盘，仍完成批改）")
        ok &= cond7

        # 8) 审核脚本：draft → approved
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        fake8 = FakeModel([BAD_RUBRIC])
        run(fake8)
        before = read_rubric(tmp)["status"]
        review_rubrics.cmd_set_status("gwy_jiangsu_2025_C__q1", "approved")
        after = read_rubric(tmp)["status"]
        cond8 = before == "draft" and after == "approved"
        print(f"[{'通过' if cond8 else '失败'}] 审核脚本升级 draft → approved（{before} → {after}）")
        ok &= cond8

        # 9) 归并：共同要点优先保留，独有要点按支持度排序
        shared = [
            {"no": 1, "summary": "培育农村职业经理人队伍", "keywords": ["农村职业经理人"], "score": 5,
             "evidence": "在H市Y区活跃着一批农村职业经理人", "materialId": "m1"},
            {"no": 2, "summary": "发展观鸟等乡村新业态", "keywords": ["观鸟"], "score": 5,
             "evidence": "婺源去年接待游客逾70万人次", "materialId": "m2"},
            {"no": 3, "summary": "推广植保无人机等新技术", "keywords": ["植保无人机"], "score": 5,
             "evidence": "为250亩稻田施肥", "materialId": "m3"},
        ]
        pool = [
            {"points": shared + [{"no": 4, "summary": "培育民宿管家", "keywords": ["民宿管家"], "score": 5,
                                  "evidence": "小孟希望有一天能够拿到最高等级证书", "materialId": "m4"}]},
            {"points": [dict(p) for p in shared] + [{"no": 4, "summary": "健全乡村人才评价机制",
                                                     "keywords": ["技能等级认定"], "score": 5,
                                                     "evidence": "通过民宿管家初级工技能等级认定考试",
                                                     "materialId": "m4"}]},
        ]
        for cand in pool:
            for p in cand["points"]:
                backend._verify_rubric_quality({"points": [p]}, mats)
        merged = backend._merge_candidate_rubrics(pool, 20, "hash", ["m1", "m2", "m3", "m4"], "p", "q1")
        summaries = [p["summary"] for p in merged["points"]] if merged else []
        cond9 = (
            merged is not None
            and all(s in summaries for s in ["培育农村职业经理人队伍", "发展观鸟等乡村新业态", "推广植保无人机等新技术"])
            and merged["mergeInfo"]["candidates"] == 2
            and sum(p["score"] for p in merged["points"]) == 20
        )
        print(f"[{'通过' if cond9 else '失败'}] 多候选归并保留共同要点（{len(summaries)} 个要点，support={merged['mergeInfo']['support'] if merged else '-'}）")
        ok &= cond9

        # 10) 累积投票模式（file 后端）：前两次不固化，第 3 次才落盘
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        os.environ["RUBRIC_VOTE_ACCUMULATE"] = "1"
        os.environ["RUBRIC_PROMOTE_AFTER"] = "3"
        os.environ["RUBRIC_SAMPLE_TIMES"] = "1"
        backend.call_grading_model = FakeModel([GOOD_RUBRIC])
        states = []
        for _ in range(3):
            backend.grade_essay(request=None, payload=build_payload(mats))
            states.append(read_rubric(tmp) is not None)
        cond10 = states == [False, False, True]
        print(f"[{'通过' if cond10 else '失败'}] 累积投票（file）：前两次不固化，第三次落盘（{states}）")
        ok &= cond10

        # 11) 累积投票（Redis/Upstash 后端）：只存聚合状态，体积恒定
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        os.environ["RUBRIC_VOTE_STORE"] = "redis"
        os.environ["UPSTASH_REDIS_REST_URL"] = "https://fake-upstash.example"
        os.environ["UPSTASH_REDIS_REST_TOKEN"] = "fake-token"
        store = {}
        writes = []

        class FakeResp:
            def __init__(self, payload):
                self.payload = payload

            def read(self):
                return self.payload

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=None):
            if req.get_method() == "POST":
                cmd = json.loads(req.data.decode("utf-8"))
                writes.append(cmd[0])
                if cmd[0] == "SET":
                    store[cmd[1]] = cmd[2]
                return FakeResp(b'{"result":"OK"}')
            key = urllib.parse.unquote(req.full_url.rsplit("/", 1)[-1])
            return FakeResp(json.dumps({"result": store.get(key)}).encode("utf-8"))

        original_urlopen = backend.urllib.request.urlopen
        backend.urllib.request.urlopen = fake_urlopen
        try:
            backend.call_grading_model = FakeModel([GOOD_RUBRIC])
            promoted = []
            for _ in range(3):
                backend.grade_essay(request=None, payload=build_payload(mats))
                promoted.append(read_rubric(tmp) is not None)
            stored = next(iter(store.values()), "")
            state = json.loads(stored) if stored else {}
            cond11 = (
                promoted == [False, False, True]
                and writes.count("SET") == 3
                and state.get("rounds") == 3
                and len(stored.encode("utf-8")) < 3000
                and len(state.get("clusters") or []) <= 12
            )
            print(
                f"[{'通过' if cond11 else '失败'}] 累积投票（Redis）：状态 {len(stored.encode('utf-8'))} 字节、"
                f"{len(state.get('clusters') or [])} 簇、rounds={state.get('rounds')}、落盘 {promoted}"
            )
            ok &= cond11
        finally:
            backend.urllib.request.urlopen = original_urlopen

        # 12) 存储不可用时降级：不影响批改
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        os.environ["UPSTASH_REDIS_REST_URL"] = ""
        backend.call_grading_model = FakeModel([GOOD_RUBRIC])
        try:
            result = backend.grade_essay(request=None, payload=build_payload(mats))
            cond12 = bool(result.get("content")) and read_rubric(tmp) is None
            print(f"[{'通过' if cond12 else '失败'}] Redis 未配置时降级为跳过投票，批改照常返回")
        except Exception as e:  # noqa: BLE001
            cond12 = False
            print(f"[失败] 降级流程抛错：{e}")
        ok &= cond12

        # 13) 内部内容清洗：标尺复述、要点对应表都不能出现在报告里
        leaky = (
            "## 模块二：官方踩分点标尺设定\n"
            "**本题已固化的踩分标尺**，共5个要点，合计20分。以下直接引用，不重新归纳。\n\n"
            "1. 要点一：坚持服务对象全覆盖\n\n"
            "### 1.8 要点对应表\n\n"
            "| 要点编号 | 要点概括 | 答案中的对应表述 | 是否覆盖 |\n"
            "| --- | --- | --- | --- |\n"
            "| 1 | 坚持服务对象全覆盖 | 「做到桩桩都要回应好」 | ✓ |\n\n"
            "## 模块四\n档位：B档（良好）\n"
        )
        clean, meta = backend._strip_internal_sections(leaky)
        cond13 = (
            "已固化" not in clean
            and "以下直接引用" not in clean
            and "要点对应表" not in clean
            and "| 要点编号" not in clean
            and "要点一：坚持服务对象全覆盖" in clean
            and "档位：B档" in clean
            and meta.get("map_rows") == 1
        )
        print(f"[{'通过' if cond13 else '失败'}] 内部内容清洗：标尺复述与要点对应表均被移除（移除 {meta.get('removed')} 处）")
        ok &= cond13

    finally:
        for k in ("RUBRIC_VOTE_ACCUMULATE", "RUBRIC_PROMOTE_AFTER", "RUBRIC_SAMPLE_TIMES",
                  "RUBRIC_VOTE_STORE", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"):
            os.environ.pop(k, None)
        backend.call_grading_model = original_call
        backend.RUBRIC_DIR = original_dir
        shutil.rmtree(tmp, ignore_errors=True)

    print("总体:", "全部通过" if ok else "存在失败")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main_test())
