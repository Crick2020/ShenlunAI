# 申论每日精读 · 开发与运维说明

每天从**多个官媒评论栏目**自动聚合选文，只挑**符合申论大作文规范**的一篇——有明确的总论点、若干**严格分论点**论述、以及结尾——生成「逐段原文 + 老师解析」讲义，同时发布到网站与 APP，并生成可被搜索引擎与大模型直接抓取的静态页面。来源不局限于《人民日报》；**唯一硬标准是结构**。

---

## 一、选文标准：必须是「申论大作文」结构

这是本功能的核心约束：选中的原文要能**直接当作申论大作文的骨架范本**，而不是随便一篇短评、驳论或会议新闻。来源可以来自任何一家官媒，但结构必须过硬。

| 要求 | 具体判定 |
| --- | --- |
| **明确的总论点** | 开头 1–3 段有清晰的中心判断/主张句（含「必须 / 关键在于 / 是……的根本 / 不是……而是……」等），不是只摆现象、只讲故事 |
| **若干严格分论点** | 中间 ≥2 段（理想 ≥3 段）各自独立展开一个分论点：**段首是可独立成立的主张句**、段内真的展开论证、分论点之间语义不重复、且位于总论点与结尾之间 |
| **结尾** | 末段收束全文，回扣标题或落到愿景、对策，不是戛然而止 |

### 多官媒来源（`pipeline/fetch_sources.py`）

| 源 id | 媒体 / 栏目 | 列表页 | 权重 |
| --- | --- | --- | --- |
| `rmrb` | 人民日报电子版 · 人民时评 / 人民论坛 / 评论员观察 | `paper.people.com.cn/rmrb/pc`（复用 `fetch_rmrb.py`） | 12 |
| `people_opinion` | 人民网观点 · 人民时评 / 壹时评 / 人民锐评 | `opinion.people.com.cn` | 9 |
| `rmlt` | 人民论坛网评 / 人民论坛实评 | `rmlt.com.cn/original/` | 10 |
| `gmw` | 光明网 · 地评线 / 光明网评论员 | `guancha.gmw.cn` | 9 |
| `ce` | 中国经济网 · 经点热评 / 中经评论 | `views.ce.cn` | 10 |
| `12371` | 共产党员网 · 先锋文汇 | `tougao.12371.cn/wenhui.php` | 8 |

聚合器统一做：列表页抓取 → 正文容器抽取（按源配置） → 页脚/导航清洗 → URL / 发布时间识别 → 跨源转载按标题去重 → 结构判定打分。所有源都是 `urllib` + 标准库，无鉴权、无第三方依赖；单个源失败只告警、不中断。来源与栏目只是**次要加分**，结构分才是第一权重。

新增一个源：在 `SOURCES` 里加一条配置（`id / name / weight / list_urls / url_re / container / column`），必要时在 `date_from_url()` 补一个日期正则即可。

### 自动判定（严格分论点）

`pipeline/article_structure.py` 逐段识别，纯规则、不依赖 LLM：

- **总论点**：前 3 段内的明确主张句或点题短判断句；**结尾**：末 2 段内的收束词或标题回扣。
- **严格分论点**的四条硬条件（`strict_subtheses()`）：
  1. 段首是主张句——显性标志（一是 / 首先 / 另一方面 / 既要…也要 / 从…看 / 除了…之外）、话题+主张（「察民情，把群众冷暖摸准。」）、或 ≤60 字的段首判断句；叙事/举例/疑问开头（近日、随着、例如、不过大家都明白…）一律不算；
  2. 段内真的展开论证：≥70 字、至少两个句子、含说理或事例标志（长段落 ≥100 字即视为展开）；
  3. 分论点之间字符 2-gram 相似度 < 0.55，排除「换个说法重复同一句」；
  4. 分论点位于总论点与结尾之间，不占首尾段。
