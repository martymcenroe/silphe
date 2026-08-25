"""Mute and volume — issue #85.

`Beep` had no amplitude to expose, which is why this could not exist before the
riffs were synthesized (#83).
"""

import io
import json
import os
import struct
import sys
import wave

import pytest

from silphe import calibrate
from silphe.calibrate import (SKA_RIFFS, VOLUME, load_sound_prefs, parse_args,
                              render_riff, save_sound_prefs, set_muted,
                              set_volume, sound_prefs_path)


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("SILPHE_RECORDINGS", str(tmp_path / "recordings"))
    monkeypatch.setattr(calibrate, "_RIFF_WAVS", {})
    monkeypatch.setattr(calibrate, "_sound_off", False)
    monkeypatch.setattr(calibrate, "_sound_reported", False)
    monkeypatch.setattr(calibrate, "_muted", False)
    monkeypatch.setattr(calibrate, "_volume", VOLUME)
    return tmp_path


class FakeWinsound:
    SND_MEMORY = 4
    SND_ASYNC = 1

    def __init__(self):
        self.calls = []

    def PlaySound(self, data, flags):                       # noqa: N802 — winsound's name
        self.calls.append((data, flags))


def install(monkeypatch):
    fake = FakeWinsound()
    monkeypatch.setitem(sys.modules, "winsound", fake)
    return fake


def play(event="hit"):
    t = calibrate.ska(event)
    if t is not None:
        t.join(timeout=10)
    return t


def peak(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        raw = w.readframes(w.getnframes())
    return max(abs(s) for s in struct.unpack(f"<{len(raw) // 2}h", raw))


# ---- muting ---------------------------------------------------------------

def test_muted_plays_nothing(monkeypatch):
    fake = install(monkeypatch)
    set_muted(True)
    assert calibrate.ska("hit") is None
    assert fake.calls == []


def test_unmuting_brings_it_back(monkeypatch):
    fake = install(monkeypatch)
    set_muted(True)
    play("hit")
    set_muted(False)
    play("hit")
    assert len(fake.calls) == 1


def test_muting_does_not_render_anything(monkeypatch):
    """No point synthesizing what will not be played."""
    install(monkeypatch)
    set_muted(True)
    calibrate.ska("board")
    assert calibrate._RIFF_WAVS == {}


# ---- volume ---------------------------------------------------------------

def test_volume_changes_what_is_rendered():
    set_volume(0.8, remember=False)
    loud = peak(render_riff(SKA_RIFFS["hit"]))
    set_volume(0.1, remember=False)
    quiet = peak(render_riff(SKA_RIFFS["hit"]))
    assert quiet < loud


def test_changing_volume_throws_away_the_cached_renders(monkeypatch):
    """The cache is keyed by event, so a stale render would keep playing at the
    old level for the rest of the session."""
    install(monkeypatch)
    play("hit")
    was = peak(calibrate._RIFF_WAVS["hit"])

    set_volume(0.05, remember=False)
    assert calibrate._RIFF_WAVS == {}, "the old render survived the change"
    play("hit")
    assert peak(calibrate._RIFF_WAVS["hit"]) < was


def test_the_same_volume_keeps_the_cache(monkeypatch):
    install(monkeypatch)
    play("hit")
    kept = calibrate._RIFF_WAVS["hit"]
    set_volume(calibrate._volume, remember=False)
    assert calibrate._RIFF_WAVS.get("hit") is kept


def test_volume_is_clamped_not_refused():
    """An out-of-range number is a typo, and refusing to start over one would
    be worse than quietly doing the sane thing."""
    set_volume(9.0, remember=False)
    assert calibrate._volume == 1.0
    set_volume(-3.0, remember=False)
    assert calibrate._volume == 0.0


def test_zero_volume_still_renders_silence_rather_than_erroring():
    set_volume(0.0, remember=False)
    assert peak(render_riff(SKA_RIFFS["hit"])) == 0


def test_render_reads_the_level_at_call_time():
    """A default bound at def time would freeze the volume at import."""
    set_volume(0.9, remember=False)
    assert peak(render_riff([(440, 60)])) > peak(render_riff([(440, 60)], volume=0.2))


# ---- remembering ----------------------------------------------------------

def test_the_choice_survives_a_restart():
    set_muted(True)
    set_volume(0.2)
    calibrate._muted, calibrate._volume = False, VOLUME     # as if freshly imported
    load_sound_prefs()
    assert calibrate._muted is True
    assert calibrate._volume == 0.2


def test_it_is_written_next_to_the_leaderboard():
    set_volume(0.4)
    assert os.path.dirname(sound_prefs_path()) == \
        os.path.dirname(calibrate.leaderboard_path())
    with open(sound_prefs_path(), encoding="utf-8") as f:
        assert json.load(f)["volume"] == 0.4


def test_no_settings_file_means_the_defaults():
    assert not os.path.exists(sound_prefs_path())
    load_sound_prefs()
    assert calibrate._muted is False
    assert calibrate._volume == VOLUME


def test_a_corrupt_settings_file_means_the_defaults_not_a_crash(fresh):
    """Never a silent game nobody asked for, and never a game that will not
    start because a preference file got mangled."""
    os.makedirs(os.path.dirname(sound_prefs_path()), exist_ok=True)
    with open(sound_prefs_path(), "w", encoding="utf-8") as f:
        f.write("{not json at all")
    load_sound_prefs()
    assert calibrate._muted is False
    assert calibrate._volume == VOLUME


def test_an_unwritable_location_does_not_crash(monkeypatch):
    """A preference is not worth taking the game down for."""
    monkeypatch.setattr(calibrate, "sound_prefs_path",
                        lambda: os.path.join(os.sep, "no", "such", "dir", "sound.json"))
    save_sound_prefs()                                      # must not raise


def test_remember_false_leaves_no_file():
    set_volume(0.5, remember=False)
    set_muted(True, remember=False)
    assert not os.path.exists(sound_prefs_path())


# ---- the command line -----------------------------------------------------

def test_no_sound_flags_means_no_opinion():
    """None, not a default — otherwise every launch would overwrite what was
    remembered."""
    opts = parse_args([])
    assert opts["muted"] is None and opts["volume"] is None


def test_mute_flag():
    assert parse_args(["--mute"])["muted"] is True


def test_volume_flag_both_spellings():
    assert parse_args(["--volume", "0.2"])["volume"] == "0.2"
    assert parse_args(["--volume=0.2"])["volume"] == "0.2"


def test_the_old_flags_still_work_alongside():
    opts = parse_args(["trackpad", "--player", "Rebecca", "--difficulty=hard", "--mute"])
    assert opts == {"device": "trackpad", "player": "Rebecca", "difficulty": "hard",
                    "volume": None, "muted": True}


def test_a_trailing_volume_flag_does_not_crash():
    assert parse_args(["--volume"])["volume"] is None
