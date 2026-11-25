"""Rendered data tables: lookup, extremes, column sums, row-wise comparison."""
from __future__ import annotations

import copy
import itertools
from functools import lru_cache

import numpy as np
from PIL import Image, ImageFilter

from ..core.palette import INK
from ..core.render import SS, Canvas, font
from ..core.spec import AnswerType, Rejected, Skill
from .base import Family, VerifyError

THEMES = [
    {"title": "Quarterly sales by product", "rownoun": "product", "rowhead": "Product",
     "rows": ["Atlas", "Beacon", "Cinder", "Drift", "Ember", "Fjord", "Glint", "Harbor", "Ivory", "Juniper", "Kestrel"],
     "cols": ["Q1", "Q2", "Q3", "Q4", "Q5"]},
    {"title": "Monthly rainfall (mm) by city", "rownoun": "city", "rowhead": "City",
     "rows": ["Mumbai", "Chennai", "Kolkata", "Jaipur", "Lucknow", "Bhopal", "Kochi", "Guwahati", "Surat", "Nashik", "Vizag"],
     "cols": ["Jun", "Jul", "Aug", "Sep", "Oct"]},
    {"title": "Exam scores by student", "rownoun": "student", "rowhead": "Student",
     "rows": ["Aarav", "Bella", "Chen", "Divya", "Elena", "Farhan", "Grace", "Hiro", "Isha", "Jonas", "Kavya"],
     "cols": ["Math", "Physics", "Chemistry", "Biology", "English"]},
    {"title": "Tickets resolved by agent", "rownoun": "agent", "rowhead": "Agent",
     "rows": ["Arjun", "Bianca", "Carlos", "Deepa", "Erik", "Fatima", "Gopal", "Hana", "Ivan", "Jia", "Kofi"],
     "cols": ["Mon", "Tue", "Wed", "Thu", "Fri"]},
]
N_ROWS = {1: (3, 3), 2: (4, 4), 3: (5, 6), 4: (7, 8), 5: (9, 10)}
N_COLS = {1: 2, 2: 3, 3: 3, 4: 4, 5: 5}
VMAX = {1: 99, 2: 99, 3: 999, 4: 999, 5: 999}
FSIZE = {1: 18, 2: 17, 3: 16, 4: 15, 5: 14}
W = 720
STRIPE = (241, 245, 249)


def advance(size: int) -> float:
    """Advance width of one monospaced digit, in final pixels."""
    return font(size * SS, mono=True).getlength("0") / SS


@lru_cache(maxsize=16)
def digit_templates(size: int) -> dict[str, list[np.ndarray]]:
    """Fixed-pitch digit cells produced by exactly the same render path as the tables.

    Each template is the full advance-width cell (not just the ink), so matching
    does not depend on the gaps between glyphs, which blur and downscaling erase."""
    adv = advance(size)
    out = {}
    for ch in "0123456789":
        variants = []
        for dx in (0.0, 0.25, 0.5, 0.75):          # sub-pixel phases seen in real cells
            for dy in (0.0, 0.5):
                c = Canvas(48, 40)
                right = 36 + dx
                c.text(right, 20 + dy, ch, size=size, anchor="rm", mono=True)
                tile = c.finish().convert("L")
                for blur in (0.0, 0.8, 1.4):        # matched filters for degraded inputs
                    t = tile.filter(ImageFilter.GaussianBlur(blur)) if blur else tile
                    g = 255 - np.asarray(t, dtype=np.float32)
                    ys = np.flatnonzero(g.max(axis=1) > 0.35 * g.max())
                    x0, x1 = int(round(right - adv)), int(round(right))
                    variants.append(_norm(g[ys.min():ys.max() + 1, x0:x1]))
        out[ch] = variants
    return out


def _norm(glyph: np.ndarray) -> np.ndarray:
    im = Image.fromarray(np.clip(glyph, 0, 255).astype(np.uint8)).resize((12, 18), Image.BILINEAR)
    a = np.asarray(im, dtype=np.float32)
    a -= a.mean()
    n = np.linalg.norm(a)
    return a / n if n else a


