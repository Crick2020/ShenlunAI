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
