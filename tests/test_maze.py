"""Field-generator tests (silphe.maze) — issue #43.

The load-bearing promise is connectivity: the Andvari round drops a roach on
open ground and the player has to be able to chase it everywhere, so an
unreachable pocket is a bug that makes a round unwinnable.
"""

import random

from silphe.maze import (components, dead_ends, generate, open_cells, render,
                         tunnels)

ROWS, COLS = 15, 30           # the garden the game actually uses


def _field(seed=0, **kw):
    return generate(ROWS, COLS, rng=random.Random(seed), **kw)


def test_every_open_cell_is_reachable_from_every_other():
    """One connected component, on every seed — no islands, ever."""
    for seed in range(40):
        walls = _field(seed)
        groups = components(walls, ROWS, COLS)
        assert len(groups) == 1, f"seed {seed} left {len(groups)} disconnected pockets"
        assert groups[0] == open_cells(walls, ROWS, COLS)


def test_field_is_neither_solid_nor_empty():
    """A maze the roach can actually run: a healthy share of open ground, and
    real walls to hide behind."""
    for seed in range(40):
        walls = _field(seed)
        openness = len(open_cells(walls, ROWS, COLS)) / (ROWS * COLS)
        assert 0.25 < openness < 0.75, f"seed {seed} openness {openness:.2f}"


def test_border_is_walled():
    """The roach stays in the garden; `_neighbors` bounds-checks too, but a
    walled border is what makes the field read as a maze."""
    walls = _field(3)
    for c in range(COLS):
        assert (0, c) in walls and (ROWS - 1, c) in walls
    for r in range(ROWS):
        assert (r, 0) in walls and (r, COLS - 1) in walls


def test_has_corridors_and_junctions():
    """Not an open plain: some cells are one-way corridors, some branch."""
    walls = _field(5)
    degrees = [len([1 for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
                    if (cell[0] + dr, cell[1] + dc) not in walls])
               for cell in open_cells(walls, ROWS, COLS)]
    assert sum(1 for d in degrees if d == 2) > 20, "no corridors"
    assert sum(1 for d in degrees if d >= 3) > 5, "no junctions to choose at"


def test_dead_ends_are_exactly_the_one_way_out_cells():
    walls = _field(11)
    ends = dead_ends(walls, ROWS, COLS)
    assert ends, "a field with no crevice gives the roach nowhere to hole up"
    for cell in ends:
        ways = [(cell[0] + dr, cell[1] + dc) for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        assert len([w for w in ways if w not in walls]) == 1
    for cell in set(open_cells(walls, ROWS, COLS)) - set(ends):
        ways = [(cell[0] + dr, cell[1] + dc) for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        assert len([w for w in ways if w not in walls]) != 1


def test_braiding_trades_dead_ends_for_loops():
    """braid=0 is a perfect maze (many traps); braiding opens them up."""
    perfect = len(dead_ends(_field(7, braid=0.0), ROWS, COLS))
    braided = len(dead_ends(_field(7, braid=1.0), ROWS, COLS))
    assert perfect > braided


def test_same_seed_gives_the_same_field():
    assert _field(21) == _field(21)
    assert _field(21) != _field(22)


def test_render_round_trips_the_walls():
    walls = _field(13)
    rowstrings = render(walls, ROWS, COLS)
    assert len(rowstrings) == ROWS and all(len(s) == COLS for s in rowstrings)
    back = {(r, c) for r, s in enumerate(rowstrings)
            for c, ch in enumerate(s) if ch == "#"}
    assert back == walls


def test_tunnels_link_open_cells_far_apart():
    """A tunnel that surfaced round the corner would be a shortcut. Surfacing
    halfway across the field is what makes the player lose the roach."""
    for seed in range(20):
        walls = _field(seed)
        ground = open_cells(walls, ROWS, COLS)
        pairs = tunnels(walls, ROWS, COLS, rng=random.Random(seed), pairs=2)
        assert len(pairs) == 2, f"seed {seed} produced {len(pairs)} tunnels"
        for mouth, out in pairs:
            assert mouth in ground and out in ground
            assert abs(mouth[0] - out[0]) + abs(mouth[1] - out[1]) >= (ROWS + COLS) // 2


def test_a_cell_is_never_two_tunnel_mouths():
    walls = _field(2)
    pairs = tunnels(walls, ROWS, COLS, rng=random.Random(2), pairs=3)
    cells = [cell for pair in pairs for cell in pair]
    assert len(cells) == len(set(cells))


def test_same_seed_gives_the_same_tunnels():
    walls = _field(9)
    assert (tunnels(walls, ROWS, COLS, rng=random.Random(4))
            == tunnels(walls, ROWS, COLS, rng=random.Random(4)))


def test_tunnels_give_up_rather_than_cheat_the_span():
    """Asked for more than the field can hold, it returns fewer — never a
    pair that surfaces next door."""
    walls = _field(6)
    asked = len(open_cells(walls, ROWS, COLS)) * 2      # more pairs than there are cells
    pairs = tunnels(walls, ROWS, COLS, rng=random.Random(1), pairs=asked)
    assert 0 < len(pairs) < asked
    for mouth, out in pairs:
        assert abs(mouth[0] - out[0]) + abs(mouth[1] - out[1]) >= (ROWS + COLS) // 2
    assert tunnels(walls, ROWS, COLS, pairs=0) == []
    assert tunnels(set(), 1, 1, pairs=2) == []


def test_tiny_grids_stay_walkable_instead_of_crashing():
    """Degenerate sizes must not hand back a solid block — a roach needs
    somewhere to stand even on a grid too small to hold a maze."""
    for rows, cols in ((3, 3), (2, 9), (1, 1), (5, 4)):
        walls = generate(rows, cols, rng=random.Random(1))
        assert len(components(walls, rows, cols)) <= 1
