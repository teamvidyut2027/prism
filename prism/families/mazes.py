"""Grid worlds: reachability, shortest paths, first move, counting walls."""
from __future__ import annotations

import copy
from collections import deque

import numpy as np

from ..core.palette import GRID, INK, NAMED, WALL, exclusive_coverage
from ..core.render import Canvas
from ..core.spec import AnswerType, Rejected, Skill
from .base import Family, VerifyError

SIZE = {1: 5, 2: 6, 3: 8, 4: 10, 5: 12}
DENSITY = {1: 0.22, 2: 0.25, 3: 0.28, 4: 0.30, 5: 0.32}
MOVES = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
W = H = 560
BOARD = 480


def bfs(grid: list[str], start, goal):
    n = len(grid)
    dist = {tuple(start): 0}
    q = deque([tuple(start)])
    while q:
        r, c = q.popleft()
        for dr, dc in MOVES.values():
            nr, nc = r + dr, c + dc
            if 0 <= nr < n and 0 <= nc < n and grid[nr][nc] == "." and (nr, nc) not in dist:
                dist[(nr, nc)] = dist[(r, c)] + 1
                q.append((nr, nc))
    return dist


def first_moves(grid, start, goal) -> list[str]:
    """All first moves that lie on *some* shortest path."""
    from_goal = bfs(grid, goal, start)
    if tuple(start) not in from_goal:
        return []
    d = from_goal[tuple(start)]
    out = []
    for name, (dr, dc) in MOVES.items():
        nb = (start[0] + dr, start[1] + dc)
        if from_goal.get(nb) == d - 1:
            out.append(name)
    return out