- 输出结构分（0–100）、`essayLike`、`status`、逐段 `outline`、`strict.pass`、`strict.checks`、`strict.rejected`（未入选段及原因）、`looseSubThesisCount`（宽松口径对照）、`pattern`（并列式 / 递进式 / 辩证式）。
- 分档：`standard`（严格通过 + ≥3 分论点 + 结尾 + 结构关系明确，分 ≥70）、`acceptable`（严格通过 + ≥2 分论点 + 结尾，分 ≥55）、`weak`。
- **排除纯新闻报道 / 会议消息**：标题含宣讲、举行、召开等，或正文出现「本报讯 / 新华社 / 本报记者」。
- 文末「摘编自……」等附注段单独标记，不参与结构判定。

### 选文打分与优先级

`fetch_sources.score()` 把**结构分作为第一权重**（`structure.score × 0.55`，严格通过额外 +8，`weak` −12，有并列/递进/辩证关系 +4），再叠加源权重、栏目、篇幅、考点词、标题比喻、窄领域降权。**任何源、任何栏目都压不过结构不达标**。

- 选文优先级：`--pick` 人工改选 > **当天**严格达标候选 > **回溯窗口内**最近一天的严格达标文章 > 结构分最高的议论文（`partial` 兜底）。
- **多源抓稿窗口**：`collect(date, lookback=N)` 一次抓 `[date-N, date]` 窗口内全部官媒（人民日报电子版最多回溯 2 期以控制请求量），默认 `ESSAY_LOOKBACK_DAYS=5`；跨源转载按标题去重，已发布讲义按 `source.originalUrl` 去重。
- **日期如实标注**：`slug` / `doc.date` 是上新当天，`source.paperDate` 是实际文章日期；回溯时【注】开头、阅读页与静态页的黄色「选文说明」提示条、`.md` 版都会写明实际来源与日期。
- 窗口内仍无达标文章时，默认取结构分最高的一篇标 `partial` 并在讲义首段提示结构差异；`--require-essay` 严格模式下则跳过上新（首页回退上一篇）。
- `--essay-only` 只保留严格达标候选；`--sources rmrb,gmw` 可临时限定来源（GitHub Variables `DAILY_SOURCES` 可设全局默认）。

> **当前策略**：多源后每天通常有 5–20 篇严格达标文章可供挑选，因此「当天有内容 + 每篇结构完整」基本可同时保证；回溯只作为兜底。回溯天数可用 `ESSAY_LOOKBACK_DAYS`（GitHub Variables / 本地环境变量）或 `--essay-lookback` 调整，设为 0 即关闭。

```bash
# 查看一批候选文章的结构判定（不联网、不调 LLM）
python3 pipeline/article_structure.py --json "<素材>/原文-2026-11-10.json"

# 独立跑多源聚合抓稿，看候选清单与首选结构
python3 pipeline/fetch_sources.py --date 2026-11-12 --top 10
python3 pipeline/fetch_sources.py --date 2026-11-12 --lookback 3 --essay-only

# 只抓稿选文，看当天选了哪篇、来自哪家媒体、结构如何
python3 pipeline/generate_daily.py --date 2026-11-12 \
  --out frontend/public/content/daily --dry-run
```

---

## 二、内容存在哪里

**唯一权威源是 Git 仓库里的结构化 JSON**：`frontend/public/content/daily/<slug>.json`，一天一份（`slug` 为 `YYYY-MM-DD`，同日第 2 篇用 `YYYY-MM-DD-2`）。

```
frontend/public/content/daily/
├── 2026-11-10.json        # 讲义全文：原文逐字段落 + 逐段解析 + 结构骨架 + 关键词/摘要/加餐/质量报告
├── 2026-11-10-2.json
├── index.json             # 全量已发布清单（归档 / sitemap 用，含结构摘要）
├── index-recent.json      # 最近 60 篇（首页卡片 / APP 默认读）
├── index-2026.json        # 按年分片清单
└── daily.schema.json      # JSON Schema
```

