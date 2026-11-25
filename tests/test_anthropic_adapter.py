"""The Anthropic adapter resolves the model id, builds a vision + structured-output request and parses the reply (no network)."""
import asyncio
import json
from types import SimpleNamespace

from prism.core.spec import AnswerType, Question, Task
from prism.models import EvalItem, build_prompt
from prism.models.anthropic_vlm import AnthropicAdapter

FULL_ID = "vendor-opus-5-5"   # stand-in for the id the Models API returns


class FakeModels:
    def list(self):
        async def gen():
            for mid in ("vendor-haiku-5-5", FULL_ID):
                yield SimpleNamespace(id=mid)
        return gen()


class FakeMessages:
    def __init__(self, reply: str, stop="end_turn"):
        self.reply, self.stop, self.calls = reply, stop, []

    async def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.reply)], stop_reason=self.stop,
                               model=kw["model"], usage=SimpleNamespace(input_tokens=812, output_tokens=40))


def _adapter(reply, stop="end_turn"):
    a = AnthropicAdapter("opus-5-5")
    a._model_id = None
    fake = FakeMessages(reply, stop)
    a._client = SimpleNamespace(beta=SimpleNamespace(messages=fake), messages=fake, models=FakeModels())
    return a, fake


def _item():
    q = Question(qid="t:q0", template="clocks.read_time", text="What time does the clock show?",
                 answer_type=AnswerType.TIME, answer="4:07", skills=["clock_reading"])
    t = Task(task_id="t", family="clocks", seed=1, difficulty=3, scene={}, manifest={}, questions=[q], image_id="t")
    return EvalItem(task=t, question=q, image_png=b"\x89PNG fake", prompt=build_prompt(q))


def test_request_shape_and_parse():
    a, fake = _adapter(json.dumps({"answer": "4:07", "confidence": 0.8}))
    r = asyncio.run(a.answer(_item()))
    assert r.raw == "4:07" and r.confidence == 0.8 and r.error is None
    assert r.input_tokens == 812
    kw = fake.calls[0]
    assert kw["model"] == FULL_ID                      # alias resolved through the Models API
    assert kw["messages"][0]["content"][0]["type"] == "image"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert "thinking" not in kw and "temperature" not in kw
    assert a.label == "Anthropic Opus 5.5" and a.id == "anthropic:opus-5-5"


def test_refusal_is_reported_not_graded_as_answer():
    a, _ = _adapter("", stop="refusal")
    r = asyncio.run(a.answer(_item()))
    assert r.raw is None and r.error == "refusal"
