"""Object scenes: counting, attribute binding, spatial relations, extremes."""
from __future__ import annotations

import copy
import itertools
import math
from collections import Counter

import cv2
import numpy as np

from ..core.palette import NAMED, exclusive_coverage
from ..core.render import Canvas, regular_polygon, star
from ..core.spec import AnswerType, Rejected, Skill
from .base import Family, VerifyError

SHAPES = ["circle", "square", "triangle", "hexagon", "star"]
PLURAL = {"circle": "circles", "square": "squares", "triangle": "triangles", "hexagon": "hexagons", "star": "stars"}
N_OBJ = {1: (4, 6), 2: (6, 9), 3: (8, 12), 4: (11, 15), 5: (14, 19)}
N_COLORS = {1: 3, 2: 4, 3: 5, 4: 6, 5: 7}
N_SHAPES = {1: 3, 2: 4, 3: 5, 4: 5, 5: 5}
RADIUS = {1: (26, 40), 2: (22, 38), 3: (18, 36), 4: (16, 34), 5: (15, 32)}
AREA_K = {"circle": math.pi, "square": 2.0, "triangle": 3 * math.sqrt(3) / 4, "hexagon": 3 * math.sqrt(3) / 2,
          "star": 5 * 0.45 * math.sin(math.radians(36))}
W, H = 720, 520
PAD = 12


def area_of(o) -> float:
    return AREA_K[o["shape"]] * o["r"] ** 2


