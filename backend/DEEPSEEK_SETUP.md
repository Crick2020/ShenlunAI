# DeepSeek 批改部署说明

后端默认使用 DeepSeek 官方 `deepseek-flash` 作为主批改模型，并保留 Gemini 和钱多多回退。

## Render 环境变量

在 Render 的 Web Service 中打开 **Environment**，添加：

```text
GRADING_PRIMARY_PROVIDER=deepseek
GRADING_FALLBACK_ENABLED=true

DEEPSEEK_API_KEY=<在 DeepSeek 控制台创建的 Key>
DEEPSEEK_CHAT_URL=https://api.deepseek.com/chat/completions
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_THINKING=disabled
DEEPSEEK_REASONING_EFFORT=low
DEEPSEEK_MAX_TOKENS=32768
DEEPSEEK_TIMEOUT_SECONDS=180
```

`DEEPSEEK_API_KEY` 必须作为 Secret 保存，不能填写到前端或提交到仓库。

## 验证顺序

1. 先使用纯文字小题提交一次批改。
2. 使用一张单独的答题图片提交一次批改。
3. 使用完整大作文提交一次批改。
4. 检查 Render 日志中的 `[DeepSeek] 调用完成`。
5. 检查响应字段 `modelProvider=deepseek` 和 `modelName=deepseek-flash`。

## 回滚

如果 DeepSeek 暂时不可用，可在 Render 将以下变量改为：

```text
GRADING_PRIMARY_PROVIDER=gemini
```

保存后重新部署即可恢复原调用顺序。

## 测试命令

```bash
cd backend
python3 -m unittest -v test_deepseek_provider.py
```


---

## 每日精读流水线（与批改后端独立）

`pipeline/llm_client.py` 复用同一套环境变量命名（`DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` / `DEEPSEEK_CHAT_URL`，可选 `GEMINI_API_KEY` 回退），但它运行在 **GitHub Actions** 里，需要在仓库 Settings → Secrets and variables → Actions 中单独配置一份 Key。

**Render 后端不做任何改动**：每日精读是静态内容（多官媒抓稿 → Git JSON → Vercel 构建期预渲染），不经过 `/api/grade`，也不需要数据库或定时任务。这样做是为了避免把模型 Key 暴露在公网可写端点上，同时绕开 Render 免费层无持久盘、无 cron 的限制。
