from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..core.spec import Question, Task
from ..grading.grader import answer_instruction

SYSTEM_PROMPT = (
    "You are taking a visual reasoning test. Each item is one image and one question about it. "
    "Look at the image carefully; everything you need is in the image. "
    "Reply with the answer only, in the format requested, plus your confidence (0 to 1) that it is correct."
)


def build_prompt(q: Question) -> str:
    return f"{q.text}\n{answer_instruction(q)}"


@dataclass
class ModelResponse:
    raw: Any
    confidence: float | None = None
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class EvalItem:
    task: Task
    question: Question
    image_png: bytes
    prompt: str


class ModelAdapter(ABC):
    id: str = ""
    label: str = ""
    kind: str = "vlm"          # vlm | baseline | oracle
    blind: bool = False        # True if the adapter never looks at the image
    price_in: float = 0.0      # USD per million input tokens
    price_out: float = 0.0

    def available(self) -> tuple[bool, str]:
        return True, ""

    def prepare(self, items: list[EvalItem]) -> None:
        """Optional one-off setup with the full item list (used by blind baselines)."""

    @abstractmethod
    async def answer(self, item: EvalItem) -> ModelResponse: ...

    def describe(self) -> dict:
        ok, why = self.available()
        return {"id": self.id, "label": self.label, "kind": self.kind, "blind": self.blind,
                "available": ok, "reason": why}
