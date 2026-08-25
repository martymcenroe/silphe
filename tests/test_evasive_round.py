"""End-to-end Andvari round — issues #43, #44, #53.

Drives a real `Garden` on a hidden Tk root: generates the maze, runs the brood
through it, kills them, and reads back the record. These are the tests that
fail if the wiring is wrong in a way the pure-logic tests cannot see.
"""

import json
import math
import os
import time

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
    """Advance the round, forcing the clock so the roaches actually travel.

    Only the per-roach movement clock is faked. Every deadline the game sets —
    a burst, an idle pause, a meal — is real wall-clock, and this loop runs far
    faster than wall-clock, so any of them outlives the whole test. Tests that
    care about a roach moving should hold the dice with `no_dice` rather than
    hope none of those timers fires.
    """
    for _ in range(frames):
        for tg in garden.roaches:
            tg["last"] -= 0.05
        garden._roach_tick()


def records(path):
    """Every record written so far. The session file is not created until the
    first write (#78), so a file that is not there yet means nothing has been
    recorded — which is the same thing an empty file used to mean."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def on_field(tg):
    """Bring a roach up and out — neither down a hide-hole nor in the tunnels.
    A swing cannot reach either, by design, so a test that means to land one
    has to fetch the roach into the open first."""
    tg["hidden"], tg["hide_cell"] = False, None
    tg["under"], tg["tunnel_until"], tg["tunnel_exit"] = False, 0.0, None


def swat(garden, tg):
    """Kill *tg* outright with a swing it cannot dodge.

    The others are stood aside for the blow: roaches may share a cell, and a
    swing resolves against whichever is nearest, so without this the killing
    stroke could land on a bystander and the test would fail somewhere else
    entirely.
    """
    garden.tool = "swatter"
    on_field(tg)
    tg["health"] = 1
    bystanders = [(o, o["px"], o["py"]) for o in garden._live() if o is not tg]
    for other, _, _ in bystanders:
        other["px"], other["py"] = -1000.0, -1000.0
    garden._click_evasive(Click(tg["px"], tg["py"]))
    for other, px, py in bystanders:
        other["px"], other["py"] = px, py
    assert tg["dead"], "the swing did not land"


def freeze(garden):
    """Stop the brood where it stands. The attention tests are about where the
    cursor is relative to the roaches, so letting them scuttle mid-assertion
    would make the result depend on the roll of their evasion."""
    for tg in garden.roaches:
        tg["speed"] = 0.0
        on_field(tg)


def stand_apart(garden):
    """Park a frozen brood on well-separated ground.

    An attention test is about the cursor moving from one roach to another,
    which measures nothing if two of them are sitting on top of each other —
    and they may be, since roaches are free to share a cell. `prog` is zeroed
    so each one interpolates to its own cell centre and stays there.
    """
    ground = sorted(open_cells(garden.walls, garden.ROWS, garden.COLS))
    spots = [ground[0], ground[-1], ground[len(ground) // 3]]
    for tg, cell in zip(garden.roaches, spots):
        tg["cell"], tg["to"], tg["from"], tg["prog"] = cell, cell, None, 0.0
        tg["px"], tg["py"] = garden._center(*cell)
    points = [(tg["px"], tg["py"]) for tg in garden.roaches]
    for i, one in enumerate(points):
        for other in points[i + 1:]:
            assert math.hypot(one[0] - other[0], one[1] - other[1]) > \
                garden.ENGAGE_MARGIN * 4, "these two are too close to tell apart"


def settle(garden):
    """Put the brood back to an unstartled standstill.

    The round has already ticked once by the time a test body runs — the
    fixture starts it — and that tick rolls the dice with the cursor parked
    mid-canvas. Anything it set is a wall-clock deadline: an idle pause of a
    third of a second, a scare of half a second, a meal of nearly two. This
    loop runs at machine speed, so any one of them outlives the entire test
    and the roach simply never moves.
    """
    for tg in garden.roaches:
        tg["burst_until"] = tg["pause_until"] = tg["feed_until"] = 0.0
        tg["want_hide"], tg["bait_cell"] = False, None
        tg["hidden"], tg["hide_cell"] = False, None
        tg["under"], tg["tunnel_until"], tg["tunnel_exit"] = False, 0.0, None


def no_dice(monkeypatch, garden=None):
    """Hold every chance-driven urge — the random darts, the whim to hole up,
    the idle pauses, the drop into a tunnel. What is left is a roach that
    responds only to what the test puts in front of it. Pass the garden to
    `settle` it as well, which any test that needs a roach to move must do."""
    from silphe import calibrate
    monkeypatch.setattr(calibrate.random, "random", lambda: 1.0)
    if garden is not None:
        settle(garden)


def every_chance(monkeypatch, garden=None):
    """The mirror of `no_dice`: every chance-driven urge fires. Used where the
    test is about what happens when a roach takes an option, not about how
    often it takes it."""
    from silphe import calibrate
    monkeypatch.setattr(calibrate.random, "random", lambda: 0.0)
    if garden is not None:
        settle(garden)


def solo(garden):
    """One roach, so that a test about a crumb is about the crumb and not
    about which of three roaches reached it first."""
    garden.roaches = garden.roaches[:1]
    garden.engaged = None
    return garden.roaches[0]


def put(garden, tg, cell):
    """Set a roach down on *cell*, ready to decide where to go next."""
    tg["cell"], tg["to"], tg["from"], tg["prog"] = cell, cell, None, 1.0
    tg["px"], tg["py"] = garden._center(*cell)


def bait_beside(garden, tg):
    """Drop a crumb and stand the roach next to it, with nothing looming over
    it. Returns the crumb cell. Callers `settle` first — an appetite is no
    match for a scare."""
    garden.last = (-500, -500)
    garden._drop_bait(time.perf_counter())
    crumb = next(iter(garden.baits))
    put(garden, tg, garden._neighbors(crumb)[0])
    return crumb


def lace(garden, cell):
    """Poison the crumb on *cell*. Whether a crumb is laced in the first place
    is a dice roll, tested on its own; these tests are about what the poison
    then does."""
    garden.baits[cell]["poison"] = True
    for entry in garden.bait_log:
        if tuple(entry["cell"]) == cell and entry["eaten"] is None:
            entry["poison"] = True


def poison(garden, tg):
    """Feed *tg* a laced crumb and let it finish the meal. Returns once the
    roach is sick."""
    crumb = bait_beside(garden, tg)
    lace(garden, crumb)
    assert feed(garden, tg), "it never settled down to eat"
    tg["feed_until"] = time.perf_counter() - 0.01
    run(garden, frames=1)
    assert tg["sick"], "it ate the poison and shrugged it off"


def summon_gecko(garden):
    """Wind the round's clock forward until the gecko turns up."""
    garden.t0 -= garden.GECKO_AFTER + 1.0
    run(garden, frames=1)
    assert garden.gecko is not None, "the gecko never arrived"
    return garden.gecko


