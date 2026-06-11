"""
arc.py — the longitudinal "arc" view: your movement signature over time.

Reads every session in recordings/ and plots your movement signature drifting
over time: reaction, accuracy, speed, tracking, tremor — one point per session,
with a trend (improving / declining) once there's more than one. Plus a
"tonight, round by round" strip so there's a real line on night one.

Zero dependencies (tkinter + stdlib). Local only.

    silphe-arc            # the dashboard, after `pip install silphe`
    silphe-arc --text     # headless summary
"""

from __future__ import annotations

import glob
import json
import math
import os
import statistics as st
import sys
import tkinter as tk

from silphe.analysis import recordings_dir

REC = recordings_dir()
KIND_COLOR = {"acquire": "#e3b341", "track": "#a371f7", "hold": "#58a6ff", "evasive": "#d29922"}


def load_sessions():
    out = []
    for fp in sorted(glob.glob(os.path.join(REC, "session-*.jsonl"))):
        rounds = [json.loads(l) for l in open(fp, encoding="utf-8") if l.strip()]
        if not rounds:
            continue
        parts = os.path.basename(fp)[:-6].split("-")  # session-<ts>-<device>
        ts = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else int(os.path.getmtime(fp))
        device = parts[2] if len(parts) > 2 else "?"
        out.append({"ts": ts, "device": device, "rounds": rounds})
    out.sort(key=lambda s: s["ts"])
    return out


def hold_jitter(r):
    s = r.get("samples", [])
    if len(s) < 10:
        return None
    tend = s[-1][0]
    tail = [p for p in s if p[0] >= tend - 1.0] or s
    return math.hypot(st.pstdev([p[1] for p in tail]), st.pstdev([p[2] for p in tail]))


def _med(vals, lo=None, hi=None):
    # median, with implausible values (pauses, walk-aways) filtered out
    v = [x for x in vals if x is not None
         and (lo is None or x >= lo) and (hi is None or x <= hi)]
    return st.median(v) if v else None


def metrics(rounds):
    by = lambda k: [r for r in rounds if r.get("kind") == k]
    acq = by("acquire")
    rt = _med([r["reaction_s"] for r in rounds if r.get("reaction_s") is not None], 0.05, 5.0)
    mt = _med([max(0.0, r["samples"][-1][0] - (r.get("reaction_s") or 0))
               for r in acq if r.get("samples")], 0, 15)
    return {
        "reaction_ms": rt * 1000 if rt is not None else None,
        "acquire_err": _med([r["click"]["err"] for r in acq if r.get("click")], 0, 400),
        "acquire_s": mt,
        "track_pct": _med([r["on_target_pct"] for r in by("track") if r.get("on_target_pct") is not None]),
        "tremor_px": _med([j for j in (hold_jitter(r) for r in by("hold")) if j is not None], 0, 40),
    }


PANELS = [
    ("reaction_ms", "REACTION", "down", lambda v: f"{v:.0f} ms"),
    ("acquire_err", "ACCURACY (miss)", "down", lambda v: f"{v:.1f} px"),
    ("acquire_s", "ACQUIRE SPEED", "down", lambda v: f"{v:.2f} s"),
    ("track_pct", "TRACKING", "up", lambda v: f"{v:.0f}%"),
    ("tremor_px", "TREMOR", "down", lambda v: f"{v:.1f} px"),
]


def text_report(sessions):
    print(f"{len(sessions)} session(s) in {REC}\n")
    for s in sessions:
        m = metrics(s["rounds"])
        cells = "  ".join(f"{k.split('_')[0]}={('-' if v is None else f'{v:.1f}')}" for k, v in m.items())
        print(f"  #{sessions.index(s)+1} [{s['device']:>8}] {len(s['rounds']):>2} rounds  {cells}")
    print()


# ---- GUI ----------------------------------------------------------------

