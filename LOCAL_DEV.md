# 本地开发：先在本机验证，再部署到 Render

这样可以在本地改后端/试卷数据，确认无误后再推送到 Render，避免每次都要等线上更新才能看到效果。

## 1. 启动本地后端

在项目根目录下：

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- `--reload`：改完 `main.py` 或 `data/*.json` 后会自动重启，无需手动停掉再开。
- 后端地址：<http://localhost:8000>
- 可访问 <http://localhost:8000/api/list> 检查试卷列表是否正常。

如需本地也走 AI 批改，在启动前设置环境变量（与 Render 上一致）：

```bash
export GEMINI_API_KEY=你的密钥
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 2. 让前端在开发时请求本地后端

在 **frontend** 目录下：

```bash
cp .env.development.example .env.development
```

这样 `npm run dev` 时会使用 `VITE_API_BASE=http://localhost:8000`，所有接口（试卷列表、试卷详情、批改）都会打到本机后端。

`.env.development` 不要提交到 git（通常已在 .gitignore 中）。

## 3. 启动前端开发服务器

```bash
cd frontend
npm install
npm run dev
```

浏览器打开控制台给出的地址（一般是 http://localhost:5173），即可在本地看到效果，且请求的都是本地后端。

## 4. 日常流程

1. **改后端或 data 里的试卷** → 保存后，若用了 `--reload`，后端会自动重启。
2. **改前端** → 保存后 Vite 会热更新。
3. 在本地把流程走通、数据/批改都确认没问题后，再 **git push**，让 Render 自动部署。线上前端仍然请求 Render 的地址（未设置 `VITE_API_BASE` 时默认就是线上后端）。

## 5. 注意

- **只在本机开发时** 使用 `.env.development` 和本地后端；**构建线上前端**（如 `npm run build`）时不要带 `VITE_API_BASE`，或保证线上构建用的是默认的 Render 地址，这样线上才会继续用 Render 后端。
- 若暂时不想用本地后端，删掉或重命名 `frontend/.env.development`，前端会恢复为请求 `https://shenlun-backend.onrender.com`。
