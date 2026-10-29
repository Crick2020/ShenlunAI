import json
import os
import unittest
from unittest.mock import patch

import main


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def deepseek_response(content="批改报告"):
    return {
        "model": "deepseek-v4.1-flash-1017",
        "choices": [
            {
                "message": {"content": content, "reasoning_content": "内部推理"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }


class DeepSeekProviderTests(unittest.TestCase):
    def test_text_request_uses_official_payload(self):
        env = {
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_MODEL": "deepseek-flash",
            "DEEPSEEK_THINKING": "disabled",
            "DEEPSEEK_MAX_TOKENS": "4096",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "main.urllib.request.urlopen", return_value=FakeResponse(deepseek_response())
        ) as urlopen:
            result = main.call_deepseek("测试批改", temperature=0.15)

        self.assertEqual(result, "批改报告")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["temperature"], 0.15)
        self.assertEqual(payload["max_tokens"], 4096)
        self.assertNotIn("reasoning_effort", payload)
        self.assertEqual(payload["messages"][1]["content"], "测试批改")

    def test_image_request_uses_high_detail(self):
        env = {
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_THINKING": "disabled",
        }
        image = "data:image/jpeg;base64,AAAA"
        with patch.dict(os.environ, env, clear=False), patch(
            "main.urllib.request.urlopen", return_value=FakeResponse(deepseek_response())
        ) as urlopen:
            result = main.call_deepseek("批改图片", [image])

        self.assertEqual(result, "批改报告")
        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        parts = payload["messages"][1]["content"]
        self.assertEqual(parts[0], {"type": "text", "text": "批改图片"})
        self.assertEqual(parts[1]["type"], "image_url")
        self.assertEqual(parts[1]["image_url"]["url"], image)
        self.assertEqual(parts[1]["image_url"]["detail"], "high")

    def test_thinking_mode_omits_temperature(self):
        env = {
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_THINKING": "enabled",
            "DEEPSEEK_REASONING_EFFORT": "low",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "main.urllib.request.urlopen", return_value=FakeResponse(deepseek_response())
        ) as urlopen:
            main.call_deepseek("测试批改", temperature=0.3)

        payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertNotIn("temperature", payload)

    def test_deepseek_failure_falls_back_to_gemini(self):
        env = {
            "GRADING_PRIMARY_PROVIDER": "deepseek",
            "GRADING_FALLBACK_ENABLED": "true",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "main.call_deepseek", return_value=None
        ), patch(
            "main.call_gemini_system", return_value="备用报告"
        ):
            raw, provider, model = main.call_grading_model("测试批改")

        self.assertEqual(raw, "备用报告")
        self.assertEqual(provider, "gemini")
        self.assertEqual(model, "gemini-3-flash-preview")


if __name__ == "__main__":
    unittest.main()