def stalk(garden, tg):
    """Stand the gecko and *tg* on the same cell, mid-stride, so the next tick
    resolves the catch."""
    gecko = garden.gecko
    put(garden, tg, gecko["cell"])
    gecko["to"], gecko["prog"] = gecko["cell"], 0.0
    gecko["last"] = time.perf_counter()
    garden._gecko_tick(time.perf_counter())


def feed(garden, tg, frames=40):
    """Run until the roach has its head down in a crumb."""
    for _ in range(frames):
        run(garden, frames=1)
        if tg["mode"] == "feeding":
            return True
    return False


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


def test_every_roach_runs_its_own_evasion_without_walking_through_walls(garden, monkeypatch):
    no_dice(monkeypatch, garden)                                   # no idle pauses to freeze one mid-test
    ground = open_cells(garden.walls, garden.ROWS, garden.COLS)
    visited = {tg["id"]: set() for tg in garden.roaches}
    for _ in range(120):
        run(garden, frames=1)
        for tg in garden.roaches:
            visited[tg["id"]].add(tg["cell"])
            assert tg["cell"] in ground and tg["to"] in ground, "roach left the open ground"

    for tg in garden.roaches:
        assert tg["path"], "every roach keeps its own trace"
        assert len(visited[tg["id"]]) > 1, "a roach never left its starting cell"
    # Two roaches sharing a cell for a moment is fine — they are insects, not
    # billiard balls. Sharing a whole trace would mean they move as one block.
    traces = [tuple(tg["path"]) for tg in garden.roaches]
    assert len(set(traces)) == len(traces), \
        "the roaches moved as one — they are not evading independently"