def chart(cv, x, y, w, h, title, series, better, fmt):
    cv.create_rectangle(x, y, x + w, y + h, outline="#30363d", fill="#0d1117")
    cv.create_text(x + 10, y + 15, text=title, anchor="w", fill="#8b949e", font=("Consolas", 11, "bold"))
    vals = [v for v in series if v is not None]
    if not vals:
        cv.create_text(x + w / 2, y + h / 2, text="no data", fill="#6e7681", font=("Consolas", 10))
        return
    cv.create_text(x + w - 10, y + 15, text=fmt(vals[-1]), anchor="e", fill="#f0f6fc", font=("Consolas", 14, "bold"))
    px0, py0, px1, py1 = x + 14, y + 34, x + w - 14, y + h - 14
    lo, hi = min(vals), max(vals)
    if hi == lo:
        hi = lo + 1
    n = max(1, len(series) - 1)
    fx = lambda i: px0 + (px1 - px0) * (i / n)
    fy = lambda v: py1 - (py1 - py0) * ((v - lo) / (hi - lo))
    pts = [(fx(i), fy(v)) for i, v in enumerate(series) if v is not None]
    if len(pts) >= 2:
        cv.create_line(*sum(([a, b] for a, b in pts), []), fill="#58a6ff", width=2)
    for a, b in pts:
        cv.create_oval(a - 3, b - 3, a + 3, b + 3, fill="#58a6ff", outline="")
    if len(vals) >= 2:
        improving = (vals[-1] < vals[0]) if better == "down" else (vals[-1] > vals[0])
        col = "#39d353" if improving else "#f85149"
        cv.create_text(x + 10, y + h - 10, text=("improving" if improving else "declining"),
                       anchor="w", fill=col, font=("Consolas", 10, "bold"))
    else:
        cv.create_text(x + 10, y + h - 10, text="baseline — play again to start the arc",
                       anchor="w", fill="#6e7681", font=("Consolas", 9))


def tonight_strip(cv, x, y, w, h, rounds):
    cv.create_rectangle(x, y, x + w, y + h, outline="#30363d", fill="#0d1117")
    cv.create_text(x + 10, y + 15, text="TONIGHT — reaction time, round by round (ms)",
                   anchor="w", fill="#8b949e", font=("Consolas", 11, "bold"))
    series = [(r.get("kind"), (r.get("reaction_s") or 0) * 1000) for r in rounds]
    vals = [v for _, v in series]
    if not vals:
        return
    px0, py0, px1, py1 = x + 14, y + 34, x + w - 14, y + h - 22
    lo, hi = min(vals), max(vals)
    if hi == lo:
        hi = lo + 1
    n = max(1, len(series) - 1)
    fx = lambda i: px0 + (px1 - px0) * (i / n)
    fy = lambda v: py1 - (py1 - py0) * ((v - lo) / (hi - lo))
    line = [coord for i, (_, v) in enumerate(series) for coord in (fx(i), fy(v))]
    if len(line) >= 4:
        cv.create_line(*line, fill="#484f58", width=1)
    for i, (kind, v) in enumerate(series):
        c = KIND_COLOR.get(kind, "#58a6ff")
        cv.create_oval(fx(i) - 4, fy(v) - 4, fx(i) + 4, fy(v) + 4, fill=c, outline="")
    legend = "  ".join(f"● {k}" for k in KIND_COLOR)
    cv.create_text(x + 14, y + h - 9, text=legend, anchor="w", fill="#6e7681", font=("Consolas", 9))


def gui(sessions):
    root = tk.Tk()
    root.title("The Ministry of Silly Mice — Arc")
    root.configure(bg="#010409")
    W, H = 1120, 720
    cv = tk.Canvas(root, width=W, height=H, bg="#010409", highlightthickness=0)
    cv.pack(fill="both", expand=True)

    series = {key: [metrics(s["rounds"]).get(key) for s in sessions] for key, *_ in PANELS}
    devices = "/".join(sorted({s["device"] for s in sessions}))
    cv.create_text(20, 22, anchor="w", fill="#f0f6fc", font=("Consolas", 15, "bold"),
                   text=f"Your Arc — {len(sessions)} session(s) · {devices}")

    cols, cw, ch, gap = 3, 350, 175, 15
    for idx, (key, title, better, fmt) in enumerate(PANELS):
        cx = 20 + (idx % cols) * (cw + gap)
        cy = 48 + (idx // cols) * (ch + gap)
        chart(cv, cx, cy, cw, ch, title, series[key], better, fmt)

    tonight_strip(cv, 20, 48 + 2 * (ch + gap), 1080, 175, sessions[-1]["rounds"])
    root.bind("<Escape>", lambda e: root.destroy())
    root.mainloop()


def main():
    sessions = load_sessions()
    if not sessions:
        print("No recordings yet. Play a session: silphe-play")
        return
    if "--text" in sys.argv:
        text_report(sessions)
    else:
        gui(sessions)


if __name__ == "__main__":
    main()