- **不入库**：`public/content/raw/原文-*.json`（抓稿候选全文，可用 `--date` 复现）、`dist/` 下所有静态 HTML/MD/sitemap/RSS/llms、门禁失败的 `draft`。
- **不存后端 / 数据库**：`backend/main.py` 完全不参与内容链路，Render 只承担批改。
- **APP 的内容读取（内置优先）**：Capacitor 把 `dist/` 打进 APK，内置 JSON 是发版时的快照。`services/dailyService.ts` 在原生平台**优先读 APP 内置**的讲义（刚重新打包的测试包无需 Git push、无需联网即可看到），清单则同时比较「线上 `index-recent.json`」与「内置清单」的新鲜度，取更新的一份并合并去重：上线几天后 CI 每天上新，线上清单更新，APP 自动切到线上内容而无需发版；断网自动回退内置。因此**本地测试只需 `npm run build:mobile && cap sync android` 重新打包，不需要先 git**。国内 Nginx 仍需给 `/content/` 加 `add_header Access-Control-Allow-Origin *;` 以保证长期在线上新，否则可设 `VITE_DAILY_ONLINE_BASE` 指向 Vercel 原生域名。

## 三、数据流

```
GitHub Actions cron 00:20 UTC（北京 08:20）
  → pipeline/fetch_sources.py 聚合 6 个官媒源 + article_structure.py 严格分论点判定
  → 跨源去重 → 当天优先挑 strict.pass 的文章（无则回溯窗口）
  → pipeline/generate_daily.py 调用 DeepSeek 逐段生成解析
    （原文不经 LLM，逐字填入；实际来源标签 + 结构骨架 + pattern 随 prompt 下发）
  → pipeline/validate_daily.py 11 条质量门禁（含严格分论点、来源署名）+ 防幻觉比对
  → 写入 daily/<slug>.json，content_index.rebuild() 重建索引
  → git commit & push main → Vercel npm run build
       → vite 插件 closeBundle 预渲染 dist/daily/*.html + *.md
       → 归档页 / sitemap 分片 / rss.xml / llms.txt / llms-full.txt / robots.txt
```

三条消费路径：搜索引擎与 AI 爬虫读静态 HTML/MD（不依赖 JS）；Web SPA 读 `./content/daily/*.json`；APP 在线读同一份 JSON。

## 四、数据契约

见 `frontend/public/content/daily/daily.schema.json` 与 `frontend/types.ts` 的 `DailyLecture` / `DailyStructure` / `DailyIndexEntry`。

关键约定：

- `source.paragraphs[]` 是逐字原文，`segments[i].original.text` 必须与它**精确相等**（去空白归一化后）。
- `source.structure`：结构判定结果，含 `status` / `score` / `subThesisCount` / `outline[]` / `strict.pass` / `pattern`。`outline` 长度必须等于 `segments` 数。
- `source.sourceName` / `sourceLabel` / `sourceId`：实际媒体名、展示用来源标签、源 id；`newspaper` 保留兼容旧数据。静态页、`.md` 版、JSON-LD 的 `citation.publisher` 都按实际来源署名。
- `segments[i].analysis.structureRole`：逐段结构角色，与 `outline[i]` 一致；`function` 要与角色对应（总论点段点明中心论点，分论点段写明第几个分论点）。
- `extras.frameworkTable[].role`：框架速览表的结构角色列，必须能看出「总论点 → 若干分论点 → 结尾」的完整链条。
- `segments[i].original.html` / `analysis.html` 只含 `<p>/<strong>` 等白名单标签，由 Python 侧转义后生成，前端用 `dangerouslySetInnerHTML` 渲染。
- `summary` 是自包含的一段话（标题 + 来源 + 日期 + 考点 + 总论点/分论点），供 GEO 整段引用。
- `relatedSlugs` 由 `content_index.rebuild()` 按关键词交集自动计算，用于打散「上一篇/下一篇」长链。
- `contentHash` 供构建期增量预渲染判断；`status=draft` 不进任何索引、不生成静态页。
- `source.provenance`：`fetch_sources`（多官媒全自动，严格逐字）或 `migrated-lecture`（人工讲义迁移，以讲义正文为准）；旧数据可能为 `fetch_rmrb`。
- `source.selectionNote`：仅回溯选文时存在，写明上新当天与实际报纸日期；同时作为【注】的开头，页面和 `.md` 版都会展示。

