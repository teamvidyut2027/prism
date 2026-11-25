"""Core data model for the Visual Task Factory.

A *Task* is one synthetic image plus the questions asked about it. Every
question carries a gold answer that was computed from the scene the image was
drawn from, and (after validation) a second answer that an independent
pixel-level verifier re-derived from the rendered image alone.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class AnswerType(str, Enum):
    INTEGER = "integer"      # exact match
    NUMBER = "number"        # |pred - gold| <= tolerance
    CHOICE = "choice"        # one label from a closed list
    BOOLEAN = "boolean"      # yes / no
    TIME = "time"            # H:MM on a 12-hour clock
    SEQUENCE = "sequence"    # ordered list of labels


class Skill(str, Enum):
    COUNTING = "counting"
    COMPARISON = "comparison"
    NUMERIC_READING = "numeric_reading"
    SPATIAL = "spatial_reasoning"
    OCR = "text_reading"
    ARITHMETIC = "arithmetic"
    TEMPORAL = "clock_reading"
    PATHFINDING = "path_reasoning"
    TREND = "trend_analysis"
    ATTRIBUTE = "attribute_binding"


class VariantKind(str, Enum):
    BASE = "base"
    PARAPHRASE = "paraphrase"          # same image, reworded question
    PERTURB = "perturbation"           # same scene, degraded pixels
    COUNTERFACTUAL = "counterfactual"  # minimal scene edit that flips the answer


@dataclass
class Question:
    qid: str
    template: str                 # stable template id, e.g. "bars.argmax"
    text: str                     # rendered natural-language prompt
    answer_type: AnswerType
    answer: Any                   # gold answer from the scene (source of truth #1)
    skills: list[str]
    params: dict = field(default_factory=dict)   # template parameters (labels, thresholds...)
    choices: list[str] | None = None
    tolerance: float = 0.0        # absolute tolerance for NUMBER answers
    phrasing: int = 0             # which paraphrase of the template was used
    # filled in by validation
    verified_answer: Any = None   # answer re-derived from pixels (source of truth #2)
    verified: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["answer_type"] = self.answer_type.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Question":
        d = dict(d)
        d["answer_type"] = AnswerType(d["answer_type"])
        return cls(**d)


@dataclass
class Task:
    task_id: str
    family: str
    seed: int
    difficulty: int
    scene: dict                   # full generative description (the ground truth)
    manifest: dict                # public rendering layout (no answers) used by verifiers
    questions: list[Question]
    variant: str = VariantKind.BASE.value
    parent_id: str | None = None  # base task this variant derives from
    variant_info: dict = field(default_factory=dict)
    image_id: str = ""            # task whose PNG this task shows (paraphrases reuse the parent's image)
    image_sha256: str = ""
    dhash: str = ""
    validation: dict = field(default_factory=dict)
    width: int = 0
    height: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["questions"] = [q.to_dict() for q in self.questions]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        d = dict(d)
        d["questions"] = [Question.from_dict(q) for q in d["questions"]]
        return cls(**d)


class Rejected(Exception):
    """Raised by a generator when a sampled scene would be ambiguous or unverifiable."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
