"""The Family contract.

A family is a parametric generator of one kind of visual task. It has two
*independent* paths to the truth:

    sample_scene ──► facts_from_scene ──► answer()  = gold answer
         │
         └► render ──► image ──► measure() (pixels only) ──► answer() = verified answer

``measure`` only ever sees the rendered pixels and the public *manifest*
(layout: where the plot area is, which colour a legend entry uses, the value
grain). It never sees the scene values. A question is admitted to a dataset
only when both paths agree, so a rendering bug, a clipped label, an occluded
object or an off-by-one in the generator cannot silently produce a wrong gold
answer.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Any

import numpy as np
from PIL import Image

from ..core.spec import AnswerType, Question, Rejected


class VerifyError(Exception):
    """The verifier could not recover the facts from the pixels."""


class Family(ABC):
    name: str = ""
    title: str = ""
    description: str = ""
    skills: list[str] = []
    # template id -> list of phrasings (str.format with question params)
    phrasings: dict[str, list[str]] = {}
    knobs: dict[str, str] = {}  # human-readable description of what difficulty changes

    # ---- generation ---------------------------------------------------------
    @abstractmethod
    def sample_scene(self, r: random.Random, difficulty: int) -> dict: ...

    @abstractmethod
    def render(self, scene: dict) -> tuple[Image.Image, dict]:
        """Return (image, manifest). The manifest must not leak answers."""

    @abstractmethod
    def facts_from_scene(self, scene: dict) -> dict: ...

    @abstractmethod
    def question_candidates(self, scene: dict, facts: dict, r: random.Random,
                            difficulty: int) -> list[tuple[str, dict]]:
        """(template, params) pairs that are *unambiguous* for this scene."""

    @abstractmethod
    def answer(self, template: str, params: dict, facts: dict) -> Any:
        """Pure function: facts -> answer. Shared by the gold and verified paths."""

    def question_meta(self, template: str, params: dict, scene: dict) -> dict:
        """answer_type, skills, choices, tolerance for a template."""
        raise NotImplementedError

    # ---- independent verification ------------------------------------------
    @abstractmethod
    def measure(self, img: np.ndarray, manifest: dict) -> dict:
        """Re-derive the facts from pixels + manifest only. Raise VerifyError."""

    def compare_facts(self, truth: dict, measured: dict) -> list[str]:
        """Return human-readable discrepancies between scene facts and measured facts."""
        return [] if truth == measured else ["measured facts differ from scene facts"]

    # ---- counterfactuals -----------------------------------------------------
    def mutate(self, scene: dict, r: random.Random, hint: dict | None = None) -> dict | None:
        """A minimal edit of the scene (used to build answer-flipping counterfactuals).

        ``hint`` holds the parameters of the question being flipped, so a family can
        edit the element the question is about instead of a random one."""
        return None

    # ---- helpers ---------------------------------------------------------------
    def build_questions(self, task_id: str, scene: dict, facts: dict, r: random.Random,
                        difficulty: int, k: int) -> list[Question]:
        cands = self.question_candidates(scene, facts, r, difficulty)
        if not cands:
            raise Rejected("no unambiguous question for this scene")
        # 1) pick k distinct templates uniformly (not weighted by how many parameterisations exist)
        by_t: dict[str, list[dict]] = {}
        for t, p in cands:
            by_t.setdefault(t, []).append(p)
        templates = sorted(by_t)
        r.shuffle(templates)
        chosen = []
        for t in templates[:k]:
            ps = by_t[t]
            # 2) balance yes/no answers: flip a coin for the target and prefer params that hit it
            if self.question_meta(t, ps[0], scene)["answer_type"] == AnswerType.BOOLEAN:
                target = r.random() < 0.5
                hit = [p for p in ps if self.answer(t, p, facts) == target]
                ps = hit or ps
            chosen.append((t, r.choice(ps)))
        return [self.make_question(f"{task_id}:q{i}", t, p, scene, facts, r.randrange(len(self.phrasings[t])))
                for i, (t, p) in enumerate(chosen)]

    def make_question(self, qid: str, template: str, params: dict, scene: dict, facts: dict,
                      phrasing: int = 0) -> Question:
        meta = self.question_meta(template, params, scene)
        text = self.phrasings[template][phrasing].format(**params)
        return Question(qid=qid, template=f"{self.name}.{template}", text=text,
                        answer_type=meta["answer_type"], answer=self.answer(template, params, facts),
                        skills=meta["skills"], params=params, choices=meta.get("choices"),
                        tolerance=meta.get("tolerance", 0.0), phrasing=phrasing)

    def describe(self) -> dict:
        return {"name": self.name, "title": self.title, "description": self.description,
                "skills": self.skills, "templates": {k: v[0] for k, v in self.phrasings.items()},
                "knobs": self.knobs}


def nice_ceiling(x: float) -> float:
    mag = 10 ** int(np.floor(np.log10(max(x, 1e-9))))
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= x:
            return m * mag
    return 10 * mag


def short_template(t: str) -> str:
    return t.split(".", 1)[-1]


__all__ = ["Family", "VerifyError", "AnswerType", "Question", "Rejected", "nice_ceiling"]
