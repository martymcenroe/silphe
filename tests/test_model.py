"""Tests for silphe.model — the cross-platform path generator."""

import random
import statistics

from silphe.model import DEFAULT_PROFILE, TREMOR_PROFILE, MovementModel


def test_plan_ends_near_target():
    wp = MovementModel(rng=random.Random(0)).plan(0, 0, 400, 250)
    x, y, _ = wp[-1]
    assert abs(x - 400) < 8 and abs(y - 250) < 8


def test_plan_is_deterministic_with_seed():
    a = MovementModel(rng=random.Random(42)).plan(10, 10, 300, 200)
    b = MovementModel(rng=random.Random(42)).plan(10, 10, 300, 200)
    assert a == b


def test_plan_varies_without_seed():
    a = MovementModel().plan(0, 0, 500, 300)
    b = MovementModel().plan(0, 0, 500, 300)
    assert a != b   # fresh randomness every call — never the same path twice


def test_waypoints_well_formed():
    wp = MovementModel(rng=random.Random(1)).plan(0, 0, 200, 200)
    assert len(wp) > 10
    assert all(len(p) == 3 for p in wp)
    assert all(dt >= 0 for _, _, dt in wp)   # time only moves forward


def test_overshoot_goes_past_the_target():
    # a ballistic launch overshoots: the path must at some point pass the target
    wp = MovementModel(rng=random.Random(3)).plan(0, 0, 300, 0)
    assert max(x for x, _, _ in wp) > 300


def test_heavier_profile_has_wider_dwell():
    def dwell_spread(profile):
        wp = MovementModel(profile=profile, rng=random.Random(7)).plan(0, 0, 100, 100)
        return statistics.pstdev([x for x, _, _ in wp[-30:]])

    assert dwell_spread(TREMOR_PROFILE) > dwell_spread(DEFAULT_PROFILE)


def test_profile_override_is_partial():
    # overriding one knob keeps the rest of DEFAULT_PROFILE
    m = MovementModel(profile={"speed": 0.5})
    assert m.p["speed"] == 0.5
    assert m.p["tremor_hz"] == DEFAULT_PROFILE["tremor_hz"]