def test_the_round_only_ends_when_the_last_roach_is_down(garden, tmp_path):
    run(garden, frames=20)
    doomed = list(garden.roaches)
    for tg in doomed[:-1]:
        swat(garden, tg)
        assert garden.state == "evasive", "round ended with roaches still loose"
    assert records(garden.recorder.path) == [], \
        "nothing is recorded until the round is over"

    swat(garden, doomed[-1])
    assert garden.state == "idle"
    garden.recorder.close()
    assert len(records(garden.recorder.path)) == 1, \
        "the whole round is one record, not one per roach"


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
    stand_apart(garden)
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
    stand_apart(garden)
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
    stand_apart(garden)
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
    stand_apart(garden)
    near, far = garden.roaches[0], garden.roaches[1]
    for tg in garden.roaches:
        tg["health"] = 5
    far["px"], far["py"] = near["px"] + 400, near["py"]

    garden.tool = "swatter"
    garden._click_evasive(Click(near["px"], near["py"]))
    assert near["health"] == 4 and far["health"] == 5


def test_a_crumb_lands_on_ground_the_roaches_can_reach(garden):
    garden._drop_bait(time.perf_counter())
    assert len(garden.baits) == 1
    crumb = next(iter(garden.baits))
    assert crumb in open_cells(garden.walls, garden.ROWS, garden.COLS)
    assert crumb not in garden.hides, "a crumb down a hide-hole is no lure"
    assert garden.bait_log[0]["cell"] == list(crumb)
    assert garden.bait_log[0]["eaten"] is None and garden.bait_log[0]["by"] is None


def test_a_crumb_pulls_a_roach_off_its_run_and_puts_its_head_down(garden, monkeypatch):
    """The whole point: a baited roach and a bolting one are different things
    to chase, and the baited one holds still long enough to be hit."""
    no_dice(monkeypatch, garden)
    tg = solo(garden)
    crumb = bait_beside(garden, tg)

    run(garden, frames=1)
    assert tg["bait_cell"] == crumb, "it did not break off for the food"
    assert tg["to"] == crumb

    assert feed(garden, tg), "it never settled down to eat"
    assert tg["cell"] == crumb
    modes = [m for _, m in tg["modes"]]
    assert "baited" in modes and "feeding" in modes

    resting = (tg["px"], tg["py"])
    run(garden, frames=6)
    assert (tg["px"], tg["py"]) == resting, "a feeding roach should hold still"


def test_finishing_the_crumb_consumes_it_and_logs_who_ate_it(garden, monkeypatch):
    no_dice(monkeypatch, garden)
    tg = solo(garden)
    crumb = bait_beside(garden, tg)
    assert feed(garden, tg)

    tg["feed_until"] = time.perf_counter() - 0.01          # the last mouthful
    run(garden, frames=1)
    assert crumb not in garden.baits and tg["bait_cell"] is None
    entry = garden.bait_log[0]
    assert entry["eaten"] is not None and entry["by"] == tg["id"]


def test_a_scare_beats_an_appetite(garden, monkeypatch):
    """Threat overrides food, and the crumb it abandons is still there for
    whoever comes along next."""
    no_dice(monkeypatch, garden)
    tg = solo(garden)
    crumb = bait_beside(garden, tg)
    run(garden, frames=1)
    assert tg["bait_cell"] == crumb

    tg["burst_until"] = time.perf_counter() + 5.0          # something loomed
    run(garden, frames=1)
    assert tg["bait_cell"] is None and tg["mode"] == "fleeing"
    assert crumb in garden.baits


def test_swatting_a_roach_mid_meal_leaves_the_crumb(garden, monkeypatch):
    no_dice(monkeypatch, garden)
    tg = solo(garden)
    crumb = bait_beside(garden, tg)
    assert feed(garden, tg)

    swat(garden, tg)
    assert tg["dead"] and garden.state == "idle"
    assert crumb in garden.baits, "an interrupted meal is somebody else's dinner"


