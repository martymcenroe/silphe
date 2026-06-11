"""
silphe-analyze — print this machine's AGGREGATE movement signature.

Reads your local session recordings (see :mod:`silphe.analysis` for the schema
and the recordings location) and prints summary numbers only — never raw
coordinates. The metrics themselves live in :mod:`silphe.analysis`; this is just
the console view.

    silphe-analyze              # after `pip install silphe`
    python -m silphe.analyze    # from a source checkout
"""

from __future__ import annotations

import statistics as st

from silphe.analysis import (
    acquire_stats,
    fitts_fit,
    hold_stats,
    load_recordings,
    recordings_dir,
)


def main() -> None:
    trials, files = load_recordings()
    if not trials:
        print("No recordings found in", recordings_dir())
        print("(Play a session: silphe-play)")
        return

    acq = [a for a in (acquire_stats(t) for t in trials if t.get("kind") == "acquire") if a]
    hold = [h for h in (hold_stats(t) for t in trials if t.get("kind") == "hold") if h]
    col = lambda rows, k: [r[k] for r in rows]

    print(f"Parsed {len(trials)} trials from {len(files)} session file(s).")

    print(f"\n=== ACQUIRE — the 'attempt' ({len(acq)} trials) ===")
    if acq:
        print(f"  movement time : mean {st.mean(col(acq,'mt')):.2f}s  "
              f"(min {min(col(acq,'mt')):.2f}, max {max(col(acq,'mt')):.2f})")
        print(f"  final error   : mean {st.mean(col(acq,'err')):.1f}px")
        print(f"  path wander   : mean {st.mean(col(acq,'eff')):.2f}x the straight line")
        print(f"  corrections   : mean {st.mean(col(acq,'rev')):.1f} per acquire  "
              f"(max {max(col(acq,'rev'))})  <- the 'tremor in the attempt'")
        print(f"  difficulty    : {min(col(acq,'ID')):.1f}-{max(col(acq,'ID')):.1f} bits (low = easy)")
        fit = fitts_fit(acq)
        if fit:
            print(f"  Fitts fit     : MT = {fit['a']:.2f} + {fit['b']:.2f}*ID   "
                  f"(base {fit['a']*1000:.0f}ms, {fit['b']*1000:.0f}ms per bit)")

    print(f"\n=== HOLD — the steady tremor ({len(hold)} trials) ===")
    if hold:
        print(f"  jitter amp    : mean {st.mean(col(hold,'jit')):.2f}px while holding still")
        print(f"  dominant freq : mean {st.mean(col(hold,'freq')):.1f} Hz")
        print("  per hold      : " + ", ".join(
            f"{h['jit']:.1f}px@{h['freq']:.0f}Hz" for h in hold))
    print()


if __name__ == "__main__":
    main()
