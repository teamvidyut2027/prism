"""Anthropic vision-language model adapter (Anthropic Python SDK).

Models are addressed by a short alias such as ``opus-5-5``; the full API model id is
resolved once from Anthropic's Models API (``client.models.list()``), or can be set
explicitly with ``PRISM_ANTHROPIC_MODEL_ID``.
"""
from __future__ import annotations

import base64
import json
import os
import time

from .base import SYSTEM_PROMPT, EvalItem, ModelAdapter, ModelResponse

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "description": "The answer, in exactly the requested format."},
        "confidence": {"type": "number", "description": "Probability (0-1) that the answer is correct."},
    },
    "required": ["answer", "confidence"],
    "additionalProperties": False,
}

# USD per million tokens (input, output)
PRICES = {"opus-5-5": (4.0, 20.0), "sonnet-5-5": (2.0, 10.0), "haiku-5-5": (0.10, 0.50)}


def pretty(alias: str) -> str:
    family, *ver = alias.split("-")
    return f"Anthropic {family.title()} {'.'.join(ver)}".strip()


class AnthropicAdapter(ModelAdapter):
    kind = "vlm"

    def __init__(self, alias: str = "opus-5-5", effort: str = "low"):
        self.alias, self.effort = alias, effort
        self.id = f"anthropic:{alias}" + ("" if effort == "low" else f"@{effort}")
        self.label = pretty(alias) + ("" if effort == "low" else f" ({effort})")
        self.price_in, self.price_out = PRICES.get(alias, (0.0, 0.0))
        self._client = None
        self._model_id: str | None = os.environ.get("PRISM_ANTHROPIC_MODEL_ID")

    def available(self):
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False, "anthropic package not installed"
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            return False, "set ANTHROPIC_API_KEY to evaluate Anthropic models"
        return True, ""

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(max_retries=4)
        return self._client

    async def model_id(self) -> str:
        """Resolve the alias (e.g. 'opus-5-5') to the full API model id via the Models API."""
        if self._model_id is None:
            async for m in self.client.models.list():
                if m.id.endswith(self.alias):
                    self._model_id = m.id
                    break
            else:
                raise RuntimeError(f"no Anthropic model matches '{self.alias}'")
        return self._model_id

    async def answer(self, item: EvalItem) -> ModelResponse:
        import anthropic
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": base64.standard_b64encode(item.image_png).decode()}},
            {"type": "text", "text": item.prompt},
        ]
        t0 = time.perf_counter()
        try:
            model = await self.model_id()
            kwargs = dict(model=model, max_tokens=4000, system=SYSTEM_PROMPT,
                          messages=[{"role": "user", "content": content}],
                          output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": ANSWER_SCHEMA}})
            try:
                # server-side fallback: a safety-classifier decline is retried on a fallback model in the same call
                resp = await self.client.beta.messages.create(
                    **kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            except (anthropic.BadRequestError, TypeError):
                resp = await self.client.messages.create(**kwargs)
        except (anthropic.APIError, RuntimeError) as e:
            return ModelResponse(raw=None, error=f"{type(e).__name__}: {getattr(e, 'message', e)}",
                                 latency_ms=(time.perf_counter() - t0) * 1000)
        dt = (time.perf_counter() - t0) * 1000
        usage = getattr(resp, "usage", None)
        common = dict(latency_ms=dt, input_tokens=getattr(usage, "input_tokens", 0) or 0,
                      output_tokens=getattr(usage, "output_tokens", 0) or 0,
                      meta={"model": getattr(resp, "model", model), "stop_reason": resp.stop_reason})
        if resp.stop_reason == "refusal":
            return ModelResponse(raw=None, error="refusal", **common)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        try:
            obj = json.loads(text)
            conf = obj.get("confidence")
            return ModelResponse(raw=obj.get("answer"), confidence=float(conf) if conf is not None else None, **common)
        except (ValueError, AttributeError):
            return ModelResponse(raw=text, **common)
