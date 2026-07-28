"""silphe.maze — the Andvari field generator.

Pure stdlib and free of tkinter, because the field layout is game-independent
logic: it tests headlessly and any build in the silphe family can lay out the
same kind of ground.

A field is a set of *wall* cells on a ``rows × cols`` grid; every cell not in
that set is open ground the roach can occupy. The generator carves a
recursive-backtracker maze on the odd-indexed lattice, braids some of its dead
ends into loops so a chase can flow, opens a few chambers so the round is not
uniformly one-cell corridor, and finally seals any pocket it cannot reach — so
the caller is guaranteed that every open cell is reachable from every other.

    walls = generate(15, 30)
    holes = dead_ends(walls, 15, 30)      # the crevices worth hiding in
"""

from __future__ import annotations

import random

__all__ = ["generate", "dead_ends", "open_cells", "components", "render"]

_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def open_cells(walls: set, rows: int, cols: int) -> set:
    """Every cell of the grid that is not a wall."""
    return {(r, c) for r in range(rows) for c in range(cols)} - set(walls)


def _open_neighbours(walls: set, cell, rows: int, cols: int) -> list:
    r, c = cell
    out = []
    for dr, dc in _STEPS:
        nb = (r + dr, c + dc)
        if 0 <= nb[0] < rows and 0 <= nb[1] < cols and nb not in walls:
            out.append(nb)
    return out


def components(walls: set, rows: int, cols: int) -> list:
    """The connected groups of open cells, largest first. A well-formed field
    has exactly one."""
    remaining = open_cells(walls, rows, cols)
    seen, groups = set(), []
    for cell in sorted(remaining):
        if cell in seen:
            continue
        group, stack = {cell}, [cell]
        seen.add(cell)
        while stack:
            for nb in _open_neighbours(walls, stack.pop(), rows, cols):
                if nb not in seen:
                    seen.add(nb)
                    group.add(nb)
                    stack.append(nb)
        groups.append(group)
    return sorted(groups, key=len, reverse=True)


def dead_ends(walls: set, rows: int, cols: int) -> list:
    """Open cells with exactly one way out — the blind alleys the roach gets
    cornered in, and the natural homes for its hide-holes."""
    return sorted(cell for cell in open_cells(walls, rows, cols)
                  if len(_open_neighbours(walls, cell, rows, cols)) == 1)


def render(walls: set, rows: int, cols: int) -> list:
    """The field as one string per row, ``#`` for wall and ``.`` for open.
    Compact enough to store on a recording, and readable in a diff."""
    return ["".join("#" if (r, c) in walls else "." for c in range(cols))
            for r in range(rows)]


def generate(rows: int, cols: int, rng=None, braid: float = 0.45,
             chambers: int = 3) -> set:
    """Carve a field and return its wall cells.

    *braid* is the share of dead ends opened into a loop — 0 leaves a perfect
    maze (every dead end a trap), 1 leaves almost none. *chambers* is how many
    small open rooms to clear, giving the round somewhere to read as open
    field rather than corridor. Pass *rng* (a :class:`random.Random`) for a
    reproducible field.
    """
    rng = rng or random
    walls = {(r, c) for r in range(rows) for c in range(cols)}

    node_rows = list(range(1, rows - 1, 2))
    node_cols = list(range(1, cols - 1, 2))
    if not node_rows or not node_cols:
        # Too small to hold a maze; leave the interior open rather than
        # handing back a solid block the roach cannot stand on.
        return {(r, c) for r in range(rows) for c in range(cols)
                if r in (0, rows - 1) or c in (0, cols - 1)}
    nodes = {(r, c) for r in node_rows for c in node_cols}

    # --- recursive backtracker over the lattice --------------------------
    start = (rng.choice(node_rows), rng.choice(node_cols))
    walls.discard(start)
    seen, stack = {start}, [start]
    while stack:
        r, c = stack[-1]
        onward = [(r + dr, c + dc) for dr, dc in ((2, 0), (-2, 0), (0, 2), (0, -2))
                  if (r + dr, c + dc) in nodes and (r + dr, c + dc) not in seen]
        if not onward:
            stack.pop()
            continue
        nxt = rng.choice(onward)
        walls.discard(((r + nxt[0]) // 2, (c + nxt[1]) // 2))   # the wall between
        walls.discard(nxt)
        seen.add(nxt)
        stack.append(nxt)

    # --- braid: loops so the chase flows ---------------------------------
    # A perfect maze corners the roach constantly, which makes the round a
    # series of trivial kills. Opening a share of the dead ends gives it
    # somewhere to run; the ones left closed stay as crevices.
    for cell in [n for n in sorted(nodes)
                 if len(_open_neighbours(walls, n, rows, cols)) <= 1]:
        if rng.random() >= braid:
            continue
        blocked = [(cell[0] + dr // 2, cell[1] + dc // 2)
                   for dr, dc in ((2, 0), (-2, 0), (0, 2), (0, -2))
                   if (cell[0] + dr, cell[1] + dc) in nodes
                   and (cell[0] + dr // 2, cell[1] + dc // 2) in walls]
        if blocked:
            walls.discard(rng.choice(blocked))

    # --- chambers: open ground to contrast against the corridors ---------
    for _ in range(max(0, chambers)):
        h, w = rng.randint(2, 3), rng.randint(3, 5)
        if rows - h - 1 <= 1 or cols - w - 1 <= 1:
            break
        r0 = rng.randrange(1, rows - h - 1)
        c0 = rng.randrange(1, cols - w - 1)
        for r in range(r0, r0 + h):
            for c in range(c0, c0 + w):
                walls.discard((r, c))

    _seal_unreachable(walls, rows, cols)
    return walls


def _seal_unreachable(walls: set, rows: int, cols: int) -> None:
    """Wall off every open pocket outside the main field, in place, so the
    caller's guarantee holds: any open cell can be walked to from any other.
    A roach dropped in an island would be unkillable."""
    groups = components(walls, rows, cols)
    for group in groups[1:]:
        walls |= group
