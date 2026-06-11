"""
analyze_lag.py — how late is the cursor vs the moving target?

Lines up the operator's cursor against where the target (track dot / roach) actually
was, and finds the time-shift that best explains the tracking. Separates:
  - temporal LAG  (you're behind in time)        -> "am I late?"
  - spatial OFFSET (constant dx/dy bias)          -> "graphics/aim off?"
  - residual ERROR (noise left after both)        -> "do I just suck?"

Aggregate numbers only; no raw coordinates printed.

    poetry run python talos-mouse-host/analyze_lag.py
"""

from __future__ import annotations

import bisect
import glob
import json
import math
import os

REC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordings")


def latest_session():
    fs = glob.glob(os.path.join(REC, "session-*.jsonl"))
    return max(fs, key=os.path.getmtime) if fs else None


def interp(path, ts, tq):
    if tq <= ts[0]:
        return path[0][1], path[0][2]
    if tq >= ts[-1]:
        return path[-1][1], path[-1][2]
    i = bisect.bisect_left(ts, tq)
    t0, x0, y0 = path[i - 1]
    t1, x1, y1 = path[i]
    f = (tq - t0) / (t1 - t0) if t1 > t0 else 0.0
    return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f


def near(ts, t, tol=0.08):
    i = bisect.bisect_left(ts, t)
    return any(0 <= j < len(ts) and abs(ts[j] - t) <= tol for j in (i - 1, i))


def lag_scan(cursor, target, gap_filter=False):
    if len(cursor) < 10 or len(target) < 10:
        return None
    ts = [p[0] for p in target]
    results = {}
    for lag_ms in range(-40, 460, 20):
        lag = lag_ms / 1000.0
        tot = cnt = sdx = sdy = 0.0
        for (t, cx, cy) in cursor:
            tq = t - lag
            if tq < ts[0] or tq > ts[-1]:
                continue
            if gap_filter and not near(ts, tq):   # skip times the roach was hidden
                continue
            tx, ty = interp(target, ts, tq)
            tot += math.hypot(cx - tx, cy - ty)
            sdx += cx - tx
            sdy += cy - ty
            cnt += 1
        if cnt >= 10:
            results[lag_ms] = (tot / cnt, sdx / cnt, sdy / cnt)
    if not results:
        return None
    best = min(results, key=lambda k: results[k][0])
    err, dx, dy = results[best]
    zero = results.get(0, (None,))[0]
    return dict(lag_ms=best, err=err, dx=dx, dy=dy, zero_err=zero)


def main():
    sf = latest_session()
    if not sf:
        print("No recordings. Play a session first.")
        return
    rounds = [json.loads(l) for l in open(sf, encoding="utf-8") if l.strip()]
    print(f"Session: {os.path.basename(sf)}   ({len(rounds)} rounds)")

    for kind, tkey, gap in (("track", "dot", False), ("evasive", "path", True)):
        scans = []
        for r in rounds:
            if r.get("kind") != kind or not r.get(tkey) or not r.get("samples"):
                continue
            cur, tgt = r["samples"], r[tkey]
            if kind == "track":                       # only the steady, post-lock pursuit
                lk = r.get("locked_at", 0)
                cur = [s for s in cur if s[0] >= lk]
                tgt = [d for d in tgt if d[0] >= lk]
            s = lag_scan(cur, tgt, gap)
            if s:
                scans.append(s)
        if not scans:
            print(f"\n{kind.upper()}: no usable rounds")
            continue
        avg = lambda k: sum(s[k] for s in scans) / len(scans)
        ze = [s["zero_err"] for s in scans if s["zero_err"] is not None]
        print(f"\n=== {kind.upper()}  ({len(scans)} rounds) ===")
        print(f"  you lag the target by : {avg('lag_ms'):+.0f} ms   <- how far BEHIND you are in time")
        print(f"  error at THAT lag     : {avg('err'):.1f} px   (how tight you are once your delay is removed)")
        if ze:
            print(f"  error at zero lag     : {sum(ze)/len(ze):.1f} px   (how it looks if you had no reaction delay)")
        print(f"  constant aim offset   : dx {avg('dx'):+.1f}px, dy {avg('dy'):+.1f}px   (a real bias, or graphics, if big)")
    print()


if __name__ == "__main__":
    main()
