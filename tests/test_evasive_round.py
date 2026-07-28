"""End-to-end Andvari round — issues #43, #44, #53.

Drives a real `Garden` on a hidden Tk root: generates the maze, runs the brood
through it, kills them, and reads back the record. These are the tests that
fail if the wiring is wrong in a way the pure-logic tests cannot see.
"""

import json

import pytest

from silphe.maze import components, open_cells, render

tk = pytest.importorskip("tkinter")


class Click:
    """Stands in for a Tk mouse event."""

    def __init__(self, x, y):
        self.x, self.y = int(x), int(y)


@pytest.fixture(scope="module")
def root():
    """One hidden Tk root for the whole module. Tearing a root down and
    building another in the same process leaves Tcl unable to find its own
    library, so every round here shares this one."""
    try:
        win = tk.Tk()
    except tk.TclError as exc:                                  # no display
        pytest.skip(f"no Tk display: {exc}")
    win.withdraw()
    yield win
    win.destroy()


def _round(root, tmp_path, monkeypatch, difficulty="easy"):
    from silphe import calibrate

    monkeypatch.setenv("SILPHE_RECORDINGS", str(tmp_path))
    monkeypatch.setattr(calibrate, "ska", lambda event: None)   # tests stay quiet
    game = calibrate.Garden(root, device="mouse", player=None, difficulty=None)
    game.plan, game.i = ["evasive"], 0
    game._choose_difficulty(difficulty)
    return game


@pytest.fixture()
def garden(root, tmp_path, monkeypatch):
    """An evasive round, mid-flight, recording into *tmp_path*."""
    game = _round(root, tmp_path, monkeypatch)
    try:
        yield game
    finally:
        game.recorder.close()
        game.canvas.destroy()


def run(garden, frames=60):
    """Advance the round, forcing the clock so the roaches actually travel."""
    for _ in range(frames):
        for tg in garden.roaches:
            tg["last"] -= 0.05
        garden._roach_tick()


def swat(garden, tg):
    """Kill *tg* outright with a swing it cannot dodge."""
    garden.tool = "swatter"
    tg["hidden"], tg["health"] = False, 1
    garden._click_evasive(Click(tg["px"], tg["py"]))


def freeze(garden):
    """Stop the brood where it stands. The attention tests are about where the
    cursor is relative to the roaches, so letting them scuttle mid-assertion
    would make the result depend on the roll of their evasion."""
    for tg in garden.roaches:
        tg["speed"], tg["hidden"] = 0.0, False


def test_round_opens_on_a_connected_maze_with_a_brood(garden):
    walls = garden.walls
    assert walls, "the round must reconfigure the garden into a maze"
    assert len(components(walls, garden.ROWS, garden.COLS)) == 1
    ground = open_cells(walls, garden.ROWS, garden.COLS)
    assert len(garden.roaches) == garden.diff["roaches"] > 1
    assert len({tg["id"] for tg in garden.roaches}) == len(garden.roaches)
    assert len({tg["cell"] for tg in garden.roaches}) == len(garden.roaches), \
        "roaches must not be stacked on one cell"
    for tg in garden.roaches:
        assert tg["cell"] in ground, "roach must start on open ground"
    assert garden.hides and garden.hides <= ground, "hide-holes must be reachable"


def test_every_roach_runs_its_own_evasion_without_walking_through_walls(garden):
    ground = open_cells(garden.walls, garden.ROWS, garden.COLS)
    seen = {tg["id"]: set() for tg in garden.roaches}
    run(garden, frames=120)
    for tg in garden.roaches:
        seen[tg["id"]].add(tg["cell"])
        assert tg["cell"] in ground and tg["to"] in ground, "roach left the open ground"
        assert tg["path"], "every roach keeps its own trace"
    assert len({tuple(tg["path"][-1]) for tg in garden.roaches}) > 1, \
        "the roaches moved as one — they are not evading independently"


def test_the_round_only_ends_when_the_last_roach_is_down(garden, tmp_path):
    run(garden, frames=20)
    doomed = list(garden.roaches)
    for tg in doomed[:-1]:
        swat(garden, tg)
        assert garden.state == "evasive", "round ended with roaches still loose"
    assert not any(line.strip() for line
                   in open(garden.recorder.path, encoding="utf-8")), \
        "nothing is recorded until the round is over"

    swat(garden, doomed[-1])
    assert garden.state == "idle"
    garden.recorder.close()
    rows = [json.loads(x) for x in open(garden.recorder.path, encoding="utf-8") if x.strip()]
    assert len(rows) == 1, "the whole round is one record, not one per roach"


