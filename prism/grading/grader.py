"""Answer normalisation and grading.

Models answer in free text (or a JSON ``answer`` field). The grader is strict
about *meaning* and lenient about *format*: "Seven", "7", "7 objects" and
"**7**" are all 7; "3:05 PM", "3:05" and "03:05" are all 3:05; "Yes." is True.
Every grade records the parsed value so a reviewer can audit a decision.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..core.spec import AnswerType, Question

WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
         "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "none": 0, "no": 0}
YES = {"yes", "true", "y", "correct", "affirmative"}
NO = {"no", "false", "n", "incorrect", "negative"}
NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


@dataclass
class Grade:
    correct: bool
    parsed: Any
    error: float | None = None      # numeric / time error magnitude when meaningful
    note: str = ""


def _clean(s: str) -> str:
    s = str(s).strip()
    s = re.sub(r"[*_`#>]", "", s)               # markdown
    s = re.sub(r"^(the\s+)?(final\s+)?answer\s*(is)?\s*[:\-]?\s*", "", s, flags=re.I)
    return s.strip().strip(".").strip()


def _norm_label(s: str) -> str:
    s = _clean(s).lower()
    s = re.sub(r"^(the|a|an)\s+", "", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_number(s: str) -> float | None:
    c = _clean(s).lower().replace(",", "")
    m = NUM.search(c)
    if m:
        return float(m.group())
    for w, v in WORDS.items():
        if re.search(rf"\b{w}\b", c):
            return float(v)
    return None


def parse_bool(s: str) -> bool | None:
    toks = _norm_label(s).split()
    if not toks:
        return None
    if toks[0] in YES:
        return True
    if toks[0] in NO:
        return False
    has_y, has_n = any(t in YES for t in toks), any(t in NO for t in toks)
    return True if has_y and not has_n else False if has_n and not has_y else None


def parse_time(s: str) -> tuple[int, int] | None:
    c = _clean(s).lower()
    m = re.search(r"(\d{1,2})\s*[:.h]\s*(\d{2})", c)
    if m:
        h, mm = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"\b(\d{1,2})\s*(o'?clock|am|pm)\b", c)
        if not m:
            return None
        h, mm = int(m.group(1)), 0
    if not (0 <= h <= 23 and 0 <= mm <= 59):
        return None
    h = h % 12 or 12
    return h, mm


def parse_choice(s: str, choices: list[str]) -> str | None:
    c = _norm_label(s)
    norm = {_norm_label(x): x for x in choices}
    if c in norm:
        return norm[c]
    # whole-word containment, longest label first ("Solar A" before "A")
    hits = [x for k, x in sorted(norm.items(), key=lambda kv: -len(kv[0])) if re.search(rf"\b{re.escape(k)}\b", c)]
    if len(hits) == 1:
        return hits[0]
    if hits:
        # several labels mentioned: take the one that appears first
        return min(hits, key=lambda x: c.find(_norm_label(x)))
    # singular/plural tolerance (e.g. "circles" for "circle")
    for k, x in norm.items():
        if c.rstrip("s") == k.rstrip("s"):
            return x
    return None


def parse_sequence(s: str | list, choices: list[str]) -> list[str] | None:
    items = s if isinstance(s, list) else re.split(r"\s*(?:,|;|>|\n|\bthen\b|->|→)\s*", _clean(s))
    out = []
    for it in items:
        it = re.sub(r"^\s*\d+[.)]\s*", "", str(it))
        ch = parse_choice(it, choices)
        if ch:
            out.append(ch)
    return out or None


def _minutes(h: int, m: int) -> int:
    return (h % 12) * 60 + m


def grade(q: Question, raw: Any) -> Grade:
    t = q.answer_type
    if raw is None:
        return Grade(False, None, note="no answer")
    if isinstance(raw, (list, tuple)) and t != AnswerType.SEQUENCE:
        raw = raw[0] if raw else ""
    s = raw if isinstance(raw, list) else str(raw)
    if t == AnswerType.INTEGER:
        v = parse_number(s)
        if v is None:
            return Grade(False, None, note="unparseable number")
        return Grade(v == q.answer, v, error=abs(v - q.answer))
    if t == AnswerType.NUMBER:
        v = parse_number(s)
        if v is None:
            return Grade(False, None, note="unparseable number")
        err = abs(v - float(q.answer))
        return Grade(err <= q.tolerance + 1e-9, v, error=err)
    if t == AnswerType.BOOLEAN:
        v = parse_bool(s)
        return Grade(v is not None and v == q.answer, v, note="" if v is not None else "not yes/no")
    if t == AnswerType.CHOICE:
        v = parse_choice(s, q.choices or [str(q.answer)])
        return Grade(v is not None and _norm_label(v) == _norm_label(str(q.answer)), v,
                     note="" if v is not None else "not one of the options")
    if t == AnswerType.TIME:
        v = parse_time(s)
        if v is None:
            return Grade(False, None, note="unparseable time")
        gh, gm = map(int, str(q.answer).split(":"))
        d = abs(_minutes(*v) - _minutes(gh, gm))
        d = min(d, 720 - d)
        return Grade(d == 0, f"{v[0]}:{v[1]:02d}", error=float(d))
    if t == AnswerType.SEQUENCE:
        v = parse_sequence(s, q.choices or list(q.answer))
        return Grade(v == list(q.answer), v)
    raise ValueError(t)


def answer_instruction(q: Question) -> str:
    """Format instruction appended to the question when prompting a model."""
    t = q.answer_type
    if t == AnswerType.INTEGER:
        return "Answer with a single whole number."
    if t == AnswerType.NUMBER:
        return "Answer with a single number (no units)."
    if t == AnswerType.BOOLEAN:
        return "Answer yes or no."
    if t == AnswerType.CHOICE:
        return "Answer with exactly one of: " + ", ".join(q.choices or []) + "."
    if t == AnswerType.TIME:
        return "Answer in H:MM format on a 12-hour clock (for example 4:07)."
    if t == AnswerType.SEQUENCE:
        return "Answer with a comma-separated list, using exactly these names: " + ", ".join(q.choices or []) + "."
    return ""