## 四·补、API Key 在哪里配置

**抓取不需要 key**：`fetch_sources.py` / `fetch_rmrb.py` / `article_structure.py` / `--dry-run` 只用 `urllib` 抓官媒公开页面，无任何鉴权。只有**生成讲义解析**（调用 DeepSeek 逐段写老师解析）才需要。

| 场景 | 配置位置 | 说明 |
| --- | --- | --- |
| 本地命令行 | `cp .env.example .env` 后填 `DEEPSEEK_API_KEY`，或直接 `export DEEPSEEK_API_KEY=xxx` | `.env` 已被根 `.gitignore` 忽略；`llm_client.py` 只在环境变量未设置时读取，不会覆盖 CI 注入值。多环境可用 `DAILY_DOTENV_PATH=/path/to/file` 指定其它路径 |
| GitHub Actions（每日自动上新） | 仓库 **Settings → Secrets and variables → Actions**：Secrets 加 `DEEPSEEK_API_KEY`；Variables 可选 `DEEPSEEK_MODEL`、`SITE_URL`、`ESSAY_LOOKBACK_DAYS`；Secret 可选 `GEMINI_API_KEY` 作回退 | workflow 的 `env:` 段已用 `${{ secrets.* }}` / `${{ vars.* }}` 引用，**不需要改代码** |
| Vercel | **不需要 key** | Vercel 只做静态构建（预渲染已生成好的 JSON）；如需改正式域名，在 Vercel 项目设置里配 `SITE_URL` |
| Render 后端 | **不需要 key** | `backend/main.py` 只负责批改，不参与内容生成 |
| `frontend/.env.*` | **不要放** | 那是 Vite 前端变量（`VITE_API_BASE` 等），写进去会打包进浏览器导致密钥泄漏 |

可用变量：`DEEPSEEK_API_KEY`（必填）、`DEEPSEEK_MODEL`（默认 `deepseek-chat`）、`DEEPSEEK_CHAT_URL`、`GEMINI_API_KEY` / `GEMINI_ENDPOINT` / `GEMINI_MODEL`（可选回退）、`ESSAY_LOOKBACK_DAYS`。

验证是否配置成功：

```bash
# 不联网也能确认变量是否读到（Python 侧）
python3 -c "import sys; sys.path.insert(0,'pipeline'); import llm_client as c; print('key 已配置:', bool(__import__('os').getenv('DEEPSEEK_API_KEY')), '| 模型:', c.DEEPSEEK_MODEL)"
# 不需要 key 的抓稿验证
python3 pipeline/generate_daily.py --date 2026-11-11 --out frontend/public/content/daily --dry-run
```

## 五、常用命令

在仓库根目录执行：