class ShapeSceneFamily(Family):
    name = "shapes"
    title = "Object scenes"
    description = "Coloured geometric objects: counting with attribute filters, left/right and above/below relations, extremes and most-common colour."
    skills = [Skill.COUNTING.value, Skill.ATTRIBUTE.value, Skill.SPATIAL.value, Skill.COMPARISON.value]
    knobs = {"objects": "4-6 -> 14-19", "colours": "3 -> 7", "shape types": "3 -> 5 (incl. hexagon vs circle)",
             "size": "large -> small, rotated"}
    phrasings = {
        "count_color": ["How many {color} shapes are there?", "Count the objects that are {color}."],
        "count_shape": ["How many {shapes} are in the image?", "Count all of the {shapes}, whatever their colour."],
        "count_both": ["How many {color} {shapes} are there?", "Count the {shapes} that are {color}."],
        "count_total": ["How many shapes are there in total?", "Count every object in the image."],
        "left_of": ["Is the {c1} {s1} to the left of the {c2} {s2}?",
                    "Looking at horizontal position, is the {c1} {s1} further left than the {c2} {s2}?"],
        "above": ["Is the {c1} {s1} above the {c2} {s2}?", "Is the {c1} {s1} positioned higher than the {c2} {s2}?"],
        "extreme_color": ["What colour is the {which} object?", "Give the colour of the {which} shape in the image."],
        "largest_shape": ["What type of shape is the largest object?", "Which kind of shape is the biggest one?"],
        "common_color": ["Which colour appears on the most objects?", "What is the most frequent object colour?"],
    }

    def sample_scene(self, r, d):
        colors = r.sample(list(NAMED), N_COLORS[d])
        kinds = SHAPES[:3] if d == 1 else r.sample(SHAPES, N_SHAPES[d])
        n = r.randint(*N_OBJ[d])
        objs = []
        for _ in range(n):
            for _try in range(200):
                rad = r.randint(*RADIUS[d])
                x, y = r.uniform(PAD + rad, W - PAD - rad), r.uniform(PAD + rad, H - PAD - rad)
                if all(math.hypot(x - o["x"], y - o["y"]) > rad + o["r"] + 10 for o in objs):
                    break
            else:
                raise Rejected("could not place objects without overlap")
            shape = r.choice(kinds)
            rot = r.uniform(0, 360) if (d >= 3 and shape != "circle") else 0.0
            objs.append({"shape": shape, "color": r.choice(colors), "x": round(x, 1), "y": round(y, 1),
                         "r": rad, "rot": round(rot, 1)})
        return {"objects": objs, "colors": colors, "kinds": kinds, "difficulty": d}

    def facts_from_scene(self, s):
        return {"objects": [{"shape": o["shape"], "color": o["color"], "x": o["x"], "y": o["y"],
                             "area": area_of(o)} for o in s["objects"]]}

    def render(self, s):
        c = Canvas(W, H)
        c.rect(1, 1, W - 2, H - 2, outline=(203, 213, 225), width=1, radius=6)
        for o in s["objects"]:
            rgb = NAMED[o["color"]]
            x, y, rad, rot = o["x"], o["y"], o["r"], o["rot"]
            if o["shape"] == "circle":
                c.ellipse(x, y, rad, fill=rgb)
            elif o["shape"] == "square":
                c.polygon(regular_polygon(x, y, rad, 4, rot + 45), fill=rgb)
            elif o["shape"] == "triangle":
                c.polygon(regular_polygon(x, y, rad, 3, rot), fill=rgb)
            elif o["shape"] == "hexagon":
                c.polygon(regular_polygon(x, y, rad, 6, rot), fill=rgb)
            else:
                c.polygon(star(x, y, rad, 5, 0.45, rot), fill=rgb)
        # the manifest exposes only the colour vocabulary used for rendering
        return c.finish(), {"palette": {k: NAMED[k] for k in NAMED}, "min_area": 120, "frame_inset": 6}

    # ---- questions -------------------------------------------------------------
    def question_candidates(self, s, f, r, d):
        objs, out = f["objects"], []
        cc = Counter(o["color"] for o in objs)
        sc = Counter(o["shape"] for o in objs)
        for col in s["colors"]:
            out.append(("count_color", {"color": col}))
            for k in s["kinds"]:
                out.append(("count_both", {"color": col, "shapes": PLURAL[k], "shape": k}))
        for k in s["kinds"]:
            out.append(("count_shape", {"shapes": PLURAL[k], "shape": k}))
        out.append(("count_total", {}))
        combo = Counter((o["color"], o["shape"]) for o in objs)
        uniq = [o for o in objs if combo[(o["color"], o["shape"])] == 1]
        for a, b in itertools.permutations(uniq, 2):
            p = {"c1": a["color"], "s1": a["shape"], "c2": b["color"], "s2": b["shape"]}
            if abs(a["x"] - b["x"]) >= 40:
                out.append(("left_of", p))
            if abs(a["y"] - b["y"]) >= 40:
                out.append(("above", p))
        for which, key, sign in (("leftmost", "x", 1), ("rightmost", "x", -1), ("topmost", "y", 1), ("bottommost", "y", -1)):
            srt = sorted(objs, key=lambda o: sign * o[key])
            if abs(srt[0][key] - srt[1][key]) >= 30:
                out.append(("extreme_color", {"which": which}))
        sa = sorted(objs, key=lambda o: -o["area"])
        if sa[0]["area"] >= 1.4 * sa[1]["area"]:
            out.append(("largest_shape", {}))
        top = cc.most_common()
        if len(top) == 1 or top[0][1] > top[1][1]:
            out.append(("common_color", {}))
        return out

    def answer(self, t, p, f):
        objs = f["objects"]
        if t == "count_color":
            return sum(o["color"] == p["color"] for o in objs)
        if t == "count_shape":
            return sum(o["shape"] == p["shape"] for o in objs)
        if t == "count_both":
            return sum(o["color"] == p["color"] and o["shape"] == p["shape"] for o in objs)
        if t == "count_total":
            return len(objs)
        if t in ("left_of", "above"):
            a = next(o for o in objs if o["color"] == p["c1"] and o["shape"] == p["s1"])
            b = next(o for o in objs if o["color"] == p["c2"] and o["shape"] == p["s2"])
            return a["x"] < b["x"] if t == "left_of" else a["y"] < b["y"]
        if t == "extreme_color":
            key, sign = {"leftmost": ("x", 1), "rightmost": ("x", -1), "topmost": ("y", 1), "bottommost": ("y", -1)}[p["which"]]
            return min(objs, key=lambda o: sign * o[key])["color"]
        if t == "largest_shape":
            return max(objs, key=lambda o: o["area"])["shape"]
        if t == "common_color":
            return Counter(o["color"] for o in objs).most_common(1)[0][0]
        raise KeyError(t)

    def question_meta(self, t, p, s):
        CNT, ATT, SPA, CMP = (Skill.COUNTING.value, Skill.ATTRIBUTE.value, Skill.SPATIAL.value,
                              Skill.COMPARISON.value)
        return {
            "count_color": {"answer_type": AnswerType.INTEGER, "skills": [CNT, ATT]},
            "count_shape": {"answer_type": AnswerType.INTEGER, "skills": [CNT, ATT]},
            "count_both": {"answer_type": AnswerType.INTEGER, "skills": [CNT, ATT]},
            "count_total": {"answer_type": AnswerType.INTEGER, "skills": [CNT]},
            "left_of": {"answer_type": AnswerType.BOOLEAN, "skills": [SPA, ATT]},
            "above": {"answer_type": AnswerType.BOOLEAN, "skills": [SPA, ATT]},
            "extreme_color": {"answer_type": AnswerType.CHOICE, "skills": [SPA, ATT], "choices": sorted(NAMED)},
            "largest_shape": {"answer_type": AnswerType.CHOICE, "skills": [CMP], "choices": SHAPES},
            "common_color": {"answer_type": AnswerType.CHOICE, "skills": [CNT, CMP, ATT], "choices": sorted(NAMED)},
        }[t]

    # ---- verification ---------------------------------------------------------------
    @staticmethod
    def classify(mask: np.ndarray) -> str:
        cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cnt = max(cnts, key=cv2.contourArea)
        area = cv2.contourArea(cnt)
        hull = cv2.contourArea(cv2.convexHull(cnt))
        if hull <= 0:
            raise VerifyError("degenerate component")
        solidity = area / hull
        (_, _), rad = cv2.minEnclosingCircle(cnt)
        fill = area / (math.pi * rad * rad)
        if solidity < 0.80:
            return "star"
        if fill > 0.90:
            return "circle"
        if fill > 0.74:
            return "hexagon"
        if fill > 0.52:
            return "square"
        return "triangle"

    def measure(self, img, man):
        objs = []
        covs = exclusive_coverage(img, man["palette"], max_residual=40)
        for name, cov in covs.items():
            k = man["frame_inset"]   # the decorative frame band never contains objects
            cov[:k], cov[-k:], cov[:, :k], cov[:, -k:] = 0, 0, 0, 0
            mask = (cov >= 0.5).astype(np.uint8)
            n, lab, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
            for i in range(1, n):
                if stats[i, cv2.CC_STAT_AREA] < man["min_area"]:
                    continue
                comp = lab == i
                w = cov * comp
                ys, xs = np.nonzero(comp)
                objs.append({"shape": self.classify(comp), "color": name,
                             "x": float((xs * w[ys, xs]).sum() / w[ys, xs].sum()),
                             "y": float((ys * w[ys, xs]).sum() / w[ys, xs].sum()),
                             "area": float(cov[ys, xs].sum())})
        return {"objects": objs}

    def compare_facts(self, truth, measured):
        probs, used = [], set()
        T, M = truth["objects"], measured["objects"]
        if len(T) != len(M):
            probs.append(f"object count: scene={len(T)} pixels={len(M)}")
        for o in T:
            best = min(((math.hypot(o["x"] - m["x"], o["y"] - m["y"]), j) for j, m in enumerate(M) if j not in used),
                       default=(1e9, None))
            if best[1] is None or best[0] > 3.0:
                probs.append(f"{o['color']} {o['shape']} at ({o['x']:.0f},{o['y']:.0f}) not found")
                continue
            used.add(best[1])
            m = M[best[1]]
            if m["color"] != o["color"] or m["shape"] != o["shape"]:
                probs.append(f"({o['x']:.0f},{o['y']:.0f}) scene={o['color']} {o['shape']} pixels={m['color']} {m['shape']}")
            elif abs(m["area"] - o["area"]) > 0.15 * o["area"]:
                probs.append(f"{o['color']} {o['shape']} area scene={o['area']:.0f} pixels={m['area']:.0f}")
        return probs

    def mutate(self, s, r, hint=None):
        s2 = copy.deepcopy(s)
        objs = s2["objects"]
        hint = hint or {}
        if "c1" in hint and r.random() < 0.7:   # move the first object across the second
            a = next((o for o in objs if o["color"] == hint["c1"] and o["shape"] == hint["s1"]), None)
            b = next((o for o in objs if o["color"] == hint["c2"] and o["shape"] == hint["s2"]), None)
            if a and b:
                key, lim = ("x", W) if r.random() < 0.5 else ("y", H)
                nv = 2 * b[key] - a[key]
                if PAD + a["r"] <= nv <= lim - PAD - a["r"]:
                    a[key] = round(nv, 1)
                    if all(math.hypot(a["x"] - o["x"], a["y"] - o["y"]) > a["r"] + o["r"] + 10 for o in objs if o is not a):
                        return s2
            return None
        op = r.choice(["recolor", "remove", "reshape"])
        i = r.randrange(len(objs))
        if "color" in hint or "shape" in hint:
            match = [k for k, o in enumerate(objs)
                     if o["color"] == hint.get("color", o["color"]) and o["shape"] == hint.get("shape", o["shape"])]
            other = [k for k in range(len(objs)) if k not in match]
            if match and (r.random() < 0.5 or not other):
                i = r.choice(match)
                op = r.choice(["remove", "recolor"] if "color" in hint else ["remove", "reshape"])
            elif other:
                o = objs[r.choice(other)]
                if "color" in hint:
                    o["color"] = hint["color"]
                if "shape" in hint:
                    o["shape"] = hint["shape"]
                return s2
        if op == "remove" and len(objs) > 3:
            objs.pop(i)
        elif op == "reshape":
            objs[i]["shape"] = r.choice([k for k in s2["kinds"] if k != objs[i]["shape"]] or s2["kinds"])
        else:
            objs[i]["color"] = r.choice([c for c in s2["colors"] if c != objs[i]["color"]])
        return s2
