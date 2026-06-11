"""
calibrate.py (v2.x) — the green-garden calibration range.

Records how the operator actually moves, across four task types laid over a
GitHub-contribution-graph field of squares:

  ACQUIRE  — click the small gold square (smaller targets + visual clutter)
  TRACK    — follow a slowly-moving dot; it's quick until you lock on, then it
             settles and the clock starts (smooth pursuit)
  HOLD     — hold dead still on a single red pixel inside a white dot (tremor test)
  EVASIVE  — "Andvari": the roach runs the dark grid (green = walls), ducks
             under silver hide-cells (they pulse red), thump it there; several hits

Everything stays on your machine (see silphe.analysis.recordings_dir). Each
record is stamped with device + OS. ESC quits; progress is saved as you go.

    silphe-play            # mouse (default), after `pip install silphe`
    silphe-play trackpad   # tag the session as trackpad
"""

from __future__ import annotations

import json
import math
import os
import platform
import random
import sys
import time
import tkinter as tk

from silphe.analysis import recordings_dir

REC_DIR = recordings_dir()
VERSION = "Andvari"
HOLD_SECS = 1.2
TRACK_SECS = 4.0
GREENS = ["#0e4429", "#006d32", "#26a641", "#39d353"]


class Garden:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"The Ministry of Silly Mice — {VERSION}")
        root.configure(bg="#0d1117")
        self.W, self.H = 1200, 760
        self.canvas = tk.Canvas(root, width=self.W, height=self.H,
                                bg="#0d1117", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.CELL, self.GAP, self.COLS, self.ROWS = 30, 6, 30, 15
        gw = self.COLS * (self.CELL + self.GAP) - self.GAP
        gh = self.ROWS * (self.CELL + self.GAP) - self.GAP
        self.ox, self.oy = (self.W - gw) // 2, (self.H - gh) // 2 + 12

        self.device = (sys.argv[1] if len(sys.argv) > 1 else "mouse").lower()
        self.os = platform.system()
        os.makedirs(REC_DIR, exist_ok=True)
        self.path = os.path.join(REC_DIR, f"session-{int(time.time())}-{self.device}.jsonl")
        self.fh = open(self.path, "a", encoding="utf-8")

        self.cells, self.base = {}, {}
        self._draw_field()

        self.plan = self._make_plan()
        self.i = 0
        self.state = "idle"
        self.samples = []
        self.t0 = 0.0
        self.first_move = None
        self.last = (self.W // 2, self.H // 2)
        self.target = None
        self.inside_since = None
        self.hides = set()
        self.walls = set()
        self.tool = "swatter"

        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Button-1>", self._click)
        root.bind("<Escape>", lambda e: self._finish())
        root.bind("t", self._switch_tool)
        root.bind("T", self._switch_tool)
        self._next()

    # ---- geometry / field ----------------------------------------------

    def _cell_xy(self, r, c):
        return self.ox + c * (self.CELL + self.GAP), self.oy + r * (self.CELL + self.GAP)

    def _center(self, r, c):
        x0, y0 = self._cell_xy(r, c)
        return x0 + self.CELL / 2, y0 + self.CELL / 2

    def _draw_field(self):
        for r in range(self.ROWS):
            for c in range(self.COLS):
                x0, y0 = self._cell_xy(r, c)
                col = random.choice(GREENS) if random.random() < 0.16 else "#161b22"
                self.cells[(r, c)] = self.canvas.create_rectangle(
                    x0, y0, x0 + self.CELL, y0 + self.CELL, fill=col, outline="#0d1117")
                self.base[(r, c)] = col

    def _pick(self):
        return random.randint(0, self.ROWS - 1), random.randint(0, self.COLS - 1)

    # ---- flow -----------------------------------------------------------

    def _make_plan(self):
        kinds = ["acquire"] * 4 + ["track"] * 3 + ["hold"] * 3 + ["evasive"] * 2
        random.shuffle(kinds)
        return kinds

    def _hud(self, msg, color="#8b949e", sub=None):
        self.canvas.delete("hud")
        self.canvas.create_text(self.W // 2, 22, text=msg, fill=color, tag="hud",
                                font=("Consolas", 15, "bold"))
        self.canvas.create_text(self.W // 2, self.H - 12, fill="#6e7681", tag="hud",
                                font=("Consolas", 10),
                                text=f"round {min(self.i + 1, len(self.plan))}/{len(self.plan)}"
                                     f"   ·   ESC to stop (saved as you go)")
        if sub:
            self.canvas.create_text(self.W // 2, 46, fill="#6e7681", tag="hud",
                                    font=("Consolas", 11), text=sub)

    def _toast(self, rc, text, good):
        cx, cy = self._center(*rc)
        self._toast_xy(cx, cy, text, good)

    def _toast_xy(self, x, y, text, good):
        self.canvas.delete("toast")                       # only the latest message — no more clogging
        tid = self.canvas.create_text(x, y - self.CELL, text=text, tags=("toast",),
                                      fill="#39d353" if good else "#f85149",
                                      font=("Consolas", 12, "bold"))
        self.root.after(700, lambda: self.canvas.delete(tid))

    def _hit_mark(self, x, y, n):                          # persistent numbered hit — stays for the round
        self.canvas.create_oval(x - 8, y - 8, x + 8, y + 8, outline="#f0f6fc", width=1, tag="hitmark")
        self.canvas.create_text(x, y, text=str(n), fill="#f0f6fc",
                                font=("Consolas", 9, "bold"), tag="hitmark")

    def _restore(self):
        if self.target and "cell" in self.target:
            rc = self.target["cell"]
            self.canvas.itemconfig(self.cells[rc], fill=self.base[rc])
        for rc in self.hides:
            self.canvas.itemconfig(self.cells[rc], fill=self.base[rc])
        self.hides = set()
        self.canvas.delete("mark", "ring", "dot", "roach", "tool", "toast", "hitmark")

    def _next(self):
        self._restore()
        self.canvas.delete("hud")
        if self.i >= len(self.plan):
            return self._finish()
        self.samples, self.t0 = [], time.perf_counter()
        self.first_move, self.inside_since = None, None
        getattr(self, "_begin_" + self.plan[self.i])()

    # ---- recording ------------------------------------------------------

    def _motion(self, e):
        self.last = (e.x, e.y)
        if self.state in ("acquire", "track", "hold", "evasive"):
            t = time.perf_counter() - self.t0
            self.samples.append((round(t, 4), e.x, e.y))
            if self.first_move is None:
                self.first_move = t

    def _save(self, obj):
        obj["device"], obj["os"] = self.device, self.os
        self.fh.write(json.dumps(obj) + "\n")
        self.fh.flush()

    # ---- ACQUIRE --------------------------------------------------------

    def _begin_acquire(self):
        rc = self._pick()
        cx, cy = self._center(*rc)
        self.target = {"cell": rc, "x": cx, "y": cy, "r": self.CELL / 2}
        self.canvas.itemconfig(self.cells[rc], fill="#e3b341")
        self._hud("Click the GOLD square.", "#e3b341",
                  sub="small target, in the weeds — find it and hit it")
        self.state = "acquire"

    # ---- TRACK (follow the slowly-moving dot) --------------------------

    def _begin_track(self):
        sq = 90
        x0 = random.randint(self.ox + 20, self.W - 20 - sq)
        y0 = random.randint(72, self.H - 64 - sq)
        cx, cy = x0 + sq / 2, y0 + sq / 2
        self.target = {
            "x0": x0, "y0": y0, "sq": sq, "cx": cx, "cy": cy,
            "rd": sq / 8, "tol": sq / 8 + 5,                       # dot = 1/4 the square's width
            "w1": 2 * math.pi * 0.18, "w2": 2 * math.pi * 0.13,   # slow, incommensurate -> smooth wander
            "ph1": random.uniform(0, 6.28), "ph2": random.uniform(0, 6.28),
            "locked": False, "lock_t": 0.0, "last_tick": time.perf_counter(),
            "dot": [], "on": 0, "tot": 0,
        }
        self.canvas.create_rectangle(x0, y0, x0 + sq, y0 + sq,
                                     fill="#241a3d", outline="#a371f7", width=2, tag="mark")
        self.canvas.create_oval(0, 0, 0, 0, fill="#d2a8ff", outline="", tag="dot")
        self._hud("Catch the moving dot to start.", "#a371f7",
                  sub="it's quick until you lock on — then it settles and the clock runs")
        self.state = "track"
        self._track_tick()

    def _track_tick(self):
        if self.state != "track":
            return
        tg = self.target
        now = time.perf_counter()
        dt = now - tg["last_tick"]
        tg["last_tick"] = now
        sf = 1.0 if tg["locked"] else 2.4                 # fast until you lock on
        tg["ph1"] += tg["w1"] * dt * sf
        tg["ph2"] += tg["w2"] * dt * sf
        amp = tg["sq"] / 2 - tg["rd"] - 3
        dx = tg["cx"] + amp * math.sin(tg["ph1"])
        dy = tg["cy"] + amp * math.sin(tg["ph2"])
        rd = tg["rd"]
        self.canvas.coords("dot", dx - rd, dy - rd, dx + rd, dy + rd)
        tg["dot"].append((round(now - self.t0, 4), round(dx, 1), round(dy, 1)))
        x, y = self.last
        on = math.hypot(x - dx, y - dy) <= tg["tol"]
        self.canvas.itemconfig("dot", fill="#39d353" if on else "#d2a8ff")

        if not tg["locked"]:
            if on:
                tg["locked"], tg["lock_t"] = True, now
                self._hud("Locked — now STAY on it.", "#39d353", sub="follow it as it drifts")
            return self.root.after(16, self._track_tick)

        tg["tot"] += 1
        tg["on"] += 1 if on else 0
        el = now - tg["lock_t"]
        self.canvas.delete("ring")
        self.canvas.create_rectangle(tg["x0"], tg["y0"] + tg["sq"] + 6,
                                     tg["x0"] + tg["sq"] * min(1.0, el / TRACK_SECS),
                                     tg["y0"] + tg["sq"] + 10, fill="#a371f7", outline="", tag="ring")
        if el >= TRACK_SECS:
            pct = round(100 * tg["on"] / max(1, tg["tot"]))
            self._save({"kind": "track", "square": {"x": tg["x0"], "y": tg["y0"], "size": tg["sq"]},
                        "reaction_s": round(self.first_move or 0, 4),
                        "locked_at": round(tg["lock_t"] - self.t0, 4),
                        "on_target_pct": pct, "dot": tg["dot"], "samples": self.samples})
            self.canvas.delete("dot")
            self._hud(f"Tracked - {pct}% glued to it.", "#39d353")
            self.state = "idle"
            self.i += 1
            return self.root.after(800, self._next)
        self.root.after(16, self._track_tick)

    # ---- HOLD (single red pixel — the tremor test) ---------------------

    def _begin_hold(self):
        rc = self._pick()
        cx, cy = self._center(*rc)
        self.target = {"cell": rc, "x": cx, "y": cy, "r": 5.0}
        self.canvas.itemconfig(self.cells[rc], fill="#1f6feb")
        self.canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5,
                                outline="#f0f6fc", width=1, tag="mark")
        self.canvas.create_rectangle(cx, cy, cx + 1, cy + 1,
                                     fill="#ff3b30", outline="", tag="mark")
        self._hud("Hold STEADY on the single red pixel.", "#ff7b72",
                  sub="one pixel, inside the white dot — your hand vs the mouse's inertia")
        self.state = "hold"
        self._dwell_tick("hold", HOLD_SECS, "STEADY")

    def _dwell_tick(self, kind, secs, ok_text):
        if self.state != kind:
            return
        cx, cy, tol = self.target["x"], self.target["y"], self.target["r"]
        x, y = self.last
        now = time.perf_counter()
        self.canvas.delete("ring")
        if math.hypot(x - cx, y - cy) <= tol:
            if self.inside_since is None:
                self.inside_since = now
            frac = min(1.0, (now - self.inside_since) / secs)
            rr = tol + 9
            self.canvas.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=90,
                                   extent=-360 * frac, style="arc",
                                   outline="#39d353", width=3, tag="ring")
            if now - self.inside_since >= secs:
                self._save({"kind": kind, "target": {"x": cx, "y": cy, "r": tol},
                            "reaction_s": round(self.first_move or 0, 4),
                            "samples": self.samples})
                self._toast(self.target["cell"], ok_text, True)
                self.state = "idle"
                self.i += 1
                return self.root.after(700, self._next)
        else:
            self.inside_since = None
        self.root.after(20, lambda: self._dwell_tick(kind, secs, ok_text))

    # ---- EVASIVE: "Andvari" — the Pac-Man maze roach ------------------

    def _begin_evasive(self):
        self.walls = {rc for rc, col in self.base.items() if col in GREENS}
        paths = [rc for rc in self.cells if rc not in self.walls]
        self.hides = set(random.sample(paths, min(5, len(paths))))
        for rc in self.hides:
            self.canvas.itemconfig(self.cells[rc], fill="#b1bac4")   # silver hide-holes
        start = random.choice([rc for rc in paths if rc not in self.hides] or paths)
        cx, cy = self._center(*start)
        self.tool = "swatter"
        self.target = {
            "cell": start, "to": start, "prog": 1.0, "px": cx, "py": cy,
            "health": random.randint(4, 6), "hp0": 0, "speed": 10.0,
            "hidden": False, "hide_cell": None, "hide_until": 0.0,
            "burst_until": 0.0, "pause_until": 0.0, "want_hide": False,
            "last": time.perf_counter(), "path": [], "switches": [],
        }
        self.target["hp0"] = self.target["health"]
        self._hud("ANDVARI — hunt the roach.", "#d29922",
                  sub="SWATTER for the runner; press T for the PICK to stab it in its silver hole")
        self.state = "evasive"
        self._show_tool()
        self._roach_tick()

    def _switch_tool(self, e=None):
        if self.state != "evasive":
            return
        self.tool = "pick" if self.tool == "swatter" else "swatter"
        self.target["switches"].append((round(time.perf_counter() - self.t0, 4), self.tool))
        self._show_tool()

    def _show_tool(self):
        self.canvas.delete("tool")
        if self.state != "evasive":
            return
        name = "SWATTER" if self.tool == "swatter" else "PICK (sharp)"
        self.canvas.create_text(self.W - 120, 22, text=f"[T] tool: {name}", fill="#e3b341",
                                tag="tool", font=("Consolas", 12, "bold"))

    def _neighbors(self, rc):
        r, c = rc
        out = []
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (r + dr, c + dc)
            if 0 <= nb[0] < self.ROWS and 0 <= nb[1] < self.COLS and nb not in self.walls:
                out.append(nb)
        return out

    def _wander(self, rc, mx, my, fleeing):
        nb = self._neighbors(rc)
        if not nb:
            return rc
        if fleeing:
            return max(nb, key=lambda cell: math.hypot(self._center(*cell)[0] - mx,
                                                       self._center(*cell)[1] - my))
        return random.choice(nb)

    def _toward(self, rc, goal):
        nb = self._neighbors(rc)
        if not nb or goal is None:
            return None
        return min(nb, key=lambda cell: abs(cell[0] - goal[0]) + abs(cell[1] - goal[1]))

    def _nearest_hide(self, rc):
        if not self.hides:
            return None
        return min(self.hides, key=lambda h: abs(h[0] - rc[0]) + abs(h[1] - rc[1]))

    def _draw_roach(self, ax, ay, bx, by):
        self.canvas.delete("roach")
        tg = self.target
        x, y = tg["px"], tg["py"]
        ang = math.atan2(by - ay, bx - ax) if (bx != ax or by != ay) else 0.0
        body = "#a9712f" if tg["health"] < tg["hp0"] else "#6e4b1f"
        self.canvas.create_oval(x - 8, y - 5, x + 8, y + 5, fill=body, outline="#3d2b12", tag="roach")
        dx, dy = math.cos(ang), math.sin(ang)
        px, py = -dy, dx
        self.canvas.create_line(x + dx * 7, y + dy * 7, x + dx * 15 - px * 4, y + dy * 15 - py * 4,
                                fill="#3d2b12", width=2, tag="roach")
        self.canvas.create_line(x + dx * 7, y + dy * 7, x + dx * 15 + px * 4, y + dy * 15 + py * 4,
                                fill="#3d2b12", width=2, tag="roach")
        self.canvas.create_text(x, y - 14, text="•" * tg["health"], fill="#f85149",
                                font=("Consolas", 9, "bold"), tag="roach")

    def _roach_tick(self):
        if self.state != "evasive":
            return
        tg = self.target
        now = time.perf_counter()
        dt = now - tg["last"]
        tg["last"] = now
        mx, my = self.last

        if tg["hidden"]:                                  # lurks under the silver cell — pulses, won't leave on its own
            self.canvas.itemconfig(self.cells[tg["hide_cell"]],
                                   fill="#f85149" if (now * 4) % 2 < 1 else "#b1bac4")
            return self.root.after(16, self._roach_tick)

        fleeing = now < tg["burst_until"]
        speed = tg["speed"] * (2.0 if fleeing else 1.0)
        if now < tg["pause_until"] and not fleeing:
            speed = 0.0
        tg["prog"] += speed * dt
        if tg["prog"] >= 1.0:                              # arrived in the next cell — decide
            tg["prog"], tg["cell"] = 0.0, tg["to"]
            ccx, ccy = self._center(*tg["cell"])
            if math.hypot(mx - ccx, my - ccy) < 95 and now > tg["burst_until"]:
                tg["burst_until"] = now + 0.5
                tg["want_hide"] = random.random() < 0.3
            elif random.random() < 0.12 and now > tg["burst_until"]:
                tg["burst_until"] = now + random.uniform(0.2, 0.5)   # chaotic random darts
            if tg["cell"] in self.hides and (tg["want_hide"] or random.random() < 0.4):
                tg["hidden"], tg["hide_cell"] = True, tg["cell"]
                tg["picked_this_hide"], tg["want_hide"] = False, False
                self.canvas.delete("roach")
                return self.root.after(16, self._roach_tick)
            if tg["want_hide"]:
                tg["to"] = (self._toward(tg["cell"], self._nearest_hide(tg["cell"]))
                            or self._wander(tg["cell"], mx, my, True))
            else:
                if random.random() < 0.02:
                    tg["pause_until"] = now + random.uniform(0.1, 0.3)
                tg["to"] = self._wander(tg["cell"], mx, my, fleeing)
        ax, ay = self._center(*tg["cell"])
        bx, by = self._center(*tg["to"])
        tg["px"] = ax + (bx - ax) * tg["prog"]
        tg["py"] = ay + (by - ay) * tg["prog"]
        tg["path"].append((round(now - self.t0, 4), round(tg["px"], 1), round(tg["py"], 1)))
        self._draw_roach(ax, ay, bx, by)
        self.root.after(16, self._roach_tick)

    # ---- click router ---------------------------------------------------

    def _click(self, e):
        if self.state == "acquire":
            tx, ty, r = self.target["x"], self.target["y"], self.target["r"]
            err = math.hypot(e.x - tx, e.y - ty)
            start = self.samples[0] if self.samples else (0, e.x, e.y)
            self._save({"kind": "acquire", "target": {"x": tx, "y": ty, "r": r},
                        "home": {"x": start[1], "y": start[2]},
                        "click": {"x": e.x, "y": e.y, "err": round(err, 1)},
                        "reaction_s": round(self.first_move or 0, 4), "samples": self.samples})
            self._toast(self.target["cell"], "GOT IT" if err <= r * 1.4 else "missed", err <= r * 1.4)
            self.state = "idle"
            self.i += 1
            self.root.after(700, self._next)
        elif self.state == "evasive":
            tg = self.target
            if tg["hidden"]:                                  # in the hole -> PICK only
                if self.tool != "pick":
                    return self._toast_xy(e.x, e.y, "need the PICK [T]", False)
                hc = tg["hide_cell"]
                x0, y0 = self._cell_xy(*hc)
                if not (x0 <= e.x <= x0 + self.CELL and y0 <= e.y <= y0 + self.CELL):
                    return
                # a stab into the big hole ALWAYS scares it out and burns the hole for good,
                # but only lands a wound 1-in-4
                self.canvas.itemconfig(self.cells[hc], fill=self.base[hc])
                self.hides.discard(hc)                        # it won't hide here again this round
                tg["hidden"], tg["hide_cell"] = False, None
                tg["prog"], tg["burst_until"] = 0.0, time.perf_counter() + 0.4
                tg["to"] = self._wander(tg["cell"], e.x, e.y, True)
                if random.random() < 0.25:
                    tg["health"] -= 1
                    tg["speed"] *= 0.88
                    tg["hit_n"] = tg.get("hit_n", 0) + 1
                    self._hit_mark(e.x, e.y, tg["hit_n"])
                    if tg["health"] <= 0:
                        self._save({"kind": "evasive", "hits": tg["hp0"], "switches": tg["switches"],
                                    "reaction_s": round(self.first_move or 0, 4),
                                    "path": tg["path"], "samples": self.samples})
                        self.canvas.delete("roach")
                        self._toast_xy(e.x, e.y, "SQUASHED", True)
                        self.state = "idle"
                        self.i += 1
                        return self.root.after(800, self._next)
                    return self._toast_xy(e.x, e.y, "STABBED it!", True)
                return self._toast_xy(e.x, e.y, "missed — it bolted out", False)

            if self.tool != "swatter":                        # on the run -> SWATTER
                return self._toast_xy(e.x, e.y, "use the SWATTER [T]", False)
            if math.hypot(e.x - tg["px"], e.y - tg["py"]) > 14:
                return
            tg["health"] -= 1
            tg["speed"] *= 0.88                               # wounded wood roach slows down
            tg["hit_n"] = tg.get("hit_n", 0) + 1
            self._hit_mark(e.x, e.y, tg["hit_n"])
            if tg["health"] <= 0:
                self._save({"kind": "evasive", "hits": tg["hp0"], "switches": tg["switches"],
                            "reaction_s": round(self.first_move or 0, 4),
                            "path": tg["path"], "samples": self.samples})
                self.canvas.delete("roach")
                self._toast_xy(e.x, e.y, "SQUASHED", True)
                self.state = "idle"
                self.i += 1
                return self.root.after(800, self._next)
            self._toast_xy(e.x, e.y, "hit!", True)

    # ---- end ------------------------------------------------------------

    def _finish(self):
        try:
            self.fh.close()
        except Exception:
            pass
        self.canvas.delete("all")
        self._hud("Done — thank you. Your movement is saved.", "#39d353",
                  sub=os.path.basename(self.path))
        self.state = "done"


def main() -> None:
    root = tk.Tk()
    Garden(root)
    root.mainloop()


if __name__ == "__main__":
    main()