```bash
# 1) 多源聚合抓稿（不需要 key）+ 检查候选结构
python3 pipeline/fetch_sources.py --date 2026-11-12 --top 10
python3 pipeline/fetch_sources.py --date 2026-11-12 --sources gmw,ce --lookback 2 --essay-only
python3 pipeline/article_structure.py --json "<素材>/原文-2026-11-10.json"

# 2) 只抓稿选文（不调 LLM，看选了哪篇 / 结构分 / pickedBy）
python3 pipeline/generate_daily.py --date 2026-11-10 \
  --out frontend/public/content/daily --dry-run

# 3) 本地生成当天讲义（需要 DEEPSEEK_API_KEY）
DEEPSEEK_API_KEY=xxx python3 pipeline/generate_daily.py \
  --date 2026-11-10 --out frontend/public/content/daily
# 强制只从结构达标文章里选 / 严格模式（无达标则跳过） / 改选文章 / 重做某天
DEEPSEEK_API_KEY=xxx python3 pipeline/generate_daily.py \
  --date 2026-11-10 --essay-only --out frontend/public/content/daily
DEEPSEEK_API_KEY=xxx python3 pipeline/generate_daily.py \
  --date 2026-11-10 --require-essay --out frontend/public/content/daily
# 调整回溯天数（默认 5，0 表示不回溯）/ 限定来源
DEEPSEEK_API_KEY=xxx python3 pipeline/generate_daily.py \
  --date 2026-11-10 --essay-lookback 7 --out frontend/public/content/daily
DEEPSEEK_API_KEY=xxx python3 pipeline/generate_daily.py \
  --date 2026-11-10 --sources rmlt,gmw,12371 --out frontend/public/content/daily
DEEPSEEK_API_KEY=xxx python3 pipeline/generate_daily.py \
  --date 2026-11-10 --pick "烟火气" --redo --out frontend/public/content/daily

# 4) 校验单篇 / 全量 11 条门禁
python3 pipeline/validate_daily.py --file frontend/public/content/daily/2026-11-10.json
python3 pipeline/validate_daily.py --dir frontend/public/content/daily

# 5) 重建索引（关联文章、结构摘要、contentHash、按年分片）
python3 pipeline/content_index.py --dir frontend/public/content/daily

# 6) 迁移一篇人工讲义
python3 pipeline/parse_lecture_md.py \
  --md "<原型>/讲义/2026-11-10.md" \
  --source "<原型>/素材/原文-2026-11-10.json" \
  --slug 2026-11-10 --edition 1 \
  --out frontend/public/content/daily

# 7) 前端构建与预览
cd frontend && npm run dev            # http://localhost:3000/?daily=2026-11-10
cd frontend && npm run build          # Web：含静态页 / sitemap / RSS / llms
cd frontend && npm run build:mobile   # APP：跳过静态页，裁剪内置 JSON 到最近 30 篇
cd frontend && npm run daily:prerender  # 单独重跑预渲染
```

手动触发上新：GitHub → Actions →「每日精读上新」→ Run workflow，可填 `date` / `pick` / `redo` / `require_essay` / `sources`。全局默认值在仓库 Variables 里配：`DEEPSEEK_MODEL`、`SITE_URL`、`ESSAY_LOOKBACK_DAYS`、`DAILY_SOURCES`。

## 五·补、APP 本地测试（不需要先 git）

APP 的讲义正文**优先读 APK 内置**的 JSON（`dailyService.getDaily()`），只有内置缺失时才在线补；清单会同时比较「线上」与「内置」的新鲜度，取更新的一份并合并去重。因此：

- **本地重新打包就能看到新内容，不需要 git push、不需要 Vercel 部署、甚至不需要联网**。
- 上线运行几天后，CI 每天上新使线上清单更新，APP 会自动切到线上内容，无需再发版。
- 断网时自动回退内置最近 30 篇。

本地构建（**需要 JDK 21**，Capacitor 8 的 `sourceCompatibility` 是 21；JDK 17 会报「无效的源发行版：21」；另需 Android SDK）：

```bash
cd frontend
npm run android:sync                 # = papers:bundle + build:mobile + cap sync android
cd android && ./build-debug.sh       # 一键脚本：自动找 JDK / 写 local.properties / assembleDebug
# 产物：android/app/build/outputs/apk/debug/app-debug.apk
```

`build-debug.sh` 的 JDK 查找顺序：已导出的 `JAVA_HOME` → `frontend/node_modules/.cache/jdk`（项目内，已 gitignore）→ Android Studio 自带 JBR → Homebrew。Android SDK 取 `ANDROID_HOME` 或 `~/Library/Android/sdk`。

> 本次已实际打出 Debug APK：`artifacts/AixueShenlun-1.0.7-debug.apk`（19 MB，包名 `com.aixue.shenlun`，versionCode 8，minSdk 24 / targetSdk 36），内置 2 篇讲义 + 547 份离线试卷。

