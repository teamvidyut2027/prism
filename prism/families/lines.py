"""Multi-series line charts: peaks, values at a point, series comparison, trends."""
from __future__ import annotations

import copy
import itertools

import numpy as np

from ..core.palette import GRID, INK, NAMED, coverage
from ..core.render import Canvas
from ..core.spec import AnswerType, Rejected, Skill
from .base import Family, VerifyError

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
YEARS = [str(y) for y in range(2013, 2026)]
SERIES = [("Revenue", "Cost", "Profit"), ("North", "South", "East"), ("Online", "Retail", "Wholesale"),
          ("Team A", "Team B", "Team C"), ("Wheat", "Rice", "Maize")]
TITLES = ["Quarterly performance", "Regional trend", "Channel comparison", "Throughput over time", "Crop yield trend"]
N_POINTS = {1: (5, 6), 2: (6, 8), 3: (7, 10), 4: (8, 12), 5: (10, 12)}
N_SERIES = {1: (1, 1), 2: (1, 2), 3: (2, 2), 4: (2, 3), 5: (3, 3)}
MARGIN = {1: 0.10, 2: 0.08, 3: 0.07, 4: 0.06, 5: 0.05}
LINE_COLORS = ["blue", "red", "green", "orange", "purple", "teal"]
W, H = 760, 480


