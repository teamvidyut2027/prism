from __future__ import annotations

from .anthropic_vlm import AnthropicAdapter
from .base import EvalItem, ModelAdapter, ModelResponse, build_prompt
from .baselines import PixelOracle, PriorBaseline, RandomBaseline
from .openai_compat import OpenAICompatAdapter


def all_adapters() -> list[ModelAdapter]:
    return [AnthropicAdapter("opus-5-5"), AnthropicAdapter("sonnet-5-5"), AnthropicAdapter("haiku-5-5"),
            OpenAICompatAdapter(), PixelOracle(), PriorBaseline(), RandomBaseline()]


def get_adapter(model_id: str) -> ModelAdapter:
    if model_id.startswith("anthropic:"):
        alias, _, effort = model_id.split(":", 1)[1].partition("@")
        return AnthropicAdapter(alias, effort or "low")
    if model_id.startswith("openai-compat:"):
        return OpenAICompatAdapter(model_id.split(":", 1)[1])
    for a in (PixelOracle(), PriorBaseline(), RandomBaseline()):
        if a.id == model_id:
            return a
    raise KeyError(f"unknown model {model_id}")


__all__ = ["EvalItem", "ModelAdapter", "ModelResponse", "build_prompt", "all_adapters", "get_adapter"]
