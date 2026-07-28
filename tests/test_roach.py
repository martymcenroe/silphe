"""Roach navigation tests (Garden's maze pathing) — issue #43.

The movement helpers only need the field and the cell geometry, so they are
exercised here bound to a bare stand-in rather than a live Tk window: this is
the real `Garden` code, running headless.
"""

import random

from silphe.calibrate import Garden
from silphe.maze import generate, open_cells


class Field:
    """The slice of Garden the roach's navigation actually touches."""

    def __init__(self, walls, rows=15, cols=30):
        self.walls, self.ROWS, self.COLS = walls, rows, cols

    def _center(self, r, c):
        return c * 36 + 15.0, r * 36 + 15.0

    _neighbors = Garden._neighbors
    _wander = Garden._wander
    _toward = Garden._toward


def corridor():
    """A 3x5 grid whose only open ground is the corridor (1,1)-(1,2)-(1,3)."""
    walls = {(r, c) for r in range(3) for c in range(5)}
    walls -= {(1, 1), (1, 2), (1, 3)}
    return Field(walls, rows=3, cols=5)


def test_neighbours_are_open_and_in_bounds():
    field = corridor()
    assert sorted(field._neighbors((1, 2))) == [(1, 1), (1, 3)]
    assert field._neighbors((1, 1)) == [(1, 2)]           # wall on three sides


def test_ambling_roach_keeps_going_instead_of_dithering():
    """Mid-corridor it never turns back — that jitter is what made the old
    open-field wander read as noise."""
    field = corridor()
    for _ in range(25):
        assert field._wander((1, 2), 0, 0, False, came_from=(1, 1)) == (1, 3)
        assert field._wander((1, 2), 0, 0, False, came_from=(1, 3)) == (1, 1)


def test_ambling_roach_turns_around_at_a_dead_end():
    field = corridor()
    assert field._wander((1, 3), 0, 0, False, came_from=(1, 2)) == (1, 2)


def test_a_poisoned_roach_staggers_instead_of_running_the_corridor():
    """Momentum is the first thing the poison takes: it stops holding a line
    and reels between both ends of the corridor."""
    field = corridor()
    picks = {field._wander((1, 2), 0, 0, False, came_from=(1, 1), sick=True)
             for _ in range(40)}
    assert picks == {(1, 1), (1, 3)}, "a dying roach should lose the thread"


def test_bolting_roach_doubles_back_when_you_cut_it_off():
    """Fleeing overrides momentum: with the cursor ahead of it, the roach
    reverses past you rather than running into the swatter."""
    field = corridor()
    ahead_x, ahead_y = field._center(1, 3)
    assert field._wander((1, 2), ahead_x, ahead_y, True, came_from=(1, 1)) == (1, 1)


def test_toward_walks_the_corridors_all_the_way_to_the_goal():
    """Step-by-step `_toward` must actually arrive, by a shortest route, on a
    real generated maze — greedy manhattan steps stall in the blind alleys."""
    walls = generate(15, 30, rng=random.Random(4))
    field = Field(walls)
    cells = sorted(open_cells(walls, 15, 30))
    start, goal = cells[0], cells[-1]

    hops, at = 0, start
    while at != goal:
        nxt = field._toward(at, goal)
        assert nxt is not None, "connected field must always offer a next step"
        assert nxt in field._neighbors(at), "stepped through a wall"
        at, hops = nxt, hops + 1
        assert hops < 15 * 30, "walked in circles instead of arriving"
    assert hops == _shortest(field, start, goal)


def test_toward_gives_up_on_an_unreachable_goal():
    """An island can't happen in a generated field, but the caller falls back
    to wandering if it ever does."""
    walls = {(r, c) for r in range(5) for c in range(5)} - {(1, 1), (3, 3)}
    field = Field(walls, rows=5, cols=5)
    assert field._toward((1, 1), (3, 3)) is None
    assert field._toward((1, 1), (1, 1)) is None
    assert field._toward((1, 1), None) is None


def _shortest(field, start, goal):
    seen, edge, steps = {start}, [start], 0
    while edge:
        if goal in seen:
            return steps
        nxt = [n for cell in edge for n in field._neighbors(cell) if n not in seen]
        seen.update(nxt)
        edge, steps = nxt, steps + 1
    raise AssertionError("goal unreachable")