`cap sync android` 会把 `dist/` 复制到 `android/app/src/main/assets/public/`；`webDir` 在 `capacitor.config.ts` 里是 `dist`。当前工作区的 Android 工程已完成同步，内置 2 篇讲义与 546 份离线试卷。

> 若只需看 Web/SPA 效果，不必打 APK：`cd frontend && npm run dev`，或起静态服务指向 `dist/` 后访问 `/?daily=2026-11-10`。
> 沙箱环境若拦截 Vite 清空 `dist/` 或 esbuild 临时目录，可用 `--outDir dist/_build_mobile`（全新目录）并把 `TMPDIR` 指到项目内目录来绕开。

## 六、内容生产 SOP（自动 + 人工兜底）

1. 每天 08:20（北京时间）自动从 6 个官媒聚合抓稿；单个源失败只告警不中断，`summary`/【注】按实际 `paper_date` 与 `sourceLabel` 生成。
2. **先做严格分论点判定，再选文**：排除新闻报道，优先 `strict.pass` 的 `standard` / `acceptable` 文章；当天无达标则在回溯窗口内找最近一天达标且未用过的文章并写入选文说明；`--essay-lookback` 控制窗口，`--sources` 可限定来源，`--require-essay` 则窗口内无达标直接跳过；`--pick "标题关键词"` 人工改选优先。
3. **原文段落直接来自抓稿 JSON，不交给 LLM**；模型只逐段生成解析，返回必须是原文子串的 `highlights`，以及照抄结构骨架的 `structureRole`。
4. 讲义按结构拆解：总论点段讲怎么亮观点、分论点段讲第几个分论点及其与总论点的关系、结尾段讲怎么收束回扣；框架速览表带 `role` 列。
5. 11 条质量自检自动执行（第 9 条结构骨架、第 10 条严格分论点、第 11 条来源署名与回链）；失败回灌 prompt 定向重生成最多 2 轮。
6. 仍失败 → `status=draft`，不进索引、不 commit、不预渲染；首页自动回退上一篇已发布内容，Actions 留下 artifact 与失败摘要。
7. 重做某天：`--date 2026-11-09 --redo`；补抓往期：`--date 2026-11-09`。

## 七、SEO / GEO 说明

- 每篇有稳定 URL `/daily/<slug>.html`，正文完整直出、不依赖 JS；另有 `/daily/<slug>.md` 纯文本版。
- 静态页与 `.md` 版都**直出「申论大作文结构骨架」**：总论点所在段、分论点数量与段号、结尾段、逐段结构角色、**严格分论点判定与并列/递进/辩证关系**，便于搜索引擎与大模型整段引用；阅读页头部与每段原文块也有结构标签，框架速览表含「结构角色」列。
- 静态页包含独立 title/description/canonical、OG/Twitter、`Article` JSON-LD（含 `citation`/`isBasedOn` 按实际媒体署名并回链原刊）、`BreadcrumbList`、`FAQPage`、语义化 `<article>/<section>/<time>/<blockquote>/<table>`。
- `sitemap.xml` 为索引 + 按年分片（Google 单文件上限 5 万 URL / 50 MB）；`rss.xml` 最近 20 篇；`llms.txt` 控制在 2000 字内，全量放 `llms-full.txt`。
- `lastmod` / `dateModified` 取 `generatedAt`，**不用构建时间**，避免全站每天被误判为更新。
- SPA 阅读页 `/?daily=<slug>` 动态注入 canonical 指向静态页，避免重复内容。
- 所有 `<loc>` / canonical / OG 统一使用 `SITE_URL = https://shenlun.zaoxin.fun`。

## 八、规模演进

每篇 JSON 约 30–50 KB。3000 篇（约 8 年）Git 仓库约 150 MB，远低于 GitHub 官方「理想 < 1 GB」建议，**Git 本身不会卡**。真正需要防的是：

