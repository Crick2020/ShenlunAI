#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日精读 LLM 客户端（纯标准库 urllib，无 SDK）。

与 backend/main.py 的调用方式和环境变量命名保持一致：
  - 主：DeepSeek OpenAI 兼容 /chat/completions
  - 备：Gemini generateContent（可选）
主备都失败时抛出 RuntimeError，由 generate_daily.py 决定重试或标记 draft。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

# 本地开发可把 key 写在仓库根 .env（已被 .gitignore 忽略）。
# 只在环境变量未设置时填充，CI/GitHub Actions 注入的值始终优先，绝不覆盖。
def _load_dotenv() -> None:
    here = Path(__file__).resolve().parent
    candidates = []
    custom = os.getenv("DAILY_DOTENV_PATH")
    if custom:
        candidates.append(Path(custom).expanduser())
    candidates += [here.parent / ".env", here / ".env"]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and not os.getenv(key):
                os.environ[key] = value


_load_dotenv()

DEEPSEEK_URL = (os.getenv("DEEPSEEK_CHAT_URL") or "https://api.deepseek.com/chat/completions").strip()
DEEPSEEK_MODEL = (os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip()
GEMINI_ENDPOINT = (os.getenv("GEMINI_ENDPOINT") or "https://generativelanguage.googleapis.com").rstrip("/")
GEMINI_MODEL = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
MAX_RETRIES = 3


def _post(url: str, payload: dict, headers: dict, timeout: int = 120) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _deepseek(system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> str:
    key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    data = _post(
        DEEPSEEK_URL, payload,
        {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    return (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""


def _gemini(system: str, user: str, temperature: float, max_tokens: int, json_mode: bool) -> str:
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY 未配置")
    config = {"temperature": temperature, "maxOutputTokens": max_tokens}
    if json_mode:
        config["responseMimeType"] = "application/json"
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": config,
    }
    url = f"{GEMINI_ENDPOINT}/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    data = _post(url, payload, {"Content-Type": "application/json"})
    candidates = data.get("candidates") or []
    parts = (candidates[0].get("content", {}).get("parts") or []) if candidates else []
    return "".join(p.get("text", "") for p in parts)


def chat(system: str, user: str, *, temperature: float = 0.4,
         max_tokens: int = 4096, json_mode: bool = True) -> str:
    """按主备顺序调用，带指数退避；返回模型输出的纯文本。"""
    providers = [_deepseek]
    if (os.getenv("GEMINI_API_KEY") or "").strip():
        providers.append(_gemini)

    last_error: Exception | None = None
    for provider in providers:
        for attempt in range(MAX_RETRIES):
            try:
                text = provider(system, user, temperature, max_tokens, json_mode)
                if text.strip():
                    return text.strip()
                raise RuntimeError("模型返回空内容")
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                    RuntimeError, ValueError, KeyError) as exc:
                last_error = exc
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    continue
                break
    raise RuntimeError(f"所有模型调用失败：{last_error}")


def parse_json_response(text: str):
    """容错解析模型返回的 JSON（去掉代码围栏、截取首尾大括号/方括号）。"""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    for pattern in (r"\{.*\}", r"\[.*\]"):
        m = re.search(pattern, cleaned, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
    raise ValueError(f"模型输出不是合法 JSON：{text[:300]}")


def chat_json(system: str, user: str, *, temperature: float = 0.4, max_tokens: int = 4096):
    return parse_json_response(chat(system, user, temperature=temperature,
                                    max_tokens=max_tokens, json_mode=True))
