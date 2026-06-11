"""
range_demo.py — a safe little shooting range for the keystone.

A local tkinter window with a bullseye. You trigger the cursor; it stalks the
target like a human (or like a robot, for contrast) and lands a real OS click on
the canvas. The path it actually took is drawn so you can SEE the difference.

Nothing here touches any website — it's a window on your own machine.

    silphe-demo                   # after `pip install silphe`
    python -m silphe.range_demo   # from a source checkout

Controls:
    SPACE  — human cursor fires at the target
    R      — robot cursor fires (straight line, no tremor — the foil)
    N      — new target (clears the drawn paths)
    ESC    — quit

Heads-up: when you fire, your real pointer gets pulled to the target for about a
second. That's the whole point. ESC any time the range is idle.
"""

from __future__ import annotations

import random
import time
import tkinter as tk

from silphe import cursor as hc

HUMAN_COLOR = "#39d353"   # GitHub-garden green, naturally
ROBOT_COLOR = "#f85149"   # sterile red
TARGET_R = 22


class Range:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("The Ministry of Silly Mice — Firing Range")
        root.configure(bg="#0d1117")
        self.W, self.H = 1200, 760

        self.canvas = tk.Canvas(root, width=self.W, height=self.H,
                                bg="#0d1117", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.human = hc.HumanCursor()              # swap to hc.TREMOR_PROFILE for a heavier tremor
        self.robot = hc.RobotCursor()
        self.tx = self.ty = 0
        self.busy = False

        self.canvas.bind("<Button-1>", self._on_click)
        root.bind("<space>", lambda e: self._fire(self.human, HUMAN_COLOR, "HUMAN"))
        root.bind("r", lambda e: self._fire(self.robot, ROBOT_COLOR, "ROBOT"))
        root.bind("R", lambda e: self._fire(self.robot, ROBOT_COLOR, "ROBOT"))
        root.bind("n", lambda e: self.new_target())
        root.bind("N", lambda e: self.new_target())
        root.bind("<Escape>", lambda e: root.destroy())

        self.new_target()

    # ---- drawing --------------------------------------------------------

    def _hud(self, msg, color="#8b949e"):
        self.canvas.delete("hud")
        self.canvas.create_text(
            self.W // 2, 28, text=msg, fill=color, tag="hud",
            font=("Consolas", 14, "bold"))
        self.canvas.create_text(
            self.W // 2, self.H - 22, tag="hud", fill="#6e7681",
            font=("Consolas", 11),
            text="SPACE human   ·   R robot   ·   N new target   ·   ESC quit")

    def new_target(self):
        self.canvas.delete("all")
        m = 120
        self.tx = random.randint(m, self.W - m)
        self.ty = random.randint(m + 30, self.H - m)
        for i, r in enumerate((TARGET_R, TARGET_R * 0.66, TARGET_R * 0.33)):
            self.canvas.create_oval(self.tx - r, self.ty - r, self.tx + r, self.ty + r,
                                    outline="#30363d" if i == 0 else "#484f58", width=2)
        self.canvas.create_oval(self.tx - 3, self.ty - 3, self.tx + 3, self.ty + 3,
                                fill="#39d353", outline="")
        self._hud("Fire when ready.")

    def _draw_path(self, waypoints, rootx, rooty, color):
        pts = []
        for (wx, wy, _dt) in waypoints:
            pts.extend((wx - rootx, wy - rooty))
        if len(pts) >= 4:
            self.canvas.create_line(*pts, fill=color, width=2, smooth=False)

    # ---- firing ---------------------------------------------------------

    def _fire(self, cursor, color, label):
        if self.busy:
            return
        self.busy = True
        for n in ("3", "2", "1"):
            self._hud(f"{label} locking on…  {n}", color)
            self.canvas.update()
            time.sleep(0.18)
        rootx, rooty = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
        screen_x, screen_y = rootx + self.tx, rooty + self.ty
        waypoints = cursor.click(screen_x, screen_y)        # <-- real cursor + trusted click
        self._draw_path(waypoints, rootx, rooty, color)
        self._hud(f"{label}: {len(waypoints)} micro-moves traced.", color)
        self.busy = False

    def _on_click(self, event):
        # Fires from the trusted OS click the cursor just issued.
        d = ((event.x - self.tx) ** 2 + (event.y - self.ty) ** 2) ** 0.5
        hit = d <= TARGET_R
        self.canvas.create_oval(event.x - 5, event.y - 5, event.x + 5, event.y + 5,
                                outline="#f0f6fc", width=2)
        self.canvas.create_text(
            self.tx, self.ty - TARGET_R - 16, tag="hud",
            fill="#39d353" if hit else "#f85149", font=("Consolas", 13, "bold"),
            text="HIT" if hit else f"{d:.0f}px off")


def main() -> None:
    root = tk.Tk()
    Range(root)
    root.mainloop()


if __name__ == "__main__":
    main()
