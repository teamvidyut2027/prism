"""Any OpenAI-compatible chat endpoint with image input (Ollama, vLLM, LM Studio, ...).

Lets the same benchmark compare Anthropic models with open-weight VLMs running locally:

    PRISM_OPENAI_BASE_URL=http://localhost:11434/v1  PRISM_OPENAI_MODEL=qwen2.5vl:7b
"""
from __future__ import annotations

import base64
import json
import os
import re
import time

import httpx

from .base import SYSTEM_PROMPT, EvalItem, ModelAdapter, ModelResponse


class OpenAICompatAdapter(ModelAdapter):
    kind = "vlm"

    def __init__(self, model: str | None = None, base_url: str | None = None):
        self.base_url = (base_url or os.environ.get("PRISM_OPENAI_BASE_URL", "")).rstrip("/")
        self.model = model or os.environ.get("PRISM_OPENAI_MODEL", "")
        self.id = f"openai-compat:{self.model or 'unset'}"
        self.label = f"{self.model or 'Local VLM'} (OpenAI-compatible)"

    def available(self):
        if not (self.base_url and self.model):
            return False, "set PRISM_OPENAI_BASE_URL and PRISM_OPENAI_MODEL"
        return True, ""

    async def answer(self, item: EvalItem) -> ModelResponse:
        b64 = base64.standard_b64encode(item.image_png).decode()
        body = {"model": self.model, "temperature": 0,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT + ' Reply as JSON: {"answer": ..., "confidence": ...}'},
                             {"role": "user", "content": [
                                 {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                                 {"type": "text", "text": item.prompt}]}]}
        headers = {}
        if os.environ.get("PRISM_OPENAI_API_KEY"):
            headers["Authorization"] = f"Bearer {os.environ['PRISM_OPENAI_API_KEY']}"
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=180) as c:
                r = await c.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            return ModelResponse(raw=None, error=str(e), latency_ms=(time.perf_counter() - t0) * 1000)
        text = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage") or {}
        common = dict(latency_ms=(time.perf_counter() - t0) * 1000, input_tokens=usage.get("prompt_tokens", 0),
                      output_tokens=usage.get("completion_tokens", 0))
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                obj = json.loads(m.group())
                conf = obj.get("confidence")
                return ModelResponse(raw=obj.get("answer"), confidence=float(conf) if conf is not None else None,
                                     **common)
            except (ValueError, TypeError):
                pass
        return ModelResponse(raw=text, **common)
