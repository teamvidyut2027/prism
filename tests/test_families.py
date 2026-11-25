"""Every family: the pixel verifier recovers the scene, answers agree, renders are deterministic,
and the verifier catches corrupted labels."""
import numpy as np
import pytest

from prism.core.render import sha256
from prism.core.rng import rng
from prism.core.spec import AnswerType, Rejected
from prism.families import REGISTRY, VerifyError

FAMILIES = sorted(REGISTRY)


def scenes(fam, n_per_level=4, seed=11):
    for d in range(1, 6):
        for i in range(n_per_level):
            try:
                yield d, fam.sample_scene(rng(seed, fam.name, d, i), d)
            except Rejected:
                continue


@pytest.mark.parametrize("name", FAMILIES)
def test_verifier_recovers_scene(name):
    fam = REGISTRY[name]
    total = agree = 0
    for d, s in scenes(fam):
        img, man = fam.render(s)
        total += 1
        try:
            if not fam.compare_facts(fam.facts_from_scene(s), fam.measure(np.asarray(img), man)):
                agree += 1
        except VerifyError:
            pass
    assert total >= 15
    assert agree / total >= 0.9, f"{name}: verifier agreed on only {agree}/{total}"


@pytest.mark.parametrize("name", FAMILIES)
def test_render_is_deterministic(name):
    fam = REGISTRY[name]
    for _, s in list(scenes(fam, 1)):
        assert sha256(fam.render(s)[0]) == sha256(fam.render(s)[0])


@pytest.mark.parametrize("name", FAMILIES)
def test_verifier_catches_corrupted_labels(name):
    """Render an edited scene but claim the original facts: the verifier must object."""
    fam = REGISTRY[name]
    checked = 0
    for d, s in scenes(fam, 3, seed=5):
        f = fam.facts_from_scene(s)
        for k in range(10):
            s2 = fam.mutate(s, rng(5, "mut", d, k))
            if s2 is not None and fam.facts_from_scene(s2) != f:
                img2, man2 = fam.render(s2)
                try:
                    problems = fam.compare_facts(f, fam.measure(np.asarray(img2), man2))
                except VerifyError:
                    problems = ["unreadable"]
                assert problems, f"{name}: corrupted label went unnoticed"
                checked += 1
                break
    assert checked >= 10


@pytest.mark.parametrize("name", FAMILIES)
def test_questions_are_well_formed(name):
    fam = REGISTRY[name]
    for d, s in scenes(fam, 2):
        f = fam.facts_from_scene(s)
        try:
            qs = fam.build_questions("t", s, f, rng(3, d), d, 3)
        except Rejected:
            continue
        assert len({q.template for q in qs}) == len(qs), "templates should be distinct within a task"
        for q in qs:
            assert q.text and "{" not in q.text, q.text
            if q.answer_type == AnswerType.CHOICE:
                assert q.answer in q.choices
            if q.answer_type == AnswerType.BOOLEAN:
                assert isinstance(q.answer, bool)


def test_seeded_scenes_are_reproducible():
    fam = REGISTRY["shapes"]
    a = fam.sample_scene(rng(1, 2, 3), 4)
    b = fam.sample_scene(rng(1, 2, 3), 4)
    assert a == b
    assert a != fam.sample_scene(rng(1, 2, 4), 4)
