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