class TableFamily(Family):
    name = "tables"
    title = "Data tables"
    description = "Rendered tables of integers: cell lookup, column maximum, column totals, row-wise comparisons and reverse lookup."
    skills = [Skill.OCR.value, Skill.ARITHMETIC.value, Skill.COMPARISON.value, Skill.COUNTING.value]
    knobs = {"rows": "3 -> 10", "numeric columns": "2 -> 5", "values": "2 -> 3 digits", "font": "18px -> 14px, zebra rows"}
    phrasings = {
        "lookup": ["What is the {col} value for {row}?", "Find the cell in row {row}, column {col}. What number is there?"],
        "argmax": ["Which {rownoun} has the highest {col} value?", "In the {col} column, which {rownoun} has the largest number?"],
        "argmin": ["Which {rownoun} has the lowest {col} value?", "In the {col} column, which {rownoun} has the smallest number?"],
        "col_sum": ["What is the sum of all values in the {col} column?", "Add up the {col} column. What is the total?"],
        "count_gt": ["For how many {rownoun}s is {a} greater than {b}?", "Count the rows where the {a} value exceeds the {b} value."],
        "reverse": ["Which {rownoun} has a {col} value of exactly {v}?", "Whose {col} entry is {v}?"],
    }

    def sample_scene(self, r, d):
        th = r.choice(THEMES)
        nr = r.randint(*N_ROWS[d])
        rows = r.sample(th["rows"], nr)
        cols = th["cols"][:N_COLS[d]]
        lo = 10 if VMAX[d] < 100 else 100 if d >= 4 else 10
        cells = [[r.randint(lo, VMAX[d]) for _ in cols] for _ in rows]
        return {"theme": {k: th[k] for k in ("title", "rownoun", "rowhead")}, "rows": rows, "cols": cols,
                "cells": cells, "font": FSIZE[d], "stripes": d >= 2, "difficulty": d}

    def facts_from_scene(self, s):
        return {"rows": s["rows"], "cols": s["cols"], "cells": s["cells"]}

    def render(self, s):
        fs = s["font"]
        rh = int(fs * 2.1)
        lw, cw = 170, 110
        tw = lw + cw * len(s["cols"])
        Ht = 70 + rh * (len(s["rows"]) + 1) + 30
        Wt = max(W, tw + 60)
        c = Canvas(Wt, Ht)
        x0 = (Wt - tw) / 2
        y0 = 62
        c.text(Wt / 2, 20, s["theme"]["title"], size=18, bold=True, anchor="mt")
        c.rect(x0, y0, x0 + tw, y0 + rh, fill=(226, 232, 240))
        c.text(x0 + 12, y0 + rh / 2, s["theme"]["rowhead"], size=fs, bold=True, anchor="lm")
        for j, col in enumerate(s["cols"]):
            c.text(x0 + lw + cw * (j + 1) - 14, y0 + rh / 2, col, size=fs, bold=True, anchor="rm")
        boxes = []
        for i, (row, vals) in enumerate(zip(s["rows"], s["cells"])):
            top = y0 + rh * (i + 1)
            if s["stripes"] and i % 2 == 1:
                c.rect(x0, top, x0 + tw, top + rh, fill=STRIPE)
            c.text(x0 + 12, top + rh / 2, row, size=fs, anchor="lm")
            rb = []
            for j, v in enumerate(vals):
                right = x0 + lw + cw * (j + 1) - 14
                c.text(right, top + rh / 2, str(v), size=fs, anchor="rm", mono=True)
                rb.append([x0 + lw + cw * j + 4, top + 2, right + 4, top + rh - 2])
            boxes.append(rb)
            c.line([(x0, top), (x0 + tw, top)], (203, 213, 225), 1)
        c.rect(x0, y0, x0 + tw, y0 + rh * (len(s["rows"]) + 1), outline=INK, width=1.5)
        return c.finish(), {"rows": s["rows"], "cols": s["cols"], "cell_boxes": boxes, "font": fs}

    def question_candidates(self, s, f, r, d):
        rows, cols, cells = f["rows"], f["cols"], f["cells"]
        base = dict(s["theme"])
        out = []
        for i, row in enumerate(rows):
            for j, col in enumerate(cols):
                out.append(("lookup", {**base, "row": row, "col": col}))
        for j, col in enumerate(cols):
            colv = [cells[i][j] for i in range(len(rows))]
            if colv.count(max(colv)) == 1:
                out.append(("argmax", {**base, "col": col}))
            if colv.count(min(colv)) == 1:
                out.append(("argmin", {**base, "col": col}))
            if d >= 2:
                out.append(("col_sum", {**base, "col": col}))
            for v in colv:
                if colv.count(v) == 1:
                    out.append(("reverse", {**base, "col": col, "v": v}))
        for (ja, a), (jb, b) in itertools.permutations(list(enumerate(cols)), 2):
            if all(cells[i][ja] != cells[i][jb] for i in range(len(rows))):
                out.append(("count_gt", {**base, "a": a, "b": b}))
        return out

    def answer(self, t, p, f):
        rows, cols, cells = f["rows"], f["cols"], f["cells"]
        col = lambda name: [cells[i][cols.index(name)] for i in range(len(rows))]
        if t == "lookup":
            return cells[rows.index(p["row"])][cols.index(p["col"])]
        if t == "argmax":
            v = col(p["col"])
            return rows[v.index(max(v))]
        if t == "argmin":
            v = col(p["col"])
            return rows[v.index(min(v))]
        if t == "col_sum":
            return sum(col(p["col"]))
        if t == "count_gt":
            return sum(a > b for a, b in zip(col(p["a"]), col(p["b"])))
        if t == "reverse":
            return rows[col(p["col"]).index(p["v"])]
        raise KeyError(t)

    def question_meta(self, t, p, s):
        O, A, C, N = Skill.OCR.value, Skill.ARITHMETIC.value, Skill.COMPARISON.value, Skill.COUNTING.value
        return {
            "lookup": {"answer_type": AnswerType.INTEGER, "skills": [O]},
            "argmax": {"answer_type": AnswerType.CHOICE, "skills": [O, C], "choices": s["rows"]},
            "argmin": {"answer_type": AnswerType.CHOICE, "skills": [O, C], "choices": s["rows"]},
            "col_sum": {"answer_type": AnswerType.INTEGER, "skills": [O, A]},
            "count_gt": {"answer_type": AnswerType.INTEGER, "skills": [O, C, N]},
            "reverse": {"answer_type": AnswerType.CHOICE, "skills": [O], "choices": s["rows"]},
        }[t]

    # ---- verification: template OCR on the rendered pixels ------------------------
    def read_number(self, gray_ink: np.ndarray, size: int, right: float) -> int:
        """Fixed-pitch template OCR: numbers are right-aligned monospaced digits,
        so digit k occupies [right - (n-k)*adv, right - (n-k-1)*adv]."""
        thr = max(45.0, 0.35 * float(gray_ink.max()))   # relative threshold survives blur and low contrast
        ink = gray_ink > thr
        xs, ys = np.flatnonzero(ink.any(axis=0)), np.flatnonzero(ink.any(axis=1))
        if len(xs) == 0:
            raise VerifyError("empty cell")
        adv = advance(size)
        n = int(round((right - xs.min()) / adv))
        if not 1 <= n <= 6:
            raise VerifyError(f"implausible digit count {n}")
        tpl = digit_templates(size)
        digits = ""
        for k in range(n):
            x1 = right - (n - 1 - k) * adv
            g = gray_ink[ys.min():ys.max() + 1, int(round(x1 - adv)):int(round(x1))]
            v = _norm(g)
            scores = {ch: max(float((v * t).sum()) for t in ts) for ch, ts in tpl.items()}
            ranked = sorted(scores, key=scores.get, reverse=True)
            best, second = ranked[0], ranked[1]
            if scores[best] < 0.70 or scores[best] - scores[second] < 0.06:
                raise VerifyError(f"ambiguous glyph ({best} {scores[best]:.2f} vs {second} {scores[second]:.2f})")
            digits += best
        return int(digits)

    def measure(self, img, man):
        gray = 255 - np.asarray(Image.fromarray(img).convert("L"), dtype=np.float32)
        cells = []
        for rb in man["cell_boxes"]:
            row = []
            for x0, y0, x1, y1 in rb:
                crop = gray[int(y0):int(y1), int(x0):int(x1)]
                crop = np.where(crop > 25, crop, 0)  # drop zebra stripe tint
                row.append(self.read_number(crop, man["font"], (x1 - 4) - int(x0)))
            cells.append(row)
        return {"rows": man["rows"], "cols": man["cols"], "cells": cells}

    def compare_facts(self, truth, measured):
        probs = []
        for i, (a, b) in enumerate(zip(truth["cells"], measured["cells"])):
            for j, (x, y) in enumerate(zip(a, b)):
                if x != y:
                    probs.append(f"{truth['rows'][i]}/{truth['cols'][j]}: scene={x} pixels={y}")
        return probs

    def mutate(self, s, r, hint=None):
        s2 = copy.deepcopy(s)
        hint = hint or {}
        i = s2["rows"].index(hint["row"]) if "row" in hint else r.randrange(len(s2["rows"]))
        col = hint.get("col") or (hint.get(r.choice(["a", "b"])) if "a" in hint else None)
        j = s2["cols"].index(col) if col else r.randrange(len(s2["cols"]))
        lo = 10 if VMAX[s2["difficulty"]] < 100 else 100 if s2["difficulty"] >= 4 else 10
        s2["cells"][i][j] = r.randint(lo, VMAX[s2["difficulty"]])
        return s2
