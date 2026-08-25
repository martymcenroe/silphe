"""Launch flow and initials entry — issues #73, #74, #75, #76.

Drives a real `Garden` on a hidden Tk root. One module-scoped root: tearing a
root down and building another in the same process leaves Tcl unable to find
its own library, and the resulting failures come back as skips, which read as
green.
"""

import json
import os

import pytest

tk = pytest.importorskip("tkinter")


class Key:
    """Stands in for a Tk key event."""

    def __init__(self, char="", keysym=None):
        self.char = char
        self.keysym = keysym or (char.upper() if char else "")


@pytest.fixture(scope="module")
def root():
    try:
        win = tk.Tk()
    except tk.TclError as exc:                              # no display
        pytest.skip(f"no Tk display: {exc}")
    win.withdraw()
    yield win
    win.destroy()


def recordings_under(tmp_path, monkeypatch):
    """Point the game at a recordings dir INSIDE *tmp_path*, not at tmp_path
    itself. The leaderboard and personal-bests files are siblings of the
    recordings dir, so pointing at tmp_path puts them in pytest's shared
    per-run directory where every test in the session would share one board.
    """
    from silphe import calibrate

    rec = tmp_path / "recordings"
    monkeypatch.setenv("SILPHE_RECORDINGS", str(rec))
    monkeypatch.setattr(calibrate, "ska", lambda event: None)
    return rec


@pytest.fixture()
def game(root, tmp_path, monkeypatch):
    """A freshly launched Garden, no player given — so it opens on the WHO'S
    PLAYING menu."""
    from silphe import calibrate

    recordings_under(tmp_path, monkeypatch)
    g = calibrate.Garden(root, device="mouse", player=None, difficulty=None)
    try:
        yield g
    finally:
        g.recorder.close()
        g.canvas.destroy()


def named(root, tmp_path, monkeypatch, **kw):
    """A Garden launched with arguments — the CLI-flag path."""
    from silphe import calibrate

    recordings_under(tmp_path, monkeypatch)
    return calibrate.Garden(root, device="mouse", **kw)


def menu_labels(g):
    """Every text item currently tagged as menu."""
    return [g.canvas.itemcget(i, "text") for i in g.canvas.find_withtag("menu")
            if g.canvas.type(i) == "text"]


# ---- #73 the boxes are opaque ---------------------------------------------

def test_every_menu_box_is_filled_not_transparent(game):
    """An unfilled canvas rectangle is see-through, so the garden showed
    through the labels. Assert on the fill of the boxes themselves rather than
    on how it looks."""
    from silphe.calibrate import BG

    boxes = [i for i in game.canvas.find_withtag("menu")
             if game.canvas.type(i) == "rectangle"]
    assert boxes, "the menu drew no boxes at all"
    for box in boxes:
        assert game.canvas.itemcget(box, "fill") == BG, "this box is transparent"


def test_the_menu_panel_matches_the_window_behind_it(game):
    """One near-black, not two: the boxes use the same colour as the canvas."""
    assert game.canvas.cget("bg") == "#0d1117"


# ---- #75 who's playing, at launch -----------------------------------------

def test_launch_asks_who_is_playing_before_anything_is_recorded(game):
    assert game.state == "launch_player_menu"
    assert "WHO'S PLAYING?" in menu_labels(game)
    assert "CHOOSE DIFFICULTY" not in menu_labels(game)


def test_the_launch_menu_offers_the_default_explicitly(game):
    """Playing as nobody has to be a choice, not what happens when you do not
    make one — that is how a session ends up filed under `default`."""
    assert "PLAY AS DEFAULT" in menu_labels(game)
    assert "NEW PLAYER..." in menu_labels(game)


def test_known_players_are_listed(root, tmp_path, monkeypatch):
    from silphe import calibrate

    rec = recordings_under(tmp_path, monkeypatch)
    (rec.parent / (rec.name + "-Rebecca")).mkdir(parents=True)
    g = calibrate.Garden(root, device="mouse", player=None, difficulty=None)
    try:
        assert "Rebecca" in menu_labels(g)
    finally:
        g.recorder.close()
        g.canvas.destroy()


def test_choosing_the_default_at_launch_goes_on_to_the_difficulty_menu(game):
    """`_choose_player` returns early when the name already matches and resumes
    a round instead. At launch the player is already None, so the default is
    exactly the case that would have hit it."""
    game._choose_launch_player(None)
    assert game.state == "difficulty_menu"
    assert "CHOOSE DIFFICULTY" in menu_labels(game)


def test_choosing_a_named_player_at_launch_records_as_them(game, tmp_path):
    game._choose_launch_player("Rebecca")
    assert game.player == "Rebecca"
    assert game.recorder.player == "Rebecca"
    # Their own sibling of the recordings dir, per player_recordings_dir.
    assert os.path.dirname(game.recorder.path) == str(tmp_path / "recordings") + "-Rebecca"
    assert game.state == "difficulty_menu"


def test_the_launch_choice_does_not_reset_the_session_the_way_a_switch_does(game):
    """The mid-session switch reshuffles the plan and zeroes the score because
    it is abandoning a session. There is nothing to abandon at launch."""
    plan_before = list(game.plan)
    game.score = 0
    game._choose_launch_player("Rebecca")
    assert game.plan == plan_before
    assert game.i == 0


def test_player_on_the_command_line_skips_the_menu(root, tmp_path, monkeypatch):
    g = named(root, tmp_path, monkeypatch, player="Rebecca", difficulty=None)
    try:
        assert g.state == "difficulty_menu"
        assert g.player == "Rebecca"
    finally:
        g.recorder.close()
        g.canvas.destroy()


