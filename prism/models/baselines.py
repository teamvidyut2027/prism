"""Reference points that frame every model score.

* ``baseline:prior`` is blind. It answers each question with the most common
  gold answer for its template across the dataset, which is the best
  image-free strategy and measures answer bias.
* ``baseline:random`` is blind. It picks uniformly from the answers its
  template produces.
* ``oracle:pixels`` looks only at the pixels, using the family's classical-CV
  verifier. It is an end-to-end integrity check of the image files, prompts
  and grader: anything below 100% on admitted items would point at a bug.
"""
from __future__ import annotations

import io
import random
from collections import Counter, defaultdict

import numpy as np
from PIL import Image

from ..core.spec import AnswerType
from ..families import REGISTRY, VerifyError
from ..validate.perturb import recoverable_view
from .base import EvalItem, ModelAdapter, ModelResponse


def _render(ans, t: AnswerType):
    if t == AnswerType.BOOLEAN:
        return "yes" if ans else "no"
    if t == AnswerType.SEQUENCE:
        return ", ".join(ans)
    return str(ans)


class PriorBaseline(ModelAdapter):
    id, label, kind, blind = "baseline:prior", "Blind prior (majority answer)", "baseline", True

    def prepare(self, items):
        c = defaultdict(Counter)
        for it in items:
            a = it.question.answer
            c[it.question.template][tuple(a) if isinstance(a, list) else a] += 1
        self.best = {t: cc.most_common(1)[0][0] for t, cc in c.items()}

    async def answer(self, item):
        a = self.best[item.question.template]
        return ModelResponse(raw=_render(list(a) if isinstance(a, tuple) else a, item.question.answer_type))


class RandomBaseline(ModelAdapter):
    id, label, kind, blind = "baseline:random", "Blind random guess", "baseline", True

    def prepare(self, items):
        c = defaultdict(set)
        for it in items:
            a = it.question.answer
            c[it.question.template].add(tuple(a) if isinstance(a, list) else a)
        self.pool = {t: sorted(v, key=str) for t, v in c.items()}

    async def answer(self, item):
        r = random.Random(item.question.qid)
        q = item.question
        if q.answer_type == AnswerType.CHOICE and q.choices:
            return ModelResponse(raw=r.choice(q.choices))
        if q.answer_type == AnswerType.SEQUENCE and q.choices:
            seq = list(q.choices)
            r.shuffle(seq)
            return ModelResponse(raw=", ".join(seq))
        a = r.choice(self.pool[q.template])
        return ModelResponse(raw=_render(list(a) if isinstance(a, tuple) else a, q.answer_type))


class PixelOracle(ModelAdapter):
    id, label, kind = "oracle:pixels", "Pixel oracle (classical CV, integrity check)", "oracle"

    async def answer(self, item: EvalItem):
        fam = REGISTRY[item.task.family]
        img = Image.open(io.BytesIO(item.image_png)).convert("RGB")
        arr = recoverable_view(img) if item.task.variant == "perturbation" else np.asarray(img)
        try:
            facts = fam.measure(arr, item.task.manifest)
            ans = fam.answer(item.question.template.split(".", 1)[1], item.question.params, facts)
        except (VerifyError, KeyError, ValueError, IndexError) as e:
            return ModelResponse(raw=None, error=f"oracle could not read image: {e}")
        return ModelResponse(raw=_render(ans, item.question.answer_type), confidence=1.0)
