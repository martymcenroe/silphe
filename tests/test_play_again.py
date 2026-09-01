"""The end screen is not a dead end — issue #88.

`done` used to refuse ESC and P and draw no buttons, so closing the window was
the only way out of a finished run and relaunching the only way back in.
"""

import os

import pytest

tk = pytest.importorskip("tkinter")


class Click:
    def __init__(self, x, y):
        self.x, self.y = int(x), int(y)


@pytest.fixture(scope="module")
def root():
    try:
        win = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no Tk display: {exc}")
    win.withdraw()
    yield win
    win.destroy()


@pytest.fixture()
def ended(root, tmp_path, monkeypatch):
    """A game that has finished a run and is sitting on the end screen."""
    from silphe import calibrate

    monkeypatch.setenv("SILPHE_RECORDINGS", str(tmp_path / "recordings"))
    monkeypatch.setattr(calibrate, "ska", lambda event: None)
    g = calibrate.Garden(root, device="mouse", player="Rebecca", difficulty="easy")
    g.score = 120
    g._conclude("Rebecca", entry_name="REB")
    try:
        yield g
    finally:
        g.recorder.close()
        g.canvas.destroy()


def labels(g):
    return [g.canvas.itemcget(i, "text") for i in g.canvas.find_withtag("endmenu")
            if g.canvas.type(i) == "text"]


def press(g, label):
    """Click the button carrying *label*, through the real hit-testing."""
    for i in g.canvas.find_withtag("endmenu"):
        if g.canvas.type(i) == "text" and g.canvas.itemcget(i, "text") == label:
            x, y = g.canvas.coords(i)
            return g._click(Click(x, y))
    raise AssertionError(f"no button labelled {label!r}")


# ---- the way out exists ---------------------------------------------------

def test_the_end_screen_offers_a_way_on(ended):
    assert ended.state == "done"
    assert labels(ended) == ["PLAY AGAIN", "DIFFICULTY", "SWITCH PLAYER", "QUIT"]


def test_the_buttons_take_clicks(ended):
    """`_click` refused every state but the menus, so the buttons would have
    been decoration."""
    assert ended._menu_buttons
    press(ended, "PLAY AGAIN")
    assert ended.state != "done"


def test_play_again_is_first(ended):
    """The common case should not be third."""
    assert labels(ended)[0] == "PLAY AGAIN"


# ---- what a restart resets ------------------------------------------------

def test_play_again_keeps_the_player_and_difficulty(ended):
    press(ended, "PLAY AGAIN")
    assert ended.player == "Rebecca"
    assert ended.difficulty == "easy"


def test_play_again_starts_the_score_over(ended):
    press(ended, "PLAY AGAIN")
    assert ended.score == 0
    assert ended.i == 0


def test_play_again_opens_a_new_session_file(ended, tmp_path):
    """The finished recorder is closed, and writing to a closed one raises on
    purpose (#78) — so a restart must not reuse it."""
    finished = ended.recorder
    press(ended, "PLAY AGAIN")
    assert ended.recorder is not finished
    ended.recorder.write({"kind": "hold"})                  # must not raise
    assert os.path.exists(ended.recorder.path)


def test_play_again_lays_a_new_field(ended):
    """The end screen cleared the canvas, so the old cell ids are gone. If they
    were kept, repainting would configure deleted items and raise."""
    press(ended, "PLAY AGAIN")
    assert len(ended.cells) == ended.ROWS * ended.COLS
    ended._paint_field()                                    # must not raise


def test_play_again_gets_a_fresh_plan(ended):
    """A full plan, opening on one of each basic type — the same guarantee a
    new player gets, since a restart is a new run."""
    press(ended, "PLAY AGAIN")
    assert len(ended.plan) == 12
    assert sorted(ended.plan[:3]) == ["acquire", "hold", "track"]


def test_the_finished_score_stays_on_the_board(ended, tmp_path):
    """Starting again must not undo the run that just ended."""
    from silphe.calibrate import leaderboard_path

    with open(leaderboard_path(), encoding="utf-8") as f:
        import json
        before = json.load(f)
    press(ended, "PLAY AGAIN")
    with open(leaderboard_path(), encoding="utf-8") as f:
        import json
        assert json.load(f) == before


# ---- the other three ------------------------------------------------------

def test_difficulty_returns_to_the_difficulty_menu(ended):
    press(ended, "DIFFICULTY")
    assert ended.state == "difficulty_menu"


def test_switch_player_returns_to_the_player_menu(ended):
    press(ended, "SWITCH PLAYER")
    assert ended.state == "launch_player_menu"


def test_switch_player_then_choosing_lands_in_a_round(ended):
    """Difficulty was already settled this launch, so picking a player goes
    straight back into play rather than asking again."""
    press(ended, "SWITCH PLAYER")
    ended._choose_launch_player("Marshy")
    assert ended.player == "Marshy"
    assert ended.recorder.player == "Marshy"
    assert ended.state not in ("done", "launch_player_menu")


def test_quitting_from_the_end_does_not_conclude_twice(ended, monkeypatch):
    """`_quit` runs `_finish`, which would take an already-concluded run
    through the leaderboard a second time."""
    concluded = []
    monkeypatch.setattr(type(ended), "_finish",
                        lambda self: concluded.append(True))
    monkeypatch.setattr(type(ended.root), "destroy", lambda self: None)
    press(ended, "QUIT")
    assert concluded == [], "quitting re-ran the ending"
