"""Scoring + leaderboard + player-roster unit tests (issues #29/#30)."""

import json

from silphe.analysis import known_players
from silphe.calibrate import LEADERBOARD_KEEP, round_score, update_leaderboard


def test_round_score_acquire_hit_scales_with_error():
    hit = {"kind": "acquire", "target": {"r": 15}, "click": {"err": 5.0}}
    graze = {"kind": "acquire", "target": {"r": 15}, "click": {"err": 20.0}}
    miss = {"kind": "acquire", "target": {"r": 15}, "click": {"err": 30.0}}
    assert round_score(hit) == 90
    assert round_score(graze) == 60
    assert round_score(miss) == 0            # beyond r * 1.4


def test_round_score_other_kinds():
    assert round_score({"kind": "track", "on_target_pct": 87}) == 87
    assert round_score({"kind": "hold"}) == 100
    assert round_score({"kind": "evasive", "hits": 5}) == 125
    assert round_score({"kind": "mystery"}) == 0


def test_update_leaderboard_sorts_and_truncates(tmp_path):
    path = str(tmp_path / "leaderboard.json")
    for j in range(LEADERBOARD_KEEP + 5):
        board = update_leaderboard(path, f"p{j}", j * 10, "2026-07-05")
    assert len(board) == LEADERBOARD_KEEP
    scores = [r["score"] for r in board]
    assert scores == sorted(scores, reverse=True)
    assert board[0] == {"name": f"p{LEADERBOARD_KEEP + 4}",
                        "score": (LEADERBOARD_KEEP + 4) * 10, "date": "2026-07-05"}
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == board


def test_update_leaderboard_survives_corrupt_file(tmp_path):
    path = str(tmp_path / "leaderboard.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("not json{{{")
    board = update_leaderboard(path, "solo", 42, "2026-07-05")
    assert board == [{"name": "solo", "score": 42, "date": "2026-07-05"}]


def test_known_players_scans_sibling_dirs(tmp_path, monkeypatch):
    base = tmp_path / "recordings"
    base.mkdir()
    (tmp_path / "recordings-Rebecca").mkdir()
    (tmp_path / "recordings-marty").mkdir()
    (tmp_path / "recordings-not-a-dir").write_text("")  # file, not a player
    monkeypatch.setenv("SILPHE_RECORDINGS", str(base))
    assert known_players() == ["Rebecca", "marty"]


def test_make_plan_covers_basics_before_first_evasive():
    from silphe.calibrate import make_plan
    for _ in range(200):
        plan = make_plan()
        assert sorted(plan) == ["acquire"] * 4 + ["evasive"] * 2 + ["hold"] * 3 + ["track"] * 3
        first_evasive = plan.index("evasive")
        for kind in ("acquire", "track", "hold"):
            assert plan.index(kind) < first_evasive
        assert sorted(plan[:3]) == ["acquire", "hold", "track"]


def test_difficulties_are_well_formed():
    from silphe.calibrate import DIFFICULTIES
    assert set(DIFFICULTIES) == {"easy", "normal", "hard"}
    for d in DIFFICULTIES.values():
        assert set(d) == {"hold_secs", "track_secs", "tol_mult", "roach_hp", "roach_speed"}
        lo, hi = d["roach_hp"]
        assert 0 < lo <= hi
    assert DIFFICULTIES["easy"]["hold_secs"] < DIFFICULTIES["hard"]["hold_secs"]
    assert DIFFICULTIES["easy"]["roach_speed"] < DIFFICULTIES["hard"]["roach_speed"]


def test_ska_riffs_well_formed_and_ska_is_safe_to_call():
    from silphe.calibrate import SKA_RIFFS, ska
    for seq in SKA_RIFFS.values():
        for freq, ms in seq:
            assert freq == 0 or 37 <= freq <= 32767   # winsound.Beep's legal range
            assert 0 < ms < 1000
    ska("board")          # fire-and-forget; must not raise even mid-test
    ska("no-such-event")  # unknown events are a no-op


def test_board_qualifies(tmp_path):
    from silphe.calibrate import LEADERBOARD_KEEP, board_qualifies, update_leaderboard
    path = str(tmp_path / "leaderboard.json")
    assert board_qualifies(path, 1)          # no board yet: anything lands
    assert not board_qualifies(path, 0)      # zero never qualifies
    for j in range(LEADERBOARD_KEEP):
        update_leaderboard(path, f"p{j}", (j + 1) * 100, "2026-07-05")
    assert board_qualifies(path, 150)        # beats the min (100)
    assert not board_qualifies(path, 100)    # ties don't bump

def test_default_initials():
    from silphe.calibrate import default_initials
    assert default_initials("Rebecca") == "REB"
    assert default_initials("mc-wiz9") == "MCW"
    assert default_initials("123") == "AAA"

def test_personal_best_roundtrip(tmp_path):
    from silphe.calibrate import personal_best, update_personal_best
    path = str(tmp_path / "personal-bests.json")
    assert personal_best(path, "Rebecca") == 0
    assert update_personal_best(path, "Rebecca", 500, "2026-07-05") == (500, True)
    assert update_personal_best(path, "Rebecca", 300, "2026-07-05") == (500, False)
    assert update_personal_best(path, "Rebecca", 700, "2026-07-05") == (700, True)
    assert update_personal_best(path, "marty", 100, "2026-07-05") == (100, True)
    assert personal_best(path, "Rebecca") == 700
    assert personal_best(path, "marty") == 100
