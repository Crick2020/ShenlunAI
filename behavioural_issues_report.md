# Behavioural issues report

以下条目依据 `model_a` / `model_b` 原始会话 JSONL 中的可核对原文整理；摘录为日志原文，未改写。

Session sources（行号均指下列文件）：

- `model_a/session_72d449ae-bc07-49bc-8641-800a40865933.jsonl`
- `model_b/session_ece5abd7-9519-4973-94b0-988c4ae86e10.jsonl`

---

### 1

- **Model:** A  
- **Issue type:** Tool Use Errors  
- **Severity:** major  
- **Transcript reference:** `model_a/session_72d449ae-bc07-49bc-8641-800a40865933.jsonl`, line 14  
- **Verbatim excerpt:**  
  `"File content (18841 tokens) exceeds maximum allowed tokens (10000). Use offset and limit parameters to read specific portions of the file, or search for specific content instead of reading the whole file.", "is_error": true`  
- **Description:** 我看到 Explore 子代理用 `Read` 整文件去读超大文件、没用 `offset`/`limit`，工具直接报错，我拿不到可用的文件片段。

---

### 2

- **Model:** B  
- **Issue type:** Tool Use Errors  
- **Severity:** major  
- **Transcript reference:** `model_b/session_ece5abd7-9519-4973-94b0-988c4ae86e10.jsonl`, line 23  
- **Verbatim excerpt:**  
  `"File does not exist. Note: your current working directory is C:\\Users\\HP\\Downloads\\sprint2\\model_b.", "is_error": true`  
- **Description:** 我看到子代理对并不存在的路径调了 `Read`，工具当场报「文件不存在」，后面只能靠其它步骤补救。

---

### 3

- **Model:** A  
- **Issue type:** Overengineering  
- **Severity:** major  
- **Transcript reference:** `model_a/session_72d449ae-bc07-49bc-8641-800a40865933.jsonl`, line 6  
- **Verbatim excerpt:**  
  `"prompt": "I need a VERY THOROUGH trace of how Node.js HTTP server manages the socket \u2194 request/response lifecycle. This is in the Node.js source repo.\n\nFocus on these files:\n- lib/_http_server.js\n- lib/_http_common.js\n- lib/_http_incoming.js\n- lib/_http_outgoing.js\n- lib/internal/http.js (if relevant)\n\nI need to understand:\n\n1. **Socket \u2192 Parser \u2192 Request binding**`  
- **Description:** 我明明只想要请求如何挂到套接字、如何清理的走读说明，它却起了 Explore，并塞了一整份多章节、「VERY THOROUGH trace」级别的任务书，范围和工程量都明显偏大。

---

### 4

- **Model:** A  
- **Issue type:** Verification Failures  
- **Severity:** minor  
- **Transcript reference:** `model_a/session_72d449ae-bc07-49bc-8641-800a40865933.jsonl`, lines 56 and 210  
- **Verbatim excerpt:**  
  Line 56: `"thinking_content": " I need to dig into the actual implementation to verify whether those race conditions are genuine issues or just theoretical concerns."`  
  Line 210 (inside `summary_data.tool_metrics`): `"tool_calls_by_type": {\n    "Agent": 1,\n    "Read": 4,\n    "Grep": 5\n  }`  
- **Description:** 我看到它在思考里说要用实现来核实竞态是否真问题，但汇总里的工具只有 `Agent` / `Read` / `Grep`，没有跑 `Bash` 或测试，等于没做可执行的验证。

---

### 5

- **Model:** B  
- **Issue type:** Tool Use Errors  
- **Severity:** minor  
- **Transcript reference:** `model_b/session_ece5abd7-9519-4973-94b0-988c4ae86e10.jsonl`, line 9  
- **Verbatim excerpt:**  
  `"File content (13882 tokens) exceeds maximum allowed tokens (10000). Use offset and limit parameters to read specific portions of the file, or search for specific content instead of reading the whole file.", "is_error": true`  
- **Description:** 我在 B 侧又遇到同类问题：`Read` 没分段读，撞到 token 上限，工具报错而不是返回部分内容。

---

### 6

- **Model:** B  
- **Issue type:** Overengineering  
- **Severity:** major  
- **Transcript reference:** `model_b/session_ece5abd7-9519-4973-94b0-988c4ae86e10.jsonl`, lines 393 and 493  
- **Verbatim excerpt:**  
  Line 393 (`type: user`): `"thank you. Based on that, what is the smallest change that would stop that extra work once the connection is no longer useable?"`  
  Line 493 (assistant `ExitPlanMode` `plan` prefix):

```
"plan": "# Destroy the response when `socketOnError` destroys the socket\n\n## Context\n\nWhen a client disconnects (TCP RST / ECONNRESET) while the server is mid-response,\n`socketOnError` destroys the socket but never notifies the response (`socket._httpMessage`)."
```
- **Description:** 我问的是断开连接后止住多余工作的「最小」改动，它却进了计划模式，甩出带上下文、改码、测例、验证的一整套方案，一上来就过重了。
