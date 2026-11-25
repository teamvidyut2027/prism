"""Bar charts: extremum, value reading, thresholds, differences, ranking."""
from __future__ import annotations

import copy
import itertools
import math

import numpy as np

from ..core.palette import GRID, INK, NAMED, color_mask, srgb_to_lab
from ..core.render import Canvas
from ..core.spec import AnswerType, Rejected, Skill
from .base import Family, VerifyError

THEMES = [
    {"title": "Harvest by fruit", "noun": "fruit", "plural": "fruits", "measure": "harvest", "unit": "tonnes",
     "cats": ["Apple", "Banana", "Cherry", "Mango", "Grape", "Lemon", "Peach", "Pear", "Plum", "Kiwi", "Melon", "Papaya"]},
    {"title": "Units sold by product", "noun": "product", "plural": "products", "measure": "sales volume", "unit": "units",
     "cats": ["Alpha", "Bravo", "Cobalt", "Delta", "Echo", "Falcon", "Granite", "Helix", "Ion", "Jade", "Krypton", "Lumen"]},
    {"title": "Annual rainfall by city", "noun": "city", "plural": "cities", "measure": "rainfall", "unit": "mm",
     "cats": ["Pune", "Delhi", "Kochi", "Agra", "Surat", "Patna", "Indore", "Mysore", "Ranchi", "Shimla", "Nagpur", "Goa"]},
    {"title": "League points by team", "noun": "team", "plural": "teams", "measure": "points total", "unit": "pts",
     "cats": ["Lions", "Hawks", "Wolves", "Tigers", "Bears", "Sharks", "Eagles", "Falcons", "Panthers", "Cobras", "Bulls", "Rhinos"]},
    {"title": "Energy output by plant", "noun": "plant", "plural": "plants", "measure": "power output", "unit": "MW",
     "cats": ["Solar A", "Wind B", "Hydro C", "Gas D", "Solar E", "Wind F", "Hydro G", "Gas H", "Solar I", "Wind J"]},
    {"title": "Visitors by museum", "noun": "museum", "plural": "museums", "measure": "visitor count", "unit": "thousand",
     "cats": ["Louvre", "Prado", "Uffizi", "Tate", "Hermitage", "Met", "Rijks", "Orsay", "Getty", "Vatican", "Acropolis"]},
]

N_BARS = {1: (3, 4), 2: (4, 5), 3: (5, 7), 4: (6, 8), 5: (8, 10)}
MARGIN = {1: 0.10, 2: 0.08, 3: 0.06, 4: 0.05, 5: 0.04}   # fraction of axis -> min visible gap
GRAIN_DIV = {1: 10, 2: 20, 3: 50, 4: 50, 5: 50}
W, H = 720, 480


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