def test_the_record_carries_the_crumbs_and_each_roach_mode_timeline(garden, monkeypatch):
    no_dice(monkeypatch, garden)
    tg = solo(garden)
    bait_beside(garden, tg)
    assert feed(garden, tg)
    swat(garden, tg)

    garden.recorder.close()
    row = json.loads(open(garden.recorder.path, encoding="utf-8").readline())
    assert row["bait"] and row["bait"][0]["cell"]
    modes = [m for _, m in row["roaches"][0]["modes"]]
    assert "baited" in modes and "feeding" in modes, \
        "analysis has to be able to segment the chase by the roach's mode"
    assert row["schema_version"] == 1


def test_tunnel_mouths_are_paired_and_keep_their_own_cells(garden):
    mouths = garden.tunnels
    assert len(mouths) == garden.TUNNEL_PAIRS * 2
    ground = open_cells(garden.walls, garden.ROWS, garden.COLS)
    span = (garden.ROWS + garden.COLS) // 2
    for mouth, far in mouths.items():
        assert mouths[far] == mouth, "a tunnel must run both ways"
        assert mouth in ground and mouth not in garden.hides
        assert abs(mouth[0] - far[0]) + abs(mouth[1] - far[1]) >= span, \
            "a tunnel that surfaces next door is just a shortcut"
    assert not (set(mouths) & {tg["cell"] for tg in garden.roaches}), \
        "nothing starts standing on a tunnel mouth"


def test_a_bolting_roach_drops_into_a_tunnel(garden, monkeypatch):
    every_chance(monkeypatch, garden)
    tg = solo(garden)
    mouth = next(iter(garden.tunnels))
    put(garden, tg, mouth)
    tg["burst_until"] = time.perf_counter() + 5.0          # bolting over the hole

    run(garden, frames=1)
    assert tg["under"] and tg["tunnel_exit"] == garden.tunnels[mouth]
    assert tg["mode"] == "tunnelling", "a tunnel is not a hide-hole"
    assert tg["tunnels"][-1]["from"] == list(mouth)
    assert tg["tunnels"][-1]["out"] is None, "still down there"
    # The trip has to last long enough to actually lose it.
    assert 0.4 <= garden.TUNNEL_SECS[0] <= garden.TUNNEL_SECS[1]
    assert tg["tunnel_until"] - time.perf_counter() >= garden.TUNNEL_SECS[0] - 0.1


def test_a_roach_in_the_tunnels_is_off_the_field(garden, monkeypatch):
    """It cannot be seen and it cannot be hit — that is what makes the player
    have to find it again."""
    no_dice(monkeypatch, garden)
    tg = solo(garden)
    put(garden, tg, next(iter(garden.tunnels)))
    garden._dive(tg, time.perf_counter())
    tg["tunnel_until"] = time.perf_counter() + 60.0        # a long trip
    run(garden, frames=3)

    assert tg["mode"] == "tunnelling"
    assert not garden.canvas.find_withtag("roach"), "an underground roach is drawn"
    before = tg["health"]
    garden.tool = "swatter"
    garden._click_evasive(Click(tg["px"], tg["py"]))
    assert tg["health"] == before, "a swat reached into the tunnels"


def test_it_surfaces_at_the_far_end_already_running(garden, monkeypatch):
    no_dice(monkeypatch, garden)
    tg = solo(garden)
    mouth = next(iter(garden.tunnels))
    far = garden.tunnels[mouth]
    put(garden, tg, mouth)
    garden._dive(tg, time.perf_counter())

    tg["tunnel_until"] = time.perf_counter() - 0.01        # the trip is over
    run(garden, frames=1)
    assert not tg["under"] and tg["cell"] == far
    assert (tg["px"], tg["py"]) == garden._center(*far)
    assert tg["burst_until"] > time.perf_counter(), "it should come out at a bolt"