| 环节 | 已内置的策略 |
| --- | --- |
| APK 体积 | mobile 构建裁掉 30 篇之外的内置 JSON，清单只留最近 60 条 |
| Vercel 构建耗时 | 每篇 `contentHash`，生成器跳过未变化篇目；超过 1000 篇时启用构建缓存/增量生成 |
| 清单膨胀 | `index-recent.json` + `index-<year>.json` 分片 |
| 归档 / sitemap / llms | 按年月分页、按年分片、`llms.txt` 保持精简 |
| 链接结构 | 每篇 3–5 条同关键词相关文章内链，避免长链导致老文章抓取过深 |

前 2 年（约 700 篇）无需运维干预。

## 九、故障排查

| 现象 | 检查 |
| --- | --- |
| 选到了短评 / 新闻，结构不像大作文 | `python3 pipeline/fetch_sources.py --date <日期> --top 20` 看各候选 `status` 与 `strict`；加 `--essay-only` 或 `--require-essay` 重跑；确认 `newsReport` 排除是否生效 |
| 某个官媒一直没被抓到 | `python3 pipeline/fetch_sources.py --sources <id> --date <日期>` 单跑该源；多为列表页结构改版，检查 `SOURCES` 里的 `url_re` / `container`，或正文是否被 `STOP_RE` 过早截断 |
| 同一篇文章被多个源重复选 | 跨源转载按 `title_key()` 去重、保留结构分更高的那篇；若标题被加了栏目前缀，检查 `normalize_title()` 的前缀规则 |
| 讲义日期与报纸日期不一致 | 属于**回溯选文**：当天无结构达标文章，选用了前几期报纸；看【注】开头与页面「选文说明」，`source.paperDate` 是实际报纸日期。可用 `--essay-lookback 0` 关闭回溯，或调大天数 |
| 回溯选到重复文章 | 去重基于已发布讲义的 `source.originalUrl`；若手工删过 JSON 或 URL 变更，可能失效，检查 `load_used_urls()` 的扫描结果 |
| 当天文章 `status=partial` | 说明当天及回溯期内都没有完全达标的议论文；看讲义第 1 段是否有结构差异提示；也可 `--date <往期> --redo` 补一篇结构完整的 |
| 严格分论点识别偏少 | 用 `python3 pipeline/article_structure.py --json <raw>` 看 `strict.rejected` 里每段被拒原因（段首不是主张句 / 段内无论证展开 / 语义重复）；可在 `STRICT_MARKER_RE` / `TOPIC_COMMA_RE` / `STRONG_CLAIM_RE` 补句式，或放宽 `_paragraph_expanded()` 的字数门槛，再重跑 `--dry-run` 验证 |
| 结构骨架 / 严格分论点门禁失败 | `qualityReport.checks` 里 `essay_structure` / `strict_subtheses` 项会写明原因；检查 `frameworkTable[].role` 是否与 `outline` 一致、`structure.strict.pass` 是否为 true |
| 来源显示错成《人民日报》 | 讲义 `source.sourceLabel` 是否缺失；`generate_overview` 已把实际来源标签写进 prompt，若仍写错可 `--redo` 重生成 |
| 首页不显示今日卡片 | `curl https://<域名>/content/daily/index-recent.json` 是否有数据；看控制台 `getFeaturedEntry` 是否抛错 |
| APP 一直显示旧内容 | 确认 APP 在线拉取未被 CORS 拦截；Nginx `/content/` 是否加 `Access-Control-Allow-Origin`；必要时设 `VITE_DAILY_ONLINE_BASE` |
| 静态页 404 | Vercel 是否命中真实 `dist/daily/*.html`；国内反代是否有 `try_files` 吞掉 `.html`；**不要加 catch-all rewrite** |
| 当天未上新 | Actions 是否失败/被跳过；目标 JSON 是否已存在且 published（幂等 guard）；`status=draft` 说明门禁未过 |
| 讲义原文有幻觉 | 看 `qualityReport.verbatimMatch`；正式流水线原文由脚本填入，若为 false 说明 JSON 被人为改动 |
| 版权下架 | 删除对应 `daily/<slug>.json`，重跑 `content_index.py` 与 `npm run daily:prerender`，重新部署即可撤下静态页 |

