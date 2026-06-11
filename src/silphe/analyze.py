"""
analyze.py — read the local calibration recordings and print AGGREGATE stats only.

No raw coordinates leave this script. It prints summary numbers (movement times,
overshoot, corrections, hold jitter + frequency, a Fitts fit) so we can fit the
movement model to the operator without dumping his every twitch.

    poetry run python talos-mouse-host/analyze.py
"""

from __future__ import annotations

import glob
import json
import math
import os
import statistics as st

REC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recordings")


def load():
    trials = []
    files = sorted(glob.glob(os.path.join(REC, "session-*.jsonl")))
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    trials.append(json.loads(line))
    return trials, len(files)


def acquire_stats(t):
    s = t["samples"]
    if len(s) < 3:
        return None
    tx, ty, r = t["target"]["x"], t["target"]["y"], t["target"]["r"]
    hx, hy = t["home"]["x"], t["home"]["y"]
    mt = s[-1][0] - s[0][0]
    plen = sum(math.hypot(s[i + 1][1] - s[i][1], s[i + 1][2] - s[i][2])
               for i in range(len(s) - 1))
    straight = math.hypot(tx - hx, ty - hy)
    eff = plen / straight if straight else 1.0
    rev, prev, shrinking = 0, None, True
    for (_t, x, y) in s:
        d = math.hypot(x - tx, y - ty)
        if prev is not None:
            if d > prev + 0.5 and shrinking:
                rev += 1
                shrinking = False
            elif d < prev - 0.5:
                shrinking = True
        prev = d
    ID = math.log2(straight / (2 * r) + 1)  # Shannon index of difficulty (bits)
    return dict(mt=mt, eff=eff, rev=rev, err=t["click"]["err"], ID=ID)


def hold_stats(t):
    s = t["samples"]
    if len(s) < 10:
        return None
    tend = s[-1][0]
    held = [p for p in s if p[0] >= tend - 1.5] or s   # just the steady-hold tail
    xs, ys = [p[1] for p in held], [p[2] for p in held]
    jit = math.hypot(st.pstdev(xs), st.pstdev(ys))
    mx = st.mean(xs)
    dur = held[-1][0] - held[0][0]
    crossings = sum(1 for i in range(len(xs) - 1) if (xs[i] - mx) * (xs[i + 1] - mx) < 0)
    freq = (crossings / 2) / dur if dur > 0 else 0.0
    return dict(jit=jit, freq=freq)


def main():
    trials, nfiles = load()
    if not trials:
        print("No recordings found in", REC)
        print("(Play a session: python talos-mouse-host/calibrate.py)")
        return

    acq = [a for a in (acquire_stats(t) for t in trials if t.get("kind") == "acquire") if a]
    hold = [h for h in (hold_stats(t) for t in trials if t.get("kind") == "hold") if h]
    col = lambda rows, k: [r[k] for r in rows]

    print(f"Parsed {len(trials)} trials from {nfiles} session file(s).")

    print(f"\n=== ACQUIRE - the'attempt' ({len(acq)} trials) ===")
    if acq:
        print(f"  movement time : mean {st.mean(col(acq,'mt')):.2f}s  "
              f"(min {min(col(acq,'mt')):.2f}, max {max(col(acq,'mt')):.2f})")
        print(f"  final error   : mean {st.mean(col(acq,'err')):.1f}px")
        print(f"  path wander   : mean {st.mean(col(acq,'eff')):.2f}x the straight line")
        print(f"  corrections   : mean {st.mean(col(acq,'rev')):.1f} per acquire  "
              f"(max {max(col(acq,'rev'))})  <-- the 'tremor in the attempt'")
        print(f"  difficulty    : {min(col(acq,'ID')):.1f}-{max(col(acq,'ID')):.1f} bits (low = easy)")
        ids, mts = col(acq, 'ID'), col(acq, 'mt')
        mid, mmt = st.mean(ids), st.mean(mts)
        denom = sum((i - mid) ** 2 for i in ids)
        if denom > 0:
            b = sum((ids[i] - mid) * (mts[i] - mmt) for i in range(len(ids))) / denom
            a = mmt - b * mid
            print(f"  Fitts fit     : MT = {a:.2f} + {b:.2f}*ID   "
                  f"(your a={a*1000:.0f}ms base, b={b*1000:.0f}ms per bit)")

    print(f"\n=== HOLD - thesteady tremor ({len(hold)} trials) ===")
    if hold:
        print(f"  jitter amp    : mean {st.mean(col(hold,'jit')):.2f}px while holding still")
        print(f"  dominant freq : mean {st.mean(col(hold,'freq')):.1f} Hz")
        print("  per hold      : " + ", ".join(
            f"{h['jit']:.1f}px@{h['freq']:.0f}Hz" for h in hold))
    print()


if __name__ == "__main__":
    main()