def test_both_flags_together_skip_straight_into_the_round(root, tmp_path, monkeypatch):
    g = named(root, tmp_path, monkeypatch, player="Rebecca", difficulty="easy")
    try:
        assert g.state not in ("launch_player_menu", "difficulty_menu")
        assert g.difficulty == "easy"
    finally:
        g.recorder.close()
        g.canvas.destroy()


def test_escape_does_not_open_the_pause_menu_over_the_launch_menu(game):
    """There is no round to pause yet, and PAUSED offers RESUME."""
    game._pause()
    assert game.state == "launch_player_menu"


# ---- #74 the prefill must not swallow typing ------------------------------

def test_the_prefill_fills_every_slot(game):
    """The precondition for the bug, asserted so the rest is not vacuous."""
    from silphe.calibrate import default_initials

    assert default_initials("default") == "DEF"
    game._begin_initials("default")
    assert game.initials == "DEF"
    assert len(game.initials) == 3


def test_the_first_letter_typed_replaces_the_prefill(game):
    game._begin_initials("default")
    game._initials_key(Key("m"))
    assert game.initials == "M"


def test_typing_then_carries_on_appending(game):
    game._begin_initials("default")
    for ch in "mck":
        game._initials_key(Key(ch))
    assert game.initials == "MCK"


def test_the_fourth_letter_is_ignored(game):
    game._begin_initials("default")
    for ch in "mckz":
        game._initials_key(Key(ch))
    assert game.initials == "MCK"


def test_backspace_edits_the_prefill_instead_of_replacing_it(game):
    """Backspacing is touching the entry, so the next letter appends to what is
    left rather than wiping it."""
    game._begin_initials("default")
    game._initials_key(Key(keysym="BackSpace"))
    assert game.initials == "DE"
    game._initials_key(Key("x"))
    assert game.initials == "DEX"


def test_backspacing_to_empty_and_typing_a_full_set(game):
    game._begin_initials("default")
    for _ in range(3):
        game._initials_key(Key(keysym="BackSpace"))
    assert game.initials == ""
    for ch in "abc":
        game._initials_key(Key(ch))
    assert game.initials == "ABC"


def test_enter_confirms_what_was_typed_not_the_prefill(game):
    """It is the leaderboard name that matters, so assert on the board rather
    than on the screen having moved on."""
    from silphe.calibrate import leaderboard_path

    game.score = 500
    game._begin_initials("default")
    for ch in "mck":
        game._initials_key(Key(ch))
    game._initials_key(Key(keysym="Return"))
    assert game.state == "done"
    with open(leaderboard_path(), encoding="utf-8") as f:
        assert [r["name"] for r in json.load(f)] == ["MCK"]


# ---- #76 T and P must reach the initials screen ---------------------------

def test_t_and_p_are_bound_specifically_so_the_catch_all_never_sees_them(game):
    """Tk fires only the most specific binding on a bindtag, so these four keys
    never reach the `<Key>` handler. Verified by generating events against the
    same five bindings on a bare root: t/T/p/P fired only the specific binding,
    while a/z/BackSpace/Return fired the catch-all. That is why the handlers
    below have to forward.
    """
    for key in ("t", "T", "p", "P", "m", "M"):
        assert game.root.bind(key), f"{key} lost its specific binding"
    assert game.root.bind("<Key>"), "the catch-all binding is gone"


def test_t_types_a_t_on_the_initials_screen(game):
    game._begin_initials("default")
    game._switch_tool(Key("t"))
    assert game.initials == "T"


def test_p_types_a_p_on_the_initials_screen(game):
    game._begin_initials("default")
    game._switch_player(Key("p"))
    assert game.initials == "P"


def test_a_player_called_PAT_can_type_their_own_initials(game):
    game._begin_initials("default")
    game._switch_player(Key("p"))
    game._initials_key(Key("a"))
    game._switch_tool(Key("t"))
    assert game.initials == "PAT"


def test_t_still_swaps_the_tool_during_a_round(game):
    """The forwarding must not cost the key its real job."""
    game.state = "evasive"
    game.t0 = 0.0
    before = game.tool
    game._switch_tool(Key("t"))
    assert game.tool != before


def test_p_still_opens_the_player_prompt_during_a_round(game, monkeypatch):
    from silphe import calibrate

    asked = []
    monkeypatch.setattr(calibrate.simpledialog, "askstring",
                        lambda *a, **k: asked.append(True) or None)
    game.state = "idle"
    game._switch_player(Key("p"))
    assert asked, "P no longer asks for a player mid-session"


# ---- M is the third key to walk into this, and must not (#76, #85) --------

@pytest.fixture()
def unmuted(monkeypatch):
    from silphe import calibrate

    monkeypatch.setattr(calibrate, "_muted", False)
    return calibrate


def test_m_types_an_m_on_the_initials_screen(game, unmuted):
    """`m` is bound specifically, so without forwarding it would vanish from
    the initials screen exactly as T and P did. SAM and TOM need it."""
    game._begin_initials("default")
    game._toggle_mute(Key("m"))
    assert game.initials == "M"
    assert unmuted._muted is False, "typing a letter muted the game"


def test_a_player_called_SAM_can_type_their_own_initials(game, unmuted):
    game._begin_initials("default")
    game._initials_key(Key("s"))
    game._initials_key(Key("a"))
    game._toggle_mute(Key("m"))
    assert game.initials == "SAM"


def test_m_still_mutes_during_a_round(game, unmuted):
    """The forwarding must not cost the key its real job."""
    game.state = "idle"
    game._toggle_mute(Key("m"))
    assert unmuted._muted is True
    game._toggle_mute(Key("m"))
    assert unmuted._muted is False