def test_the_trip_records_both_ends_and_both_timestamps(garden, monkeypatch):
    """The disappear/reappear stamps are what let analysis find the
    re-acquisition in the cursor trace."""
    no_dice(monkeypatch, garden)
    tg = solo(garden)
    mouth = next(iter(garden.tunnels))
    far = garden.tunnels[mouth]
    put(garden, tg, mouth)
    garden._dive(tg, time.perf_counter())
    tg["tunnel_until"] = time.perf_counter() - 0.01
    run(garden, frames=1)

    trip = tg["tunnels"][-1]
    assert trip["from"] == list(mouth) and trip["to"] == list(far)
    # Not strictly greater: this test drives both ends inside one tenth of a
    # millisecond. How long a real trip lasts is TUNNEL_SECS, pinned below.
    assert trip["out"] >= trip["in"] >= 0, "it must surface no sooner than it dives"

    swat(garden, tg)
    garden.recorder.close()
    row = json.loads(open(garden.recorder.path, encoding="utf-8").readline())
    assert row["roaches"][0]["tunnels"] == [trip]
    assert "tunnelling" in [m for _, m in row["roaches"][0]["modes"]]


def test_whether_a_crumb_is_laced_follows_the_odds(garden, monkeypatch):
    every_chance(monkeypatch, garden)
    garden._drop_bait(time.perf_counter())
    assert all(food["poison"] for food in garden.baits.values())
    assert garden.bait_log[-1]["poison"] is True

    garden.baits.clear()
    no_dice(monkeypatch, garden)
    garden._drop_bait(time.perf_counter())
    assert not any(food["poison"] for food in garden.baits.values())
    assert garden.bait_log[-1]["poison"] is False


def test_a_laced_crumb_sickens_the_roach_that_finishes_it(garden, monkeypatch):
    no_dice(monkeypatch, garden)
    tg = solo(garden)
    crumb = bait_beside(garden, tg)
    lace(garden, crumb)
    assert feed(garden, tg)

    healthy = tg["speed"]
    tg["feed_until"] = time.perf_counter() - 0.01          # the last mouthful
    run(garden, frames=1)
    assert tg["sick"] and tg["sickened_at"] is not None
    assert tg["speed"] < healthy, "the poison should slow it"
    assert tg["dies_at"] > time.perf_counter(), "it dies on a clock, not on the spot"
    assert not tg["dead"]


def test_a_poisoned_roach_dies_where_it_falls_and_leaves_a_laced_corpse(garden, monkeypatch):
    no_dice(monkeypatch, garden)
    tg = solo(garden)
    poison(garden, tg)

    fell = tg["cell"]
    tg["dies_at"] = time.perf_counter() - 0.01
    run(garden, frames=1)
    assert tg["dead"] and tg["died"]["cause"] == "poison"
    assert fell in garden.baits, "it should leave a body"
    assert garden.baits[fell]["kind"] == "corpse" and garden.baits[fell]["poison"]


def test_the_corpse_carries_the_poison_to_whatever_eats_it(garden, monkeypatch):
    """The Advion domino: the second roach never touched the bait."""
    no_dice(monkeypatch, garden)
    garden.last = (-500, -500)
    first, second = garden.roaches[0], garden.roaches[1]

    ground = sorted(open_cells(garden.walls, garden.ROWS, garden.COLS))
    fell = next(rc for rc in ground if rc not in garden.hides
                and rc not in garden.tunnels and garden._neighbors(rc))
    put(garden, first, fell)
    garden._roach_down(first, time.perf_counter(), "poison")
    assert garden.baits[fell]["kind"] == "corpse"

    put(garden, second, garden._neighbors(fell)[0])
    assert feed(garden, second), "it never settled down to the corpse"
    second["feed_until"] = time.perf_counter() - 0.01
    run(garden, frames=1)
    assert second["sick"], "the domino did not fall"
    assert fell not in garden.baits, "the corpse should be eaten"


def test_the_gecko_waits_before_it_shows_up(garden, monkeypatch):
    no_dice(monkeypatch, garden)
    run(garden, frames=40)
    assert garden.gecko is None, "the round starts as the player's alone"

    gecko = summon_gecko(garden)
    assert gecko["cell"] not in garden.walls
    assert gecko["arrived"] >= garden.GECKO_AFTER