## 十、日期浏览：横向日期条（已落地）

用户在原型对比后选定**横向日期条**作为正式方案（月历保留为可切换的备选，不默认）：

- **SPA / APP 阅读页**：`components/DailyDatePicker.tsx` 默认显示横向日期条，每张卡片两行——上行日期（同日多篇标「第 N 篇」）、下行文章标题；当前篇目蓝底白字。配「← 更早 / 更新 →」按钮与「共 N 篇 · 日期范围」统计，可左右横滑，「更早 …」加载全部历史。右上角可切到「月历」查看按日分布、按年加载 `index-<year>.json`。
- **静态归档页**：`dist/daily/archive/<year>.html` 使用同样的横向日期条（纯 HTML、不依赖 JS），有文章的日期直接链接到对应静态页，兼顾 SEO/GEO 内链。
- 样式在 `daily-style.css` 的 `.daily-strip` / `.daily-day-card` / `.daily-cal*`（月历备选）；原型文件 `frontend/prototype/daily-dates-prototype.html` 保留作对比参考，不参与构建。

### 移动端 UI 微调（2026-11-12）

- 日期切换卡片：`.daily-switcher` 增加 `box-sizing/min-width/max-width` 防被内容撑宽；窄屏（≤720px）下 `.daily-switcher__top` 改为两行，标题独占一行、「月历 / 日期条」切换按钮在卡片内第二行完整显示，不再溢出右边界；`.daily-strip` 设 `min-width:0; width:100%` 保证横向滚动不撑破卡片。
- 「备课加餐」：SPA 去掉按屏宽强制展开的脚本，静态模板去掉 `open` 属性，**所有端默认折叠**；内容仍完整写在 HTML / `.md` 里，不影响搜索引擎与大模型抓取。
- 「相关精读」区块：从 SPA 阅读页与静态讲义页一并删除；`relatedSlugs` 数据契约保留，归档页 / 日期条 / 上一下篇内链仍在，SEO 链接结构不受影响。

### 返回键回顶（2026-11-12）

SPA 不更换 document，Android WebView 会保留上一页的 `scrollY`，因此从精读页滑到底部再按手机返回键，首页会停在原滚动位置。`App.tsx` 现在统一处理：

- 模块级 `scrollToTop()`：`window.scrollTo({top:0, behavior:'auto'})` + `documentElement/body.scrollTop = 0`，并用 `requestAnimationFrame` 在 DOM 更新后再兜一次（页面高度变化会 clamp 滚动值）。
- `useEffect([currentPage, selectedDaily])` 在任何页面切换、阅读页切换文章时调用，覆盖首页卡片进入、顶部导航、物理返回键、浏览器 popstate、上/下篇切换全部路径。
- 初始化设置 `window.history.scrollRestoration = 'manual'`，阻止浏览器在 popstate 时自动恢复旧滚动位置。
- `DailyReader.tsx` 数据加载完成后的 `behavior:'smooth'` 改为瞬时 `auto`，避免平滑滚动在快速返回时被打断停在中途。

### 试卷列表位置记忆（2026-11-12）

试卷列表与精读页的返回策略不同：**精读页返回首页要回顶，试卷详情返回列表要回到进入前的位置**。

- `handleSelectPaper()` 在点击瞬间把 `window.scrollY` 记到 `listScrollYRef`；`useEffect` 里用 `prevPageRef` 判断来源页：`exam → home` 时调用 `restoreScrollTo(y)`（`scrollTo` + `scrollTop` 赋值 + 两次 rAF + 160ms 延迟校正），其它切页仍走 `scrollToTop()`。
- 覆盖路径：物理返回键、浏览器 popstate、ExamDetail 的返回按钮、详情 → 报告 → 详情 → 返回列表；深链 `?paper=` 进入时记录的是 0，返回等价于回顶。
- 列表页的「地区筛选展开」状态改用 `sessionStorage` 记忆，避免返回后列表高度变化导致位置偏移。
