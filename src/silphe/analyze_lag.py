"""
silphe-lag — how late is the cursor vs the moving target?

Lines up your cursor against where the target actually was and decomposes the
tracking into temporal LAG (you're behind in time), spatial OFFSET (a constant
aim bias), and residual ERROR (noise left after both). Aggregate numbers only;
no raw coordinates printed. The math lives in :func:`silphe.analysis.lag_scan`.

    silphe-lag                    # after `pip install silphe`
    python -m silphe.analyze_lag  # from a source checkout
"""

from __future__ import annotations

import glob
import json
import os

from silphe.analysis import lag_scan, recordings_dir


def _latest_session() -> str | None:
    fs = glob.glob(os.path.join(recordings_dir(), "session-*.jsonl"))
    return max(fs, key=os.path.getmtime) if fs else None


def main() -> None:
    sf = _latest_session()
    if not sf:
        print("No recordings. Play a session first: silphe-play")
        return
    rounds = [json.loads(line) for line in open(sf, encoding="utf-8") if line.strip()]
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
        print(f"  error at THAT lag     : {avg('err'):.1f} px   (how tight you are once the delay is removed)")
        if ze:
            print(f"  error at zero lag     : {sum(ze)/len(ze):.1f} px   (how it looks with no reaction delay)")
        print(f"  constant aim offset   : dx {avg('dx'):+.1f}px, dy {avg('dy'):+.1f}px   (a real bias, or graphics, if big)")
    print()


if __name__ == "__main__":
    main()