def test_the_gecko_takes_a_roach_but_the_player_gets_nothing_for_it(garden, monkeypatch):
    no_dice(monkeypatch, garden)
    tg = solo(garden)
    gecko = summon_gecko(garden)
    stalk(garden, tg)

    assert tg["dead"] and tg["died"]["cause"] == "gecko"
    assert [kill[1] for kill in gecko["kills"]] == [tg["id"]]
    assert garden.hit_n == 0, "the player never landed a blow"

    run(garden, frames=1)                                  # the round notices it is over
    garden.recorder.close()
    row = json.loads(open(garden.recorder.path, encoding="utf-8").readline())
    assert row["player_hits"] == 0 and row["score"] == 0, "the gecko does not score for you"
    assert row["hits"] == tg["hp0"], "what it would have taken is still recorded"
    assert row["roaches"][0]["died"]["cause"] == "gecko"
    assert row["gecko"]["path"] and row["gecko"]["kills"]


def test_the_gecko_cannot_reach_down_a_hole(garden, monkeypatch):
    no_dice(monkeypatch, garden)
    tg = solo(garden)
    summon_gecko(garden)
    tg["hidden"], tg["hide_cell"] = True, garden.gecko["cell"]
    stalk(garden, tg)
    assert not tg["dead"], "it got one out of a hide-hole"

    tg["hidden"], tg["under"] = False, True
    stalk(garden, tg)
    assert not tg["dead"], "it got one out of the tunnels"


def test_a_roach_runs_from_whichever_danger_is_nearer(garden):
    tg = garden.roaches[0]
    assert garden._threat(-500.0, -500.0, tg) == (-500.0, -500.0), "no gecko, no question"

    garden.gecko = {"px": tg["px"] + 10.0, "py": tg["py"]}
    assert garden._threat(-500.0, -500.0, tg) == (tg["px"] + 10.0, tg["py"])

    garden.gecko = {"px": tg["px"] + 900.0, "py": tg["py"]}
    assert garden._threat(tg["px"] + 5.0, tg["py"], tg) == (tg["px"] + 5.0, tg["py"])


def test_a_swatted_roach_is_recorded_as_the_players_work(garden, monkeypatch):
    no_dice(monkeypatch, garden)
    tg = solo(garden)
    swat(garden, tg)
    assert tg["died"]["cause"] == "swat"

    garden.recorder.close()
    row = json.loads(open(garden.recorder.path, encoding="utf-8").readline())
    assert row["player_hits"] == garden.hit_n > 0
    assert row["score"] > 0
    assert row["gecko"] is None, "no gecko showed up in this round"


def test_the_whole_ecology_runs_without_falling_over(garden):
    """Brood, crumbs, poison, corpses, hide-holes, tunnels and the gecko, all
    at once, with the dice left alone. Nothing here is stubbed — this is the
    guard that the pieces do not break each other."""
    summon_gecko(garden)
    ground = open_cells(garden.walls, garden.ROWS, garden.COLS)

    for _ in range(300):
        garden.next_bait = 0.0                             # keep the food coming
        if garden.gecko is not None:
            garden.gecko["last"] -= 0.05                   # and the gecko hunting
        run(garden, frames=1)
        if garden.state != "evasive":
            break
        for tg in garden._live():
            assert tg["cell"] in ground and tg["to"] in ground, "a roach left the field"
        if garden.gecko is not None:
            assert garden.gecko["cell"] in ground, "the gecko walked into a wall"
        for cell in garden.baits:
            assert cell in ground, "food landed inside a wall"

    if garden.state == "idle":                             # the gecko cleaned up
        garden.recorder.close()
        row = json.loads(open(garden.recorder.path, encoding="utf-8").readline())
        assert row["kind"] == "evasive" and row["schema_version"] == 1
        assert all(tg["died"] for tg in row["roaches"]), "a round ends with none left"


def test_next_round_puts_the_garden_back(garden):
    """The maze and the brood belong to the roach round; acquire/track/hold get
    the garden they were planted on."""
    garden._restore()
    assert garden.walls == set() and garden.hides == set() and garden.roaches == []
    painted = {rc: garden.canvas.itemcget(item, "fill")
               for rc, item in garden.cells.items()}
    assert painted == garden.base