def test_the_record_carries_every_roach_and_the_maze(garden):
    run(garden, frames=40)
    expected_maze = render(garden.walls, garden.ROWS, garden.COLS)
    expected_hits = sum(tg["hp0"] for tg in garden.roaches)
    for tg in list(garden.roaches):
        swat(garden, tg)

    garden.recorder.close()
    row = json.loads(open(garden.recorder.path, encoding="utf-8").readline())
    assert row["kind"] == "evasive"
    assert row["maze"] == expected_maze
    assert row["hits"] == expected_hits, "every roach's health counts toward the score"
    assert row["score"] > 0
    assert len(row["roaches"]) == len(garden.roaches)
    for entry, tg in zip(row["roaches"], garden.roaches):
        assert entry["id"] == tg["id"] and entry["hp0"] == tg["hp0"]
        assert entry["path"], "each roach's own trace must survive"
    assert row["path"], "the pursued trace must survive"
    assert row["schema_version"] == 1, "added fields are not a breaking change"


def test_path_follows_whichever_roach_the_player_is_chasing(garden):
    """`path` is what pursuit lag is measured against, so it has to track the
    player's attention — not some roach nobody was looking at."""
    run(garden, frames=10)
    freeze(garden)
    first, second = garden.roaches[0], garden.roaches[1]

    garden.last = (first["px"], first["py"])               # cursor sits on the first
    run(garden, frames=5)
    assert garden.engaged == first["id"]
    assert garden.path[-1][1:] == (round(first["px"], 1), round(first["py"], 1))

    garden.last = (second["px"], second["py"])             # attention crosses over
    run(garden, frames=5)
    assert garden.engaged == second["id"]
    assert garden.path[-1][1:] == (round(second["px"], 1), round(second["py"], 1))


def test_target_switches_are_recorded_but_not_flapped(garden):
    run(garden, frames=10)
    freeze(garden)
    first, second = garden.roaches[0], garden.roaches[1]

    garden.last = (first["px"], first["py"])
    run(garden, frames=3)
    garden.last = (second["px"], second["py"])
    run(garden, frames=3)
    ids = [switch[1] for switch in garden.target_switches]
    assert first["id"] in ids and second["id"] in ids
    assert all(isinstance(t, float) and t >= 0 for t, _ in garden.target_switches)

    # Parked midway between two roaches, the record must not chatter.
    settled = len(garden.target_switches)
    garden.last = ((first["px"] + second["px"]) / 2, (first["py"] + second["py"]) / 2)
    run(garden, frames=15)
    assert len(garden.target_switches) - settled <= 1, "the cursor drifting is not a decision"


def test_killing_the_engaged_roach_re_homes_onto_what_is_left(garden):
    run(garden, frames=10)
    freeze(garden)
    first = garden.roaches[0]
    garden.last = (first["px"], first["py"])
    run(garden, frames=3)
    assert garden.engaged == first["id"]

    swat(garden, first)
    run(garden, frames=3)
    assert garden.engaged is not None and garden.engaged != first["id"], \
        "attention must move to a live roach once the quarry is dead"
    assert garden.target_switches[-1][1] == garden.engaged


def test_a_burnt_out_hide_hole_goes_back_to_the_maze_not_the_garden(garden):
    """#53: the round repaints the field, so a hole restored from the garden
    scatter can leave a green cell sitting in an open corridor."""
    run(garden, frames=10)
    tg = garden.roaches[0]
    hole = sorted(garden.hides)[0]
    tg["hidden"], tg["hide_cell"], tg["cell"] = True, hole, hole

    garden.tool = "pick"
    x0, y0 = garden._cell_xy(*hole)
    garden._click_evasive(Click(x0 + garden.CELL / 2, y0 + garden.CELL / 2))

    assert hole not in garden.hides, "a stabbed hole is burnt for the round"
    assert garden.canvas.itemcget(garden.cells[hole], "fill") == garden.maze_base[hole]
    assert garden.maze_base[hole] == "#161b22", "a hide-hole sits on open ground"


def test_the_swatter_lands_on_the_nearest_roach(garden):
    run(garden, frames=20)
    freeze(garden)
    near, far = garden.roaches[0], garden.roaches[1]
    for tg in garden.roaches:
        tg["health"] = 5
    far["px"], far["py"] = near["px"] + 400, near["py"]

    garden.tool = "swatter"
    garden._click_evasive(Click(near["px"], near["py"]))
    assert near["health"] == 4 and far["health"] == 5


def test_next_round_puts_the_garden_back(garden):
    """The maze and the brood belong to the roach round; acquire/track/hold get
    the garden they were planted on."""
    garden._restore()
    assert garden.walls == set() and garden.hides == set() and garden.roaches == []
    painted = {rc: garden.canvas.itemcget(item, "fill")
               for rc, item in garden.cells.items()}
    assert painted == garden.base
