"""
silphe.analysis — quantify a movement signature from recorded sessions.

These helpers read Silphe's session recordings and return **aggregate metrics
only** — movement time, path wander, corrective sub-movements, a Fitts's-law
fit, hold tremor (amplitude + dominant frequency), and a decomposition of
tracking into temporal *lag* / spatial *offset* / residual *noise*. No raw
coordinates are returned by the summary helpers, by design: the point is to
characterize the hand without exposing the trace.

Pure standard library; runs on any platform.

Session schema
--------------
A *session* is a ``.jsonl`` file (one JSON object — a *trial* — per line).
Common keys on every trial::

    kind      : "acquire" | "track" | "hold" | "evasive"
    samples   : [[t, x, y], ...]    cursor trace; t = seconds from trial start
    reaction_s, device, os

Per kind::

    acquire   : target{x, y, r}, home{x, y}, click{x, y, err}
    hold      : target{x, y, r}
    track     : dot [[t, x, y], ...]   (target trace), locked_at, on_target_pct
    evasive   : path[[t, x, y], ...]   (target trace), hits, switches

``move_to``-style generated paths (see :mod:`silphe.model`) are NOT sessions;
these helpers operate on *recorded human* sessions written by the calibration
game.
"""

from __future__ import annotations

import bisect
import glob
import json
import math
import os
import statistics as st

__all__ = [
    "recordings_dir",
    "player_recordings_dir",
    "known_players",
    "load_session",
    "load_recordings",
    "acquire_stats",
    "hold_stats",
    "fitts_fit",
    "lag_scan",
    "session_signature",
]


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

# The recordings-dir helpers moved into the capture kernel (silphe.core, #48)
# so the game and the analyzers share one definition. Re-exported here for
# backward compatibility — existing callers of silphe.analysis keep working.
from silphe.core import known_players, player_recordings_dir, recordings_dir  # noqa: E402,F401


def load_session(path: str) -> list[dict]:
    """Load one ``session-*.jsonl`` file into a list of trial dicts."""
    trials = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                trials.append(json.loads(line))
    return trials


def load_recordings(directory: str | None = None) -> tuple[list[dict], list[str]]:
    """Load every ``session-*.jsonl`` under *directory* (default
    :func:`recordings_dir`). Returns ``(flat_trials, file_paths)``.
    """
    directory = directory or recordings_dir()
    files = sorted(glob.glob(os.path.join(directory, "session-*.jsonl")))
    trials = []
    for fp in files:
        trials.extend(load_session(fp))
    return trials, files


# --------------------------------------------------------------------------
# Per-trial metrics
# --------------------------------------------------------------------------

def acquire_stats(trial: dict) -> dict | None:
    """Metrics for one ACQUIRE trial: movement time, path wander, corrective
    reversals, final error, and the Shannon index of difficulty (bits)."""
    s = trial["samples"]
    if len(s) < 3:
        return None
    tx, ty, r = trial["target"]["x"], trial["target"]["y"], trial["target"]["r"]
    hx, hy = trial["home"]["x"], trial["home"]["y"]
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
    idx = math.log2(straight / (2 * r) + 1) if r > 0 else 0.0   # Fitts ID (bits)
    return dict(mt=mt, eff=eff, rev=rev, err=trial["click"]["err"], ID=idx)


def hold_stats(trial: dict) -> dict | None:
    """Metrics for one HOLD trial: tremor amplitude (px) and dominant
    frequency (Hz) of the steady-hold tail."""
    s = trial["samples"]
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


def fitts_fit(acquire_rows: list[dict]) -> dict | None:
    """Least-squares Fitts fit ``MT = a + b * ID`` over ACQUIRE rows (as
    produced by :func:`acquire_stats`). ``a`` is base time (s), ``b`` is seconds
    per bit. Returns ``None`` if there is too little spread to fit."""
    rows = [r for r in acquire_rows if r]
    if len(rows) < 2:
        return None
    ids = [r["ID"] for r in rows]
    mts = [r["mt"] for r in rows]
    mid, mmt = st.mean(ids), st.mean(mts)
    denom = sum((i - mid) ** 2 for i in ids)
    if denom <= 0:
        return None
    b = sum((ids[i] - mid) * (mts[i] - mmt) for i in range(len(ids))) / denom
    a = mmt - b * mid
    return dict(a=a, b=b)


# --------------------------------------------------------------------------
# Tracking: temporal lag vs spatial offset vs residual noise
# --------------------------------------------------------------------------

def _interp(path, ts, tq):
    if tq <= ts[0]:
        return path[0][1], path[0][2]
    if tq >= ts[-1]:
        return path[-1][1], path[-1][2]
    i = bisect.bisect_left(ts, tq)
    t0, x0, y0 = path[i - 1]
    t1, x1, y1 = path[i]
    f = (tq - t0) / (t1 - t0) if t1 > t0 else 0.0
    return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f


def _near(ts, t, tol=0.08):
    i = bisect.bisect_left(ts, t)
    return any(0 <= j < len(ts) and abs(ts[j] - t) <= tol for j in (i - 1, i))


def lag_scan(cursor: list, target: list, gap_filter: bool = False) -> dict | None:
    """Find the time-shift that best aligns *cursor* to *target* (both lists of
    ``[t, x, y]``). Returns the best lag (ms), the residual error at that lag,
    the constant aim offset ``(dx, dy)``, and the error at zero lag — separating
    *being late* from *being inaccurate*. ``gap_filter`` skips target times with
    no nearby sample (e.g. while an evasive target was hidden)."""
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
            if gap_filter and not _near(ts, tq):
                continue
            tx, ty = _interp(target, ts, tq)
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


# --------------------------------------------------------------------------
# Whole-session signature
# --------------------------------------------------------------------------

def _mean(vals):
    vals = [v for v in vals if v is not None]
    return st.mean(vals) if vals else None


def session_signature(trials: list[dict]) -> dict:
    """Bundle a movement signature from a flat list of trials: acquire timing +
    accuracy + Fitts fit, hold tremor, and tracking lag/offset for the smooth
    (``track``) and evasive targets. Missing task types come back as ``None``.
    """
    acq = [a for a in (acquire_stats(t) for t in trials if t.get("kind") == "acquire") if a]
    hold = [h for h in (hold_stats(t) for t in trials if t.get("kind") == "hold") if h]

    sig: dict = {
        "n_trials": len(trials),
        "acquire": None,
        "hold": None,
        "track": None,
        "evasive": None,
    }

    if acq:
        sig["acquire"] = {
            "n": len(acq),
            "movement_time_s": _mean([a["mt"] for a in acq]),
            "final_error_px": _mean([a["err"] for a in acq]),
            "path_wander_x": _mean([a["eff"] for a in acq]),
            "corrections": _mean([a["rev"] for a in acq]),
            "fitts": fitts_fit(acq),
        }
    if hold:
        sig["hold"] = {
            "n": len(hold),
            "tremor_px": _mean([h["jit"] for h in hold]),
            "tremor_hz": _mean([h["freq"] for h in hold]),
        }

    for kind, tkey, gap in (("track", "dot", False), ("evasive", "path", True)):
        scans = []
        for r in trials:
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
        if scans:
            sig[kind] = {
                "n": len(scans),
                "lag_ms": _mean([s["lag_ms"] for s in scans]),
                "error_at_lag_px": _mean([s["err"] for s in scans]),
                "error_at_zero_lag_px": _mean([s["zero_err"] for s in scans]),
                "aim_offset_px": (
                    _mean([s["dx"] for s in scans]),
                    _mean([s["dy"] for s in scans]),
                ),
            }
    return sig
