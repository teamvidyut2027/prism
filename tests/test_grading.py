import pytest

from prism.core.spec import AnswerType, Question
from prism.grading.grader import grade


def q(t, ans, choices=None, tol=0.0):
    return Question(qid="x", template="f.t", text="?", answer_type=t, answer=ans, skills=[], choices=choices,
                    tolerance=tol)


@pytest.mark.parametrize("raw,ok", [("7", True), ("Seven", True), ("**7**", True), ("7 objects", True),
                                    ("The answer is 7.", True), ("8", False), ("", False), ("none", False)])
def test_integer(raw, ok):
    assert grade(q(AnswerType.INTEGER, 7), raw).correct is ok


def test_integer_zero_words():
    assert grade(q(AnswerType.INTEGER, 0), "none").correct
    assert grade(q(AnswerType.INTEGER, 0), "zero").correct


@pytest.mark.parametrize("raw,ok", [("48", True), ("53", True), ("53.5", False), ("1,050", False)])
def test_number_tolerance(raw, ok):
    assert grade(q(AnswerType.NUMBER, 50, tol=3.0), raw).correct is ok


@pytest.mark.parametrize("raw,ans,ok", [("Yes.", True, True), ("no", False, True), ("TRUE", True, True),
                                        ("No, it is not.", True, False), ("maybe", True, False)])
def test_boolean(raw, ans, ok):
    assert grade(q(AnswerType.BOOLEAN, ans), raw).correct is ok


@pytest.mark.parametrize("raw,ok", [("3:05", True), ("03:05", True), ("3:05 PM", True), ("15:05", True),
                                    ("3.05", True), ("3:06", False), ("5:15", False)])
def test_time(raw, ok):
    assert grade(q(AnswerType.TIME, "3:05"), raw).correct is ok


def test_time_error_is_circular():
    g = grade(q(AnswerType.TIME, "12:02"), "11:58")
    assert not g.correct and g.error == 4


@pytest.mark.parametrize("raw,ok", [("Solar A", True), ("solar a", True), ("The answer is Solar A.", True),
                                    ("Wind B", False), ("A", False)])
def test_choice(raw, ok):
    assert grade(q(AnswerType.CHOICE, "Solar A", ["Solar A", "Wind B", "Gas D"]), raw).correct is ok


def test_choice_plural():
    assert grade(q(AnswerType.CHOICE, "circle", ["circle", "square"]), "circles").correct


def test_sequence():
    qq = q(AnswerType.SEQUENCE, ["Pear", "Kiwi", "Plum"], ["Pear", "Kiwi", "Plum"])
    assert grade(qq, "Pear, Kiwi, Plum").correct
    assert grade(qq, "1. Pear\n2. Kiwi\n3. Plum").correct
    assert grade(qq, ["Pear", "Kiwi", "Plum"]).correct
    assert not grade(qq, "Kiwi, Pear, Plum").correct


def test_none_is_wrong():
    assert not grade(q(AnswerType.INTEGER, 3), None).correct