class LineChartFamily(Family):
    name = "lines"
    title = "Line charts"
    description = "One to three series over time: peaks, point values, which series leads, direction of change, counting rises."
    skills = [Skill.TREND.value, Skill.NUMERIC_READING.value, Skill.COMPARISON.value, Skill.COUNTING.value,
              Skill.ATTRIBUTE.value]
    knobs = {"points": "5-6 -> 10-12", "series": "1 -> 3 (legend binding)", "separation": "10% -> 5% of axis",
             "markers": "on -> off"}
    phrasings = {
        "peak": ["In which period did {series} reach its highest value?",
                 "At which x-axis label is the {series} line at its maximum?"],
        "value_at": ["What is the value of {series} at {x}?",
                     "Read the chart: what does {series} show for {x}?"],
        "higher_at": ["At {x}, which series has the higher value: {a} or {b}?",
                      "Which is higher at {x}, {a} or {b}?"],
        "change": ["Did {series} increase from {x1} to {x2}?",
                   "Is the value of {series} at {x2} higher than at {x1}?"],
        "count_rises": ["How many times does {series} go up from one point to the next?",
                        "Count the segments where the {series} line rises."],
    }

    def sample_scene(self, r, d):
        n = r.randint(*N_POINTS[d])
        xs = MONTHS[:n] if (n <= 12 and r.random() < 0.5) else YEARS[:n]
        k = r.randint(*N_SERIES[d])
        ti = r.randrange(len(SERIES))
        names = list(SERIES[ti][:k])
        axis_max = r.choice([50, 100, 200, 500, 1000])
        grain = axis_max // 50
        sep = MARGIN[d] * axis_max
        series = {nm: [] for nm in names}
        for _ in range(n):
            for _try in range(60):
                pt = {nm: (series[nm][-1] if series[nm] else r.randint(10, 40) * grain) for nm in names}
                pt = {nm: int(min(48, max(3, round(v / grain + r.gauss(0, 7)))) * grain) for nm, v in pt.items()}
                if all(abs(pt[a] - pt[b]) >= sep for a, b in itertools.combinations(names, 2)):
                    break
            else:
                raise Rejected("series could not be separated at every x")
            for nm in names:
                series[nm].append(pt[nm])
        colors = r.sample(LINE_COLORS, k)
        return {"title": TITLES[ti], "xs": xs, "series": series, "colors": dict(zip(names, colors)),
                "axis_max": axis_max, "grain": grain, "margin": sep, "markers": d <= 3 or r.random() < 0.5,
                "gridlines": d <= 4, "difficulty": d}

    def facts_from_scene(self, s):
        return {"xs": s["xs"], "series": s["series"]}

    def render(self, s):
        c = Canvas(W, H)
        c.text(W / 2, 14, s["title"], size=18, bold=True, anchor="mt")
        x0, y0, x1, y1 = 80, 70, W - 40, H - 60
        amax, xs = s["axis_max"], s["xs"]
        for i in range(6):
            y = y1 - (y1 - y0) * i / 5
            if s["gridlines"] and i:
                c.line([(x0, y), (x1, y)], GRID, 1)
            c.text(x0 - 8, y, str(int(amax * i / 5)), size=12, anchor="rm")
        step = (x1 - x0 - 40) / (len(xs) - 1)
        px = [x0 + 20 + step * i for i in range(len(xs))]
        for x, lab in zip(px, xs):
            c.line([(x, y1), (x, y1 + 4)], INK, 1)
            c.text(x, y1 + 9, lab, size=12, anchor="mt")
        # legend (top-left inside the header band)
        lx = x0
        for nm, col in s["colors"].items():
            c.line([(lx, 50), (lx + 22, 50)], NAMED[col], 3)
            c.text(lx + 28, 50, nm, size=13, anchor="lm")
            lx += 40 + c.text_size(nm, 13)[0] + 20
        for nm, vals in s["series"].items():
            rgb = NAMED[s["colors"][nm]]
            pts = [(x, y1 - (y1 - y0) * v / amax) for x, v in zip(px, vals)]
            c.line(pts, rgb, 2.6)
            if s["markers"]:
                for x, y in pts:
                    c.ellipse(x, y, 4.2, fill=rgb)
        c.line([(x0, y0), (x0, y1), (x1, y1)], INK, 1.5)
        manifest = {"plot": [x0, y0, x1, y1], "axis_max": amax, "grain": s["grain"], "x_pixels": px,
                    "xs": xs, "series_rgb": {nm: NAMED[col] for nm, col in s["colors"].items()},
                    "markers": s["markers"]}
        return c.finish(), manifest

    # ---- questions ---------------------------------------------------------------
    def question_candidates(self, s, f, r, d):
        out, m, xs = [], s["margin"], f["xs"]
        names = list(f["series"])
        for nm, vals in f["series"].items():
            srt = sorted(vals, reverse=True)
            if srt[0] - srt[1] >= m:
                out.append(("peak", {"series": nm}))
            for x in xs:
                out.append(("value_at", {"series": nm, "x": x}))
            for i, j in itertools.combinations(range(len(xs)), 2):
                if abs(vals[j] - vals[i]) >= m and j - i >= 2:
                    out.append(("change", {"series": nm, "x1": xs[i], "x2": xs[j]}))
            if all(abs(vals[i + 1] - vals[i]) >= m for i in range(len(vals) - 1)):
                out.append(("count_rises", {"series": nm}))
        for a, b in itertools.permutations(names, 2):
            for x in xs:
                out.append(("higher_at", {"a": a, "b": b, "x": x}))   # separation guaranteed at every x
        return out

    def answer(self, t, p, f):
        xs, S = f["xs"], f["series"]
        if t == "peak":
            v = S[p["series"]]
            return xs[int(np.argmax(v))]
        if t == "value_at":
            return S[p["series"]][xs.index(p["x"])]
        if t == "higher_at":
            i = xs.index(p["x"])
            return p["a"] if S[p["a"]][i] > S[p["b"]][i] else p["b"]
        if t == "change":
            v = S[p["series"]]
            return v[xs.index(p["x2"])] > v[xs.index(p["x1"])]
        if t == "count_rises":
            v = S[p["series"]]
            return sum(v[i + 1] > v[i] for i in range(len(v) - 1))
        raise KeyError(t)

    def question_meta(self, t, p, s):
        multi = len(s["series"]) > 1
        bind = [Skill.ATTRIBUTE.value] if multi else []
        return {
            "peak": {"answer_type": AnswerType.CHOICE, "skills": [Skill.TREND.value, Skill.COMPARISON.value] + bind,
                     "choices": s["xs"]},
            "value_at": {"answer_type": AnswerType.NUMBER, "skills": [Skill.NUMERIC_READING.value] + bind,
                         "tolerance": 0.05 * s["axis_max"]},
            "higher_at": {"answer_type": AnswerType.CHOICE, "skills": [Skill.COMPARISON.value, Skill.ATTRIBUTE.value],
                          "choices": [p.get("a"), p.get("b")]},
            "change": {"answer_type": AnswerType.BOOLEAN, "skills": [Skill.TREND.value] + bind},
            "count_rises": {"answer_type": AnswerType.INTEGER, "skills": [Skill.TREND.value, Skill.COUNTING.value] + bind},
        }[t]

    # ---- verification --------------------------------------------------------------
    @staticmethod
    def _run_centre(col_cov: np.ndarray) -> float | None:
        ys = np.flatnonzero(col_cov >= 0.25)
        if len(ys) == 0:
            return None
        # largest contiguous run (ignores stray pixels), coverage-weighted centre
        splits = np.split(ys, np.flatnonzero(np.diff(ys) > 1) + 1)
        run = max(splits, key=lambda s: col_cov[s].sum())
        lo, hi = max(0, run[0] - 1), min(len(col_cov), run[-1] + 2)
        w = col_cov[lo:hi]
        return float((np.arange(lo, hi) * w).sum() / w.sum())

    def measure(self, img, man):
        x0, y0, x1, y1 = man["plot"]
        sub = img[int(y0) - 6:int(y1) + 1, int(x0):int(x1) + 1]
        off = (6 + 4) if man["markers"] else 5
        out = {}
        for nm, rgb in man["series_rgb"].items():
            mask = coverage(sub, rgb)
            vals = []
            for i, cx in enumerate(man["x_pixels"]):
                ests = []
                for side in (-1, 1):
                    if (side < 0 and i == 0) or (side > 0 and i == len(man["x_pixels"]) - 1):
                        continue
                    pts = []
                    for o in (off, off + 4, off + 8, off + 12):
                        col = int(round(cx + side * o - x0))
                        if not 0 <= col < mask.shape[1]:
                            continue
                        yc = self._run_centre(mask[:, col])
                        if yc is not None:
                            pts.append((side * o, yc))
                        if len(pts) == 2:
                            break
                    if len(pts) == 2:
                        (xa, ya), (xb, yb) = pts
                        ests.append(ya - xa * (yb - ya) / (xb - xa))
                if not ests:
                    raise VerifyError(f"could not trace {nm} at {man['xs'][i]}")
                y = float(np.mean(ests)) + (y0 - 6)
                v = (y1 - y) / (y1 - y0) * man["axis_max"]
                vals.append(int(round(v / man["grain"]) * man["grain"]))
            out[nm] = vals
        return {"xs": man["xs"], "series": out}

    def compare_facts(self, truth, measured):
        probs = []
        for nm, vals in truth["series"].items():
            mv = measured["series"].get(nm, [])
            for x, a, b in zip(truth["xs"], vals, mv):
                if a != b:
                    probs.append(f"{nm}@{x}: scene={a} pixels={b}")
        return probs

    def mutate(self, s, r, hint=None):
        s2 = copy.deepcopy(s)
        hint = hint or {}
        names = list(s2["series"])
        if "a" in hint and "x" in hint:   # cross one series over the other at x
            i = s2["xs"].index(hint["x"])
            a, b = hint["a"], hint["b"]
            va, vb = s2["series"][a][i], s2["series"][b][i]
            off = int(round(s2["margin"] * r.uniform(1.2, 1.8) / s2["grain"])) * s2["grain"]
            nv = vb - off if va > vb else vb + off
            others = [s2["series"][o][i] for o in names if o != a]
            if 3 * s2["grain"] <= nv <= 48 * s2["grain"] and all(abs(nv - o) >= s2["margin"] for o in others):
                s2["series"][a][i] = nv
                return s2
            return None
        off = int(round(s2["margin"] * r.uniform(1.2, 1.8) / s2["grain"])) * s2["grain"]
        lo, hi = 3 * s2["grain"], 48 * s2["grain"]

        def ok(series_name, i, nv):
            others = [s2["series"][o][i] for o in names if o != series_name]
            return lo <= nv <= hi and all(abs(nv - o) >= s2["margin"] for o in others)

        if "x1" in hint:   # flip the direction of change between x1 and x2
            v = s2["series"][hint["series"]]
            i1, i2 = s2["xs"].index(hint["x1"]), s2["xs"].index(hint["x2"])
            nv = v[i1] - off if v[i2] > v[i1] else v[i1] + off
            if ok(hint["series"], i2, nv):
                v[i2] = nv
                return s2
            return None
        if hint.get("series") and set(hint) == {"series"} and r.random() < 0.5:   # move the peak elsewhere
            v = s2["series"][hint["series"]]
            i = r.choice([k for k in range(len(v)) if k != v.index(max(v))])
            nv = max(v) + off
            if ok(hint["series"], i, nv):
                v[i] = nv
                return s2
            return None
        nm = hint.get("series") or r.choice(names)
        xs_named = [hint[k] for k in ("x", "x1", "x2") if k in hint]
        i = s2["xs"].index(r.choice(xs_named)) if xs_named and r.random() < 0.8 else r.randrange(len(s2["xs"]))
        delta = int(round(s2["margin"] * r.uniform(1.5, 2.5) / s2["grain"])) * s2["grain"]
        for sign in ([1, -1] if r.random() < 0.5 else [-1, 1]):
            nv = s2["series"][nm][i] + sign * delta
            if 3 * s2["grain"] <= nv <= 48 * s2["grain"]:
                others = [s2["series"][o][i] for o in s2["series"] if o != nm]
                if all(abs(nv - o) >= s2["margin"] for o in others):
                    s2["series"][nm][i] = nv
                    return s2
        return None
