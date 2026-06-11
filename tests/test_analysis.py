"""Tests for silphe.analysis — the movement-signature math.

Where possible these inject a *known* truth (a known Fitts slope, a known lag, a
known tremor frequency) and assert the analyzer recovers it.
"""

import math

from silphe.analysis import (
    acquire_stats,
    fitts_fit,
    hold_stats,
    lag_scan,
    session_signature,
)


def _acquire(home, target, r, path, err=2.0):
    samples = [[i * 0.01, x, y] for i, (x, y) in enumerate(path)]
    return {
        "kind": "acquire",
        "samples": samples,
        "target": {"x": target[0], "y": target[1], "r": r},
        "home": {"x": home[0], "y": home[1]},
        "click": {"x": target[0], "y": target[1], "err": err},
    }


def test_acquire_stats_on_a_straight_path():
    path = [(i * 10, 0) for i in range(11)]   # (0,0) -> (100,0), monotonic
    s = acquire_stats(_acquire((0, 0), (100, 0), 10, path))
    assert s is not None
    assert abs(s["eff"] - 1.0) < 0.01      # straight line: path == straight distance
    assert s["rev"] == 0                   # no corrective reversals
    assert abs(s["ID"] - math.log2(100 / 20 + 1)) < 1e-9
    assert s["err"] == 2.0


def test_acquire_stats_counts_a_reversal():
    # approach, then overshoot far past the target (distance to target grows
    # again), then correct back -> one corrective reversal
    path = [(0, 0), (90, 0), (150, 0), (100, 0)]
    s = acquire_stats(_acquire((0, 0), (100, 0), 10, path))
    assert s["rev"] >= 1


def test_hold_stats_recovers_known_frequency():
    # 5 Hz oscillation over exactly 1 s -> dominant frequency should read ~5 Hz
    samples = [[i * 0.01, 10 * math.sin(2 * math.pi * 5 * (i * 0.01)), 0.0]
               for i in range(101)]
    s = hold_stats({"kind": "hold", "samples": samples,
                    "target": {"x": 0, "y": 0, "r": 5}})
    assert s is not None
    assert abs(s["freq"] - 5.0) < 0.6


def test_fitts_fit_recovers_known_slope():
    rows = [{"ID": i, "mt": 0.20 + 0.15 * i} for i in (1, 2, 3, 4, 5)]
    fit = fitts_fit(rows)
    assert fit is not None
    assert abs(fit["a"] - 0.20) < 1e-9
    assert abs(fit["b"] - 0.15) < 1e-9


def test_fitts_fit_needs_two_points():
    assert fitts_fit([{"ID": 2.0, "mt": 0.5}]) is None


def test_lag_scan_recovers_injected_lag():
    n = 200
    tgt_xy = [(100 * math.sin(i * 0.07), 100 * math.cos(i * 0.07)) for i in range(n)]
    target = [[i * 0.02, x, y] for i, (x, y) in enumerate(tgt_xy)]
    # the cursor sits where the target was 5 samples (= 100 ms) earlier
    cursor = [[i * 0.02, tgt_xy[i - 5][0], tgt_xy[i - 5][1]] for i in range(5, n)]
    res = lag_scan(cursor, target)
    assert res is not None
    assert res["lag_ms"] == 100
    assert res["err"] < 1.0          # near-perfect alignment once the lag is removed


def test_lag_scan_too_short_returns_none():
    assert lag_scan([[0, 0, 0]], [[0, 0, 0]]) is None


def test_session_signature_integrates_task_types():
    trials = [_acquire((0, 0), (100, 0), 10, [(i * 10, 0) for i in range(11)])]
    sig = session_signature(trials)
    assert sig["n_trials"] == 1
    assert sig["acquire"] is not None and sig["acquire"]["n"] == 1
    assert sig["hold"] is None        # no hold trials supplied
    assert sig["track"] is None
