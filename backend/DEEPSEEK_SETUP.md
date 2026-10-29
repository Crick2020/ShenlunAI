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
