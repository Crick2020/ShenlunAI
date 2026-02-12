# 把前端 + 后端同步到 GitHub

本项目是**单仓库**：`frontend/` 和 `backend/` 都在同一个 Git 仓库里，一次推送即可同步两端。

## 一、日常同步（推荐）

在项目根目录执行：

```bash
# 1. 查看改动（前端、后端都会列出）
git status

# 2. 全部加入暂存（或只加某几个文件）
git add .
# 仅前端: git add frontend/
# 仅后端: git add backend/

# 3. 提交
git commit -m "描述你的修改，例如：修复试卷拉取、新增某接口"

# 4. 推送到 GitHub（前端+后端一起同步）
git push origin main
```

若当前分支不叫 `main`，用 `git branch` 看当前分支名，把上面最后一句里的 `main` 换成该名字。

## 二、首次或重新绑定远程

若还没配置过远程，或要换一个 GitHub 仓库：

```bash
# 查看是否已有 origin
git remote -v

# 没有则添加（替换成你的仓库地址）
git remote add origin git@github.com:你的用户名/ShenlunAI.git

# 已有但想改地址
git remote set-url origin git@github.com:你的用户名/ShenlunAI.git
```

## 三、一条命令快速同步（可选）

在项目根目录可以加一个脚本，例如 `sync.sh`：

```bash
#!/bin/bash
cd "$(dirname "$0")"
git add .
git status
read -p "提交说明 (Commit message): " msg
[ -n "$msg" ] && git commit -m "$msg" && git push origin main
```

使用：`chmod +x sync.sh` 后执行 `./sync.sh`，按提示输入提交说明即可推送。提交说明可以随便写，但写清楚「改了什么」以后查历史更方便（例如：`修复试卷拉取`、`新增某题数据`）。

## 四、不要提交的内容

已写在 `.gitignore` 里，包括：

- `node_modules/`、`dist/`、`.next/`（依赖与构建产物）
- `.env`、`.env.local`、`frontend/.env.development`（含密钥或本地配置）
- `__pycache__/`、`venv/`（Python 缓存与虚拟环境）

这样可避免把敏感信息和无关文件推到 GitHub。
