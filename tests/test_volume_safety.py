"""The level must not be able to hurt — issue #92.

The stock default was peak 0.35 of full scale, chosen on speakers. On earbuds
it was loud enough to hurt, and there was no way to turn it down mid-round:
mute was all or nothing, and `--volume` only exists at launch.
"""

import io
import struct
import wave

import pytest

from silphe import calibrate
from silphe.calibrate import (SKA_RIFFS, VOLUME, VOLUME_CEILING, VOLUME_STEP,
                              nudge_volume, render_riff, set_muted, set_volume)


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("SILPHE_RECORDINGS", str(tmp_path / "recordings"))
    monkeypatch.setattr(calibrate, "_RIFF_WAVS", {})
    monkeypatch.setattr(calibrate, "_muted", False)
    monkeypatch.setattr(calibrate, "_volume", VOLUME)


def peak(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        raw = w.readframes(w.getnframes())
    return max(abs(s) for s in struct.unpack(f"<{len(raw) // 2}h", raw))


# ---- the default is safe --------------------------------------------------

def test_the_default_is_well_below_full_scale():
    """A game must not open at a level nobody gave it permission for."""
    assert VOLUME <= 0.15, "the stock level is back up where it hurt"


def test_the_default_is_quieter_than_the_one_that_hurt():
    """0.35 peak is the level that was actually painful on earbuds."""
    assert VOLUME < 0.35


def test_the_default_is_not_silent():
    """Erring downwards must not go all the way to useless."""
    assert VOLUME > 0.0
    assert peak(render_riff(SKA_RIFFS["hit"])) > 1000


@pytest.mark.parametrize("event", sorted(SKA_RIFFS))
def test_every_riff_renders_at_the_default_level(event):
    assert peak(render_riff(SKA_RIFFS[event])) == pytest.approx(VOLUME * 32767, rel=0.01)


# ---- the ceiling is a bound, not a preference -----------------------------

def test_the_ceiling_holds_against_a_direct_set():
    set_volume(1.0, remember=False)
    assert calibrate._volume == VOLUME_CEILING


def test_the_ceiling_holds_against_the_command_line():
    """`--volume 1.0` is a request, not an override — hearing safety is not a
    thing the CLI gets to opt out of."""
    set_volume(float("9"), remember=False)
    assert calibrate._volume <= VOLUME_CEILING


def test_the_ceiling_holds_against_holding_the_key_down():
    for _ in range(200):
        nudge_volume(1)
    assert calibrate._volume == VOLUME_CEILING


def test_the_ceiling_is_itself_below_full_scale():
    assert VOLUME_CEILING < 1.0


def test_nothing_clips_even_at_the_ceiling():
    set_volume(VOLUME_CEILING, remember=False)
    for event in SKA_RIFFS:
        assert peak(render_riff(SKA_RIFFS[event])) <= int(VOLUME_CEILING * 32767) + 1


# ---- nudging --------------------------------------------------------------

def test_a_step_down_is_quieter_and_a_step_up_is_louder():
    start = calibrate._volume
    assert nudge_volume(-1) == pytest.approx(start - VOLUME_STEP)
    assert nudge_volume(1) == pytest.approx(start)


def test_it_cannot_go_below_silence():
    for _ in range(50):
        nudge_volume(-1)
    assert calibrate._volume == 0.0


def test_the_level_is_remembered():
    nudge_volume(-1)
    lowered = calibrate._volume
    calibrate._volume = VOLUME                              # as if freshly imported
    calibrate.load_sound_prefs()
    assert calibrate._volume == pytest.approx(lowered)


def test_a_nudge_rerenders_at_the_new_level():
    """The cache is keyed by event, so a stale render would keep playing at the
    old level — which for a volume control is the whole point missed."""
    was = peak(render_riff(SKA_RIFFS["hit"]))
    nudge_volume(-1)
    assert peak(render_riff(SKA_RIFFS["hit"])) < was


def test_turning_it_up_unmutes():
    """Reaching for louder while muted means you want to hear it."""
    set_muted(True, remember=False)
    nudge_volume(1)
    assert calibrate._muted is False


def test_turning_it_down_does_not_unmute():
    set_muted(True, remember=False)
    nudge_volume(-1)
    assert calibrate._muted is True


def test_a_zero_step_changes_nothing():
    before = calibrate._volume
    assert nudge_volume(0) == before
