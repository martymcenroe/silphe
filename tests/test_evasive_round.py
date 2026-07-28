"""End-to-end Andvari round — issue #43.

Drives a real `Garden` on a hidden Tk root: generates the maze, runs the roach
through it, kills it, and reads back the record. This is the test that fails
if the maze wiring is wrong in a way the pure-logic tests cannot see.
"""

import json
import os

import pytest

from silphe.maze import components, open_cells

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


@pytest.fixture()
def garden(root, tmp_path, monkeypatch):
    """An evasive round, mid-flight, recording into *tmp_path*."""
    from silphe import calibrate

    monkeypatch.setenv("SILPHE_RECORDINGS", str(tmp_path))
    monkeypatch.setattr(calibrate, "ska", lambda event: None)   # tests stay quiet

    game = calibrate.Garden(root, device="mouse", player=None, difficulty=None)
    game.plan, game.i = ["evasive"], 0
    game._choose_difficulty("easy")
    try:
        yield game
    finally:
        game.recorder.close()
        game.canvas.destroy()


def test_round_opens_on_a_connected_maze(garden):
    walls = garden.walls
    assert walls, "the round must reconfigure the garden into a maze"
    assert len(components(walls, garden.ROWS, garden.COLS)) == 1
    ground = open_cells(walls, garden.ROWS, garden.COLS)
    assert garden.target["cell"] in ground, "roach must start on open ground"
    assert garden.hides and garden.hides <= ground, "hide-holes must be reachable"


def test_roach_runs_the_corridors_without_walking_through_walls(garden):
    ground = open_cells(garden.walls, garden.ROWS, garden.COLS)
    visited = set()
    for _ in range(120):
        garden.target["last"] -= 0.05                           # advance the clock
        garden._roach_tick()
        visited.add(garden.target["cell"])
        assert garden.target["cell"] in ground, "roach left the open ground"
        assert garden.target["to"] in ground, "roach aimed into a wall"
    assert len(visited) > 3, "roach never left its starting cell"


def test_squashing_the_roach_records_the_round_and_its_maze(garden):
    from silphe.maze import render

    for _ in range(20):                                         # let it move off its start
        garden.target["last"] -= 0.05
        garden._roach_tick()

    roach = garden.target
    roach["hidden"], roach["health"] = False, 1                 # one swat from dead
    expected = render(garden.walls, garden.ROWS, garden.COLS)
    garden._click(Click(roach["px"], roach["py"]))

    garden.recorder.close()
    rows = [json.loads(line) for line in
            open(garden.recorder.path, encoding="utf-8") if line.strip()]
    assert len(rows) == 1, "a squashed roach writes exactly one round"
    row = rows[0]
    assert row["kind"] == "evasive"
    assert row["maze"] == expected, "the round's own field must ride on the record"
    assert row["path"], "the roach's trace must survive"
    assert row["schema_version"] == 1, "an added field is not a breaking change"
    assert os.path.exists(garden.recorder.path)


def test_next_round_puts_the_garden_back(garden):
    """The maze belongs to the roach round; acquire/track/hold get the garden
    they were planted on."""
    garden._restore()
    assert garden.walls == set() and garden.hides == set()
    painted = {rc: garden.canvas.itemcget(item, "fill")
               for rc, item in garden.cells.items()}
    assert painted == garden.base