class MazeFamily(Family):
    name = "mazes"
    title = "Grid mazes"
    description = "Square grid worlds with walls, a start and a goal: reachability, shortest path length, first move, counting walls in a row."
    skills = [Skill.PATHFINDING.value, Skill.COUNTING.value, Skill.SPATIAL.value]
    knobs = {"grid": "5x5 -> 12x12", "wall density": "22% -> 32%"}
    phrasings = {
        "reachable": ["Moving only up, down, left or right through white cells, can the green circle reach the red square?",
                      "Is there a path of white cells (no diagonal moves) from the green circle to the red square?"],
        "shortest": ["What is the minimum number of moves needed to go from the green circle to the red square? Each move goes one cell up, down, left or right, and black cells are walls.",
                     "Count the steps on the shortest path from the green circle to the red square (4-directional moves, walls are black)."],
        "first_move": ["On a shortest path from the green circle to the red square, what is the first move: up, down, left or right?",
                       "Which direction should the green circle move first to reach the red square as quickly as possible?"],
        "row_walls": ["How many black wall cells are in row {row} (rows are numbered from 1 at the top)?",
                      "Count the black cells in row {row}, where row 1 is the top row."],
    }

    def sample_scene(self, r, d):
        n = SIZE[d]
        want_reach = r.random() < 0.5
        for _ in range(80):
            grid = [["#" if r.random() < DENSITY[d] else "." for _ in range(n)] for _ in range(n)]
            free = [(i, j) for i in range(n) for j in range(n) if grid[i][j] == "."]
            if len(free) < 4:
                continue
            s, g = r.sample(free, 2)
            if abs(s[0] - g[0]) + abs(s[1] - g[1]) < max(3, n // 2):
                continue
            rows = ["".join(row) for row in grid]
            if (tuple(g) in bfs(rows, s, g)) == want_reach:
                return {"grid": rows, "start": list(s), "goal": list(g), "difficulty": d}
        raise Rejected("could not sample a grid with the requested reachability")

    def facts_from_scene(self, s):
        return {"grid": s["grid"], "start": s["start"], "goal": s["goal"]}

    def render(self, s):
        n = len(s["grid"])
        cell = BOARD / n
        ox, oy = (W - BOARD) / 2 + 10, (H - BOARD) / 2 + 10
        c = Canvas(W, H)
        for i, row in enumerate(s["grid"]):
            c.text(ox - 10, oy + cell * (i + 0.5), str(i + 1), size=12, anchor="rm", fill=INK)
            for j, ch in enumerate(row):
                if i == 0:
                    c.text(ox + cell * (j + 0.5), oy - 8, str(j + 1), size=12, anchor="mb", fill=INK)
                if ch == "#":
                    c.rect(ox + cell * j, oy + cell * i, ox + cell * (j + 1), oy + cell * i + cell, fill=WALL)
        for k in range(n + 1):
            c.line([(ox + cell * k, oy), (ox + cell * k, oy + BOARD)], (203, 213, 225), 1)
            c.line([(ox, oy + cell * k), (ox + BOARD, oy + cell * k)], (203, 213, 225), 1)
        si, sj = s["start"]
        gi, gj = s["goal"]
        c.ellipse(ox + cell * (sj + 0.5), oy + cell * (si + 0.5), cell * 0.32, fill=NAMED["green"])
        q = cell * 0.30
        c.rect(ox + cell * (gj + 0.5) - q, oy + cell * (gi + 0.5) - q, ox + cell * (gj + 0.5) + q,
               oy + cell * (gi + 0.5) + q, fill=NAMED["red"])
        c.rect(ox, oy, ox + BOARD, oy + BOARD, outline=INK, width=2)
        return c.finish(), {"origin": [ox, oy], "cell": cell, "n": n, "wall_rgb": WALL,
                            "start_rgb": NAMED["green"], "goal_rgb": NAMED["red"]}

    def question_candidates(self, s, f, r, d):
        dist = bfs(f["grid"], f["start"], f["goal"])
        reach = tuple(f["goal"]) in dist
        out = [("reachable", {})]
        if reach:
            out.append(("shortest", {}))
            if len(first_moves(f["grid"], f["start"], f["goal"])) == 1:
                out.append(("first_move", {}))
        for i in range(len(f["grid"])):
            out.append(("row_walls", {"row": i + 1}))
        return out

    def answer(self, t, p, f):
        if t == "reachable":
            return tuple(f["goal"]) in bfs(f["grid"], f["start"], f["goal"])
        if t == "shortest":
            return bfs(f["grid"], f["start"], f["goal"])[tuple(f["goal"])]
        if t == "first_move":
            return first_moves(f["grid"], f["start"], f["goal"])[0]
        if t == "row_walls":
            return f["grid"][p["row"] - 1].count("#")
        raise KeyError(t)

    def question_meta(self, t, p, s):
        P, C, S = Skill.PATHFINDING.value, Skill.COUNTING.value, Skill.SPATIAL.value
        return {
            "reachable": {"answer_type": AnswerType.BOOLEAN, "skills": [P]},
            "shortest": {"answer_type": AnswerType.INTEGER, "skills": [P, C]},
            "first_move": {"answer_type": AnswerType.CHOICE, "skills": [P, S], "choices": list(MOVES)},
            "row_walls": {"answer_type": AnswerType.INTEGER, "skills": [C, S]},
        }[t]

    def measure(self, img, man):
        n, cell = man["n"], man["cell"]
        ox, oy = man["origin"]
        cov = exclusive_coverage(img, {"wall": man["wall_rgb"], "start": man["start_rgb"], "goal": man["goal_rgb"]},
                                 max_residual=40)
        k = max(2, int(cell * 0.15))
        grid = []
        for i in range(n):
            row = ""
            for j in range(n):
                cy, cx = int(oy + cell * (i + 0.5)), int(ox + cell * (j + 0.5))
                row += "#" if cov["wall"][cy - k:cy + k + 1, cx - k:cx + k + 1].mean() > 0.5 else "."
            grid.append(row)

        def locate(name):
            ys, xs = np.nonzero(cov[name] >= 0.5)
            if len(ys) < 10:
                raise VerifyError(f"{name} marker not found")
            return [int((ys.mean() - oy) // cell), int((xs.mean() - ox) // cell)]

        return {"grid": grid, "start": locate("start"), "goal": locate("goal")}

    def compare_facts(self, truth, measured):
        probs = []
        for i, (a, b) in enumerate(zip(truth["grid"], measured["grid"])):
            if a != b:
                probs.append(f"row {i + 1}: scene={a} pixels={b}")
        for k in ("start", "goal"):
            if truth[k] != measured[k]:
                probs.append(f"{k}: scene={truth[k]} pixels={measured[k]}")
        return probs

    def mutate(self, s, r, hint=None):
        s2 = copy.deepcopy(s)
        n = len(s2["grid"])
        dist = bfs(s2["grid"], s2["start"], s2["goal"])
        # prefer toggling a cell next to the current shortest-path frontier: it is the edit most likely to matter
        cand = [(i, j) for i in range(n) for j in range(n) if [i, j] not in (s2["start"], s2["goal"])]
        on_path = [c for c in cand if c in dist]
        i, j = r.choice(on_path if (on_path and r.random() < 0.7) else cand)
        row = list(s2["grid"][i])
        row[j] = "." if row[j] == "#" else "#"
        s2["grid"][i] = "".join(row)
        return s2
