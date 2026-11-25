"""Analog clocks: reading the time, elapsed-time arithmetic, hand positions."""
from __future__ import annotations

import copy
import math

import numpy as np
from scipy.ndimage import map_coordinates

from ..core.palette import INK, NAMED, coverage
from ..core.render import Canvas
from ..core.spec import AnswerType, Rejected, Skill
from .base import Family, VerifyError

W = H = 520
CX, CY, R = 260, 260, 220
RIMS = [(30, 58, 95), (15, 118, 110), (88, 28, 135), (120, 53, 15), (55, 65, 81)]
FACES = [(255, 255, 255), (250, 250, 245), (248, 250, 252)]


def _ang_dist(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def fmt_time(h: int, m: int) -> str:
    return f"{h}:{m:02d}"


class ClockFamily(Family):
    name = "clocks"
    title = "Analog clocks"
    description = "Analog clock faces from fully numbered to bare dials, with distractor second hands: read the time, do time arithmetic."
    skills = [Skill.TEMPORAL.value, Skill.ARITHMETIC.value, Skill.SPATIAL.value]
    knobs = {"numerals": "all 12 -> 4 -> none", "minute ticks": "on -> off", "minute grain": "5 min -> 1 min",
             "distractor": "red second hand at level 5"}
    phrasings = {
        "read_time": ["What time does the clock show?", "Read the analog clock. What time is it?"],
        "minutes_to_hour": ["How many minutes are left until the next full hour?",
                            "According to the clock, how many minutes until the hour hand reaches the next hour?"],
        "time_after": ["What time will the clock show {k} minutes from now?",
                       "If {k} minutes pass, what time will this clock read?"],
        "minute_number": ["Which numeral (1-12) is the minute hand pointing at?",
                          "The minute hand points at which hour mark (1-12)?"],
    }

    def sample_scene(self, r, d):
        h = r.randint(1, 12)
        m = r.randrange(0, 60, 5) if d <= 2 else r.randrange(0, 60)
        a_min = m * 6
        a_hr = (h % 12) * 30 + m * 0.5
        if _ang_dist(a_min, a_hr) < 20:
            raise Rejected("hands overlap: hour and minute hand closer than 20 degrees")
        return {"h": h, "m": m,
                "numerals": {1: "all", 2: "all", 3: "quarters", 4: "none", 5: "none"}[d],
                "minute_ticks": d <= 4,
                "second_hand": (r.randrange(60) if d >= 5 else None),
                "rim": r.randrange(len(RIMS)), "face": r.randrange(len(FACES)), "difficulty": d}

    def facts_from_scene(self, s):
        return {"h": s["h"], "m": s["m"]}

    def render(self, s):
        c = Canvas(W, H)
        rim, face = RIMS[s["rim"]], FACES[s["face"]]
        c.ellipse(CX, CY, R + 14, fill=rim)
        c.ellipse(CX, CY, R, fill=face)
        for i in range(60):
            if i % 5 and not s["minute_ticks"]:
                continue
            a = math.radians(i * 6)
            r0 = R * (0.88 if i % 5 == 0 else 0.93)
            w = 4 if i % 5 == 0 else 1.6
            c.line([(CX + r0 * math.sin(a), CY - r0 * math.cos(a)),
                    (CX + R * 0.98 * math.sin(a), CY - R * 0.98 * math.cos(a))], INK, w)
        show = {"all": range(1, 13), "quarters": (3, 6, 9, 12), "none": ()}[s["numerals"]]
        for n in show:
            a = math.radians(n * 30)
            c.text(CX + R * 0.76 * math.sin(a), CY - R * 0.76 * math.cos(a), str(n), size=30, anchor="mm", bold=True)
        a_hr = math.radians((s["h"] % 12) * 30 + s["m"] * 0.5)
        a_min = math.radians(s["m"] * 6)
        c.line([(CX - R * 0.08 * math.sin(a_hr), CY + R * 0.08 * math.cos(a_hr)),
                (CX + R * 0.50 * math.sin(a_hr), CY - R * 0.50 * math.cos(a_hr))], INK, 10)
        c.line([(CX - R * 0.10 * math.sin(a_min), CY + R * 0.10 * math.cos(a_min)),
                (CX + R * 0.80 * math.sin(a_min), CY - R * 0.80 * math.cos(a_min))], INK, 5)
        if s["second_hand"] is not None:
            a_s = math.radians(s["second_hand"] * 6)
            c.line([(CX - R * 0.15 * math.sin(a_s), CY + R * 0.15 * math.cos(a_s)),
                    (CX + R * 0.86 * math.sin(a_s), CY - R * 0.86 * math.cos(a_s))], NAMED["red"], 2)
        c.ellipse(CX, CY, 9, fill=INK)
        return c.finish(), {"centre": [CX, CY], "radius": R, "hand_rgb": INK, "face_rgb": face}

    # ---- questions --------------------------------------------------------------
    def question_candidates(self, s, f, r, d):
        out = [("read_time", {})]
        if f["m"] != 0:
            out.append(("minutes_to_hour", {}))
        if d >= 2:
            for k in (15, 25, 40, 45, 50, 75, 90):
                out.append(("time_after", {"k": k}))
        if f["m"] % 5 == 0:
            out.append(("minute_number", {}))
        return out

    def answer(self, t, p, f):
        h, m = f["h"], f["m"]
        if t == "read_time":
            return fmt_time(h, m)
        if t == "minutes_to_hour":
            return 60 - m
        if t == "time_after":
            tot = (h % 12) * 60 + m + p["k"]
            hh, mm = divmod(tot % 720, 60)
            return fmt_time(hh or 12, mm)
        if t == "minute_number":
            return (m // 5) or 12
        raise KeyError(t)

    def question_meta(self, t, p, s):
        T, A, S = Skill.TEMPORAL.value, Skill.ARITHMETIC.value, Skill.SPATIAL.value
        return {
            "read_time": {"answer_type": AnswerType.TIME, "skills": [T]},
            "minutes_to_hour": {"answer_type": AnswerType.INTEGER, "skills": [T, A]},
            "time_after": {"answer_type": AnswerType.TIME, "skills": [T, A]},
            "minute_number": {"answer_type": AnswerType.INTEGER, "skills": [T, S]},
        }[t]

    # ---- verification -------------------------------------------------------------
    @staticmethod
    def _profile(cov, cx, cy, R, r_lo, r_hi, step=0.5):
        angs = np.arange(0, 360, step)
        radii = np.linspace(r_lo * R, r_hi * R, 24)
        A, RR = np.meshgrid(np.radians(angs), radii, indexing="ij")
        xs = cx + RR * np.sin(A)
        ys = cy - RR * np.cos(A)
        vals = map_coordinates(cov, [ys.ravel(), xs.ravel()], order=1).reshape(A.shape)
        return angs, vals.mean(axis=1)

    def measure(self, img, man):
        cx, cy = man["centre"]
        R = man["radius"]
        cov = coverage(img, man["hand_rgb"], bg=man["face_rgb"], max_residual=45)
        angs, prof_m = self._profile(cov, cx, cy, R, 0.56, 0.68)
        a_min = float(angs[int(np.argmax(prof_m))])
        if prof_m.max() < 0.5:
            raise VerifyError("minute hand not found")
        angs, prof_h = self._profile(cov, cx, cy, R, 0.20, 0.40)
        prof_h = prof_h.copy()
        prof_h[np.array([_ang_dist(a, a_min) < 12 for a in angs])] = 0
        a_hr = float(angs[int(np.argmax(prof_h))])
        if prof_h.max() < 0.5:
            raise VerifyError("hour hand not found")
        m = int(round(a_min / 6)) % 60
        h = int(round((a_hr - 0.5 * m) / 30)) % 12
        return {"h": h or 12, "m": m}

    def compare_facts(self, truth, measured):
        return [] if truth == measured else [f"scene={fmt_time(**truth)} pixels={fmt_time(**measured)}"]

    def mutate(self, s, r, hint=None):
        s2 = copy.deepcopy(s)
        delta = r.choice([-1, 1]) * r.randint(7, 50)
        if s2["difficulty"] <= 2:
            delta = int(round(delta / 5)) * 5 or 5
        tot = ((s2["h"] % 12) * 60 + s2["m"] + delta) % 720
        hh, mm = divmod(tot, 60)
        s2["h"], s2["m"] = hh or 12, mm
        if _ang_dist(mm * 6, (hh % 12) * 30 + mm * 0.5) < 20:
            return None
        return s2