class BarChartFamily(Family):
    name = "bars"
    title = "Bar charts"
    description = "Vertical and horizontal bar charts with known values: extremes, value reading, thresholds, differences and ranking."
    skills = [Skill.COMPARISON.value, Skill.NUMERIC_READING.value, Skill.COUNTING.value, Skill.ARITHMETIC.value]
    knobs = {"bars": "3-4 -> 8-10", "gap between compared bars": "10% -> 4% of the axis",
             "value labels": "shown -> hidden", "orientation": "vertical -> also horizontal, rotated labels"}
    phrasings = {
        "argmax": ["Which {noun} has the highest {measure}?",
                   "In this chart, which {noun} shows the largest {measure} value?",
                   "Identify the {noun} with the tallest/longest bar."],
        "argmin": ["Which {noun} has the lowest {measure}?",
                   "Which {noun} shows the smallest {measure} value in the chart?"],
        "value": ["What is the {measure} of {label}?",
                  "Read the chart: what value does the bar for {label} show?"],
        "count_above": ["How many {plural} have a {measure} greater than {threshold}?",
                        "Count the bars whose value is above {threshold}."],
        "diff": ["By how much does the {measure} of {a} exceed that of {b}?",
                 "What is the difference between {a} and {b} (value of {a} minus value of {b})?"],
        "compare": ["Is the {measure} of {a} greater than the {measure} of {b}?",
                    "Does {a} have a higher {measure} than {b}?"],
        "rank": ["List all {plural} from highest to lowest {measure}.",
                 "Order the bars by value, largest first, giving the {noun} names."],
    }

    # ---- scene --------------------------------------------------------------
    def sample_scene(self, r, d):
        theme = r.choice(THEMES)
        n = r.randint(*N_BARS[d])
        labels = r.sample(theme["cats"], n)
        axis_max = r.choice([10, 20, 50, 100, 200, 500, 1000] if d >= 2 else [10, 20, 50, 100])
        grain = max(1, axis_max // GRAIN_DIV[d])
        kmax = axis_max // grain
        values = [r.randint(max(1, math.ceil(0.08 * kmax)), kmax) * grain for _ in range(n)]
        orientation = "h" if (d >= 3 and r.random() < 0.4) else "v"
        multi = d >= 2 and r.random() < 0.5
        colors = r.sample(list(NAMED), n) if multi else [r.choice(list(NAMED))] * n
        return {
            "theme": {k: theme[k] for k in ("title", "noun", "plural", "measure", "unit")},
            "labels": labels, "values": values, "axis_max": axis_max, "grain": grain,
            "orientation": orientation, "colors": colors,
            "show_values": d <= 2 or (d == 3 and r.random() < 0.5),
            "gridlines": d <= 4 or r.random() < 0.5,
            "label_angle": 35 if (orientation == "v" and n >= 8) else 0,
            "margin": MARGIN[d] * axis_max, "difficulty": d,
        }

    def facts_from_scene(self, scene):
        return {"values": dict(zip(scene["labels"], scene["values"]))}

    # ---- rendering ------------------------------------------------------------
    def render(self, s):
        c = Canvas(W, H)
        th = s["theme"]
        c.text(W / 2, 14, th["title"], size=18, bold=True, anchor="mt")
        n, amax, vertical = len(s["labels"]), s["axis_max"], s["orientation"] == "v"
        if vertical:
            x0, y0, x1, y1 = 80, 60, W - 30, H - (95 if s["label_angle"] else 60)
        else:
            x0, y0, x1, y1 = 120, 60, W - 50, H - 50
        plot_len = (y1 - y0) if vertical else (x1 - x0)
        # grid + ticks
        for i in range(6):
            v = amax * i / 5
            if vertical:
                y = y1 - plot_len * i / 5
                if s["gridlines"] and i:
                    c.line([(x0, y), (x1, y)], GRID, 1)
                c.text(x0 - 8, y, _fmt(v), size=12, anchor="rm", fill=INK)
            else:
                x = x0 + plot_len * i / 5
                if s["gridlines"] and i:
                    c.line([(x, y0), (x, y1)], GRID, 1)
                c.text(x, y1 + 8, _fmt(v), size=12, anchor="mt", fill=INK)
        unit = f"{th['measure']} ({th['unit']})"
        if vertical:
            c.text(20, (y0 + y1) / 2, unit, size=12, anchor="mm", angle=90)
        else:
            c.text((x0 + x1) / 2, H - 14, unit, size=12, anchor="mb")
        slot = ((x1 - x0) if vertical else (y1 - y0)) / n
        thick = slot * 0.62
        slots = []
        for i, (lab, val, col) in enumerate(zip(s["labels"], s["values"], s["colors"])):
            rgb = NAMED[col]
            centre = (x0 if vertical else y0) + slot * (i + 0.5)
            ext = plot_len * val / amax
            if vertical:
                c.rect(centre - thick / 2, y1 - ext, centre + thick / 2, y1, fill=rgb)
                if s["show_values"]:
                    c.text(centre, y1 - ext - 4, _fmt(val), size=12, anchor="mb", bold=True)
                if s["label_angle"]:
                    c.text(centre + 4, y1 + 30, lab, size=12, anchor="mm", angle=s["label_angle"])
                else:
                    c.text(centre, y1 + 8, lab, size=13, anchor="mt")
            else:
                c.rect(x0, centre - thick / 2, x0 + ext, centre + thick / 2, fill=rgb)
                if s["show_values"]:
                    c.text(x0 + ext + 5, centre, _fmt(val), size=12, anchor="lm", bold=True)
                c.text(x0 - 8, centre, lab, size=13, anchor="rm")
            slots.append({"label": lab, "centre": centre, "rgb": rgb})
        # axes on top
        if vertical:
            c.line([(x0, y0), (x0, y1), (x1, y1)], INK, 1.5)
        else:
            c.line([(x0, y0), (x0, y1), (x1, y1)], INK, 1.5)
        manifest = {"orientation": s["orientation"], "plot": [x0, y0, x1, y1], "axis_max": amax,
                    "grain": s["grain"], "thickness": thick, "slots": slots}
        return c.finish(), manifest

    # ---- questions ------------------------------------------------------------
    def question_candidates(self, s, facts, r, d):
        vals, labels, m = facts["values"], s["labels"], s["margin"]
        base = dict(s["theme"])
        srt = sorted(labels, key=vals.get, reverse=True)
        out = []
        if vals[srt[0]] - vals[srt[1]] >= m:
            out.append(("argmax", base))
        if vals[srt[-2]] - vals[srt[-1]] >= m:
            out.append(("argmin", base))
        for lab in labels:
            out.append(("value", {**base, "label": lab}))
        for i in range(1, 5):
            t = s["axis_max"] * i // 5
            if all(abs(v - t) >= m for v in vals.values()) and 0 < sum(v > t for v in vals.values()) < len(labels):
                out.append(("count_above", {**base, "threshold": t}))
        for a, b in itertools.permutations(labels, 2):
            gap = vals[a] - vals[b]
            if abs(gap) >= m:
                out.append(("compare", {**base, "a": a, "b": b}))
                if gap > 0:
                    out.append(("diff", {**base, "a": a, "b": b}))
        if d >= 3 and len(labels) <= 7 and all(vals[srt[i]] - vals[srt[i + 1]] >= m for i in range(len(srt) - 1)):
            out.append(("rank", base))
        return out

    def answer(self, t, p, facts):
        v = facts["values"]
        if t == "argmax":
            return max(v, key=v.get)
        if t == "argmin":
            return min(v, key=v.get)
        if t == "value":
            return v[p["label"]]
        if t == "count_above":
            return sum(x > p["threshold"] for x in v.values())
        if t == "diff":
            return v[p["a"]] - v[p["b"]]
        if t == "compare":
            return v[p["a"]] > v[p["b"]]
        if t == "rank":
            return sorted(v, key=v.get, reverse=True)
        raise KeyError(t)

    def question_meta(self, t, p, s):
        labelled = s["show_values"]
        read = [Skill.NUMERIC_READING.value] + ([Skill.OCR.value] if labelled else [])
        tol = 0.0 if labelled else 0.04 * s["axis_max"]
        return {
            "argmax": {"answer_type": AnswerType.CHOICE, "skills": [Skill.COMPARISON.value], "choices": s["labels"]},
            "argmin": {"answer_type": AnswerType.CHOICE, "skills": [Skill.COMPARISON.value], "choices": s["labels"]},
            "value": {"answer_type": AnswerType.NUMBER, "skills": read, "tolerance": tol},
            "count_above": {"answer_type": AnswerType.INTEGER,
                            "skills": [Skill.COUNTING.value, Skill.COMPARISON.value, Skill.NUMERIC_READING.value]},
            "diff": {"answer_type": AnswerType.NUMBER, "skills": read + [Skill.ARITHMETIC.value],
                     "tolerance": 0.0 if labelled else 0.06 * s["axis_max"]},
            "compare": {"answer_type": AnswerType.BOOLEAN, "skills": [Skill.COMPARISON.value]},
            "rank": {"answer_type": AnswerType.SEQUENCE, "skills": [Skill.COMPARISON.value], "choices": s["labels"]},
        }[t]

    # ---- independent verification ------------------------------------------------
    def measure(self, img, man):
        lab = srgb_to_lab(img)
        x0, y0, x1, y1 = man["plot"]
        vertical = man["orientation"] == "v"
        plot_len = (y1 - y0) if vertical else (x1 - x0)
        half = max(2, int(man["thickness"] * 0.25))
        values = {}
        for sl in man["slots"]:
            c = int(round(sl["centre"]))
            if vertical:
                band = lab[int(y0):int(y1) - 2, c - half:c + half + 1]
                mask = color_mask(None, sl["rgb"], lab=band).mean(axis=1) >= 0.5   # rows, top->bottom
                mask = mask[::-1]                                                   # baseline -> top
            else:
                band = lab[c - half:c + half + 1, int(x0) + 2:int(x1)]
                mask = color_mask(None, sl["rgb"], lab=band).mean(axis=0) >= 0.5   # cols, left->right
            if not mask[:3].any():
                raise VerifyError(f"bar for {sl['label']} not found at its slot")
            run = int(np.argmin(mask)) if not mask.all() else len(mask)
            ext = run + 2  # the 2px skipped next to the axis line
            v = ext / plot_len * man["axis_max"]
            values[sl["label"]] = int(round(v / man["grain"]) * man["grain"])
        return {"values": values}

    def compare_facts(self, truth, measured):
        return [f"{k}: scene={truth['values'][k]} pixels={measured['values'].get(k)}"
                for k in truth["values"] if truth["values"][k] != measured["values"].get(k)]

    def mutate(self, s, r, hint=None):
        s2 = copy.deepcopy(s)
        hint = hint or {}
        named = [hint[k] for k in ("label", "a", "b") if k in hint]
        i = s2["labels"].index(r.choice(named)) if named else r.randrange(len(s2["values"]))
        if "threshold" in hint:   # push one bar across the threshold
            t, g = hint["threshold"], s2["grain"]
            v = s2["values"][i]
            off = max(g, int(round(s2["margin"] * r.uniform(1.2, 2.0) / g)) * g)
            nv = t - off if v > t else t + off
            if 0.08 * s2["axis_max"] <= nv <= s2["axis_max"]:
                s2["values"][i] = nv
                return s2
            return None
        step = max(s2["grain"], int(round(s2["margin"] * r.uniform(1.5, 3) / s2["grain"])) * s2["grain"])
        nv = s2["values"][i] + (step if r.random() < 0.5 else -step)
        if not (s2["grain"] <= nv <= s2["axis_max"]) or nv < 0.08 * s2["axis_max"]:
            nv = s2["values"][i] - (nv - s2["values"][i])
        if not (0.08 * s2["axis_max"] <= nv <= s2["axis_max"]):
            return None
        s2["values"][i] = nv
        return s2
