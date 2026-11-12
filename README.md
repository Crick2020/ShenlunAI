<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Run and deploy your AI Studio app

This contains everything you need to run your app locally.

View your app in AI Studio: https://ai.studio/apps/drive/1-cwsGBfHjiDAEUICVSk-Dfw4icezwfds

## Run Locally

**Prerequisites:**  Node.js


1. Install dependencies:
   `npm install`
2. Set the `GEMINI_API_KEY` in [.env.local](.env.local) to your Gemini API key
3. Run the app:
   `npm run dev`

## 本地开发与测试（后端在 Render 时）

改完代码后想先在本地验证再部署，可以按下面做。

### 1. 启动本地后端

在项目根目录执行：

```bash
cd backend
uvicorn main:app --reload --port 8000
```

后端会跑在 `http://localhost:8000`，改代码后会自动重载。

### 2. 让前端连本地后端

前端默认连的是 Render 上的地址 `https://shenlun-backend.onrender.com`。本地测试时要改成连本机：

1. 在 **frontend** 目录下，把示例配置复制为本地开发配置（只需做一次）：
   ```bash
   cd frontend
   cp .env.development.example .env.development
   ```
2. `.env.development` 里已有 `VITE_API_BASE=http://localhost:8000`，无需再改。
3. 启动前端：
   ```bash
   npm run dev
   ```

这样前端会请求 `http://localhost:8000`，即你本机正在跑的后端，不会打到 Render。

### 3. 只测后端接口（可选）

不启动前端、只测后端时，可以用：

```bash
cd backend
python test_grade_api.py
```

前提是已用上面的命令把后端跑在 8000 端口。

### 4. 自检：线上后端是否已包含事业单位等试卷

若首页选了「事业单位」仍为空，多半是**当前连接的后端**（默认 `https://shenlun-backend.onrender.com`）尚未部署含 `backend/data/sydw_*.json` 的版本。可在终端执行：

```bash
curl -sS "https://shenlun-backend.onrender.com/api/list" | python3 -c "import sys,json;d=json.load(sys.stdin);print('总条数', len(d));print('事业单位', sum(1 for x in d if x.get('examType')=='事业单位'))"
```

若「事业单位」为 `0`，需在仓库推送最新代码后，在 Render **重新部署**后端；本地验证请用上一节的 `.env.development` 指向 `http://localhost:8000`。

### 小结

| 步骤 | 命令 / 操作 |
|------|----------------|
| 启动后端 | `cd backend && uvicorn main:app --reload --port 8000` |
| 前端连本地 | `cd frontend` → 已有 `.env.development` 且 `VITE_API_BASE=http://localhost:8000` |
| 启动前端 | `cd frontend && npm run dev` |

测试没问题后，再部署到 Render；前端部署后仍会使用 Render 上的后端（未设置 `VITE_API_BASE` 时默认就是 Render 地址）。


---

## 申论每日精读（新增）

每天 08:20（北京时间）由 GitHub Actions 自动从《人民日报》评论版选一篇申论范文，生成「原文 + 老师逐段解析」讲义，同时发布到网站与 APP：

- 首页「今日精读」卡片 → 阅读页支持按日期切换历史，原文与老师解析用不同底色与竖线强区分。
- 每篇另有独立静态页 `/daily/<日期>.html` 与纯文本 `.md` 版，含 Article / BreadcrumbList / FAQPage 结构化数据，供搜索引擎与大模型直接抓取；站点自动生成 sitemap 分片、RSS 与 llms.txt。
- 内容以结构化 JSON 存于 `frontend/public/content/daily/`，一天一份、一次 commit；不占用后端、不使用数据库。
- APP 在线拉取当天内容，内置最近 30 篇作离线兜底。

开发、命令、数据契约与故障排查见 `docs/DAILY_READING.md`；生成范式见 `pipeline/lecture_prompt.md`。

### 多官媒选文与严格分论点（2026-11 更新）

每日精读的来源已扩展为**人民日报电子版、人民网观点、人民论坛网评、光明网地评线、中国经济网经点热评、共产党员网先锋文汇**六个官媒评论栏目，由 `pipeline/fetch_sources.py` 聚合。选文的唯一硬标准是**符合申论大作文格式**：明确总论点 + 若干**严格分论点**（段首主张句、段内展开论证、彼此语义不重复、位于首尾之间）+ 结尾，由 `pipeline/article_structure.py` 纯规则判定。只有 `strict.pass` 的文章才会被发布；来源与栏目只作次要权重。可用 `--sources` 或仓库 Variable `DAILY_SOURCES` 限定来源。详见 `docs/DAILY_READING.md`。

