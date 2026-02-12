# 用 Vercel 部署前端，让朋友访问网站

前端在 GitHub 已同步、且已注册 Vercel 后，按下面步骤操作即可上线。

---

## 第一步：在 Vercel 里导入 GitHub 仓库

1. 打开 [vercel.com](https://vercel.com)，登录你的账号。
2. 点击 **「Add New…」** → **「Project」**（或 **「Import Project」**）。
3. 选择 **「Import Git Repository」**，找到并选择 **GitHub**。
4. 若首次使用，按提示授权 Vercel 访问 GitHub（可只授权 `Crick2020/ShenlunAI` 这一个仓库）。
5. 在仓库列表里选中 **ShenlunAI**，点击 **「Import」**。

---

## 第二步：配置构建设置（重要）

在 **Configure Project** 页面请务必设置：

| 项 | 填写 |
|----|------|
| **Framework Preset** | 选 **Vite**（Vercel 一般会自动识别） |
| **Root Directory** | 点击 **Edit**，填 **`frontend`**（因为前端代码在仓库的 `frontend` 目录下） |
| **Build Command** | 留空或填 **`npm run build`** |
| **Output Directory** | 留空（Vite 默认输出到 `dist`，Vercel 会认） |
| **Install Command** | 留空或 **`npm install`** |

然后点击 **「Deploy」**，等待构建完成（约 1～2 分钟）。

---

## 第三步：拿到访问链接

- 部署成功后，Vercel 会给你一个地址，形如：  
  **`https://shenlun-ai-xxxx.vercel.app`**
- 把这个链接发给朋友，他们用浏览器打开即可访问你的申论智批网站。

（若你绑定了自己的域名，也可以在 **Settings → Domains** 里添加，用自定义域名访问。）

---

## 第四步：环境变量（可选）

- 线上前端默认会请求 **`https://shenlun-backend.onrender.com`** 的接口（试卷列表、批改等）。
- 若你希望线上也走自己的后端：
  1. 在 Vercel 项目里进入 **Settings → Environment Variables**。
  2. 新增变量：**Name** 填 **`VITE_API_BASE`**，**Value** 填你的后端地址（例如 `https://你的后端.onrender.com`）。
  3. 保存后，在 **Deployments** 里对最新一次部署点 **「Redeploy」**，新配置才会生效。

不配置的话，会继续用默认的 Render 后端，朋友也能正常看到页面和拉取试卷。

---

## 之后更新网站

- 只要把新代码 **push 到 GitHub 的 main 分支**，Vercel 会自动重新构建并更新网站，无需再在 Vercel 里点一次部署。

---

## 常见问题

- **页面 404 / 白屏**：确认 **Root Directory** 填的是 **`frontend`**，且该目录下有 `package.json` 和 `vite.config.ts`。
- **接口请求失败**：确认后端（如 Render）已启动且 CORS 允许你的 Vercel 域名；或按上面第四步配置 **VITE_API_BASE** 指向你的后端。

按以上步骤做完，朋友就可以通过你发的 Vercel 链接访问你的网站了。
