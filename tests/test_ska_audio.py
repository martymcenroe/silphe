"""Ska riffs are synthesized, not beeped — issues #83, #84.

The audible half still needs human ears. The rendering does not, and nor does
the promise that a sound which cannot play says so exactly once.
"""

import io
import sys
import struct
import threading
import wave

import pytest

from silphe import calibrate
from silphe.calibrate import SKA_RIFFS, render_riff


@pytest.fixture(autouse=True)
def fresh_audio_state(monkeypatch):
    """Each test gets an unrendered, un-given-up-on audio module."""
    monkeypatch.setattr(calibrate, "_RIFF_WAVS", {})
    monkeypatch.setattr(calibrate, "_sound_off", False)
    monkeypatch.setattr(calibrate, "_sound_reported", False)


class FakeWinsound:
    """Stands in for the real module, so these run anywhere and make no noise."""

    SND_MEMORY = 4
    SND_ASYNC = 1

    def __init__(self, raises=None):
        self.calls = []
        self.raises = raises

    def PlaySound(self, data, flags):                       # noqa: N802 — winsound's name
        if self.raises:
            raise self.raises
        self.calls.append((data, flags))


def install(monkeypatch, fake):
    monkeypatch.setitem(sys.modules, "winsound", fake)
    return fake


def play(event="hit"):
    """Fire a riff and wait for its thread. Waiting on the thread `ska` hands
    back is what keeps these deterministic instead of sleeping and hoping."""
    t = calibrate.ska(event)
    if t is not None:
        t.join(timeout=10)
        assert not t.is_alive(), "the riff thread never finished"
    return t


def samples(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        raw = w.readframes(w.getnframes())
    return list(struct.unpack(f"<{len(raw) // 2}h", raw))


def expected_frames(seq, rate=calibrate.SAMPLE_RATE):
    return sum(int(rate * ms / 1000) for _, ms in seq)


# ---- the rendering --------------------------------------------------------

@pytest.mark.parametrize("event", sorted(SKA_RIFFS))
def test_every_riff_renders_to_a_real_wav(event):
    data = render_riff(SKA_RIFFS[event])
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    with wave.open(io.BytesIO(data)) as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == calibrate.SAMPLE_RATE
        assert w.getnframes() == expected_frames(SKA_RIFFS[event])


@pytest.mark.parametrize("event", sorted(SKA_RIFFS))
def test_a_riff_lasts_as_long_as_its_score_says(event):
    seq = SKA_RIFFS[event]
    with wave.open(io.BytesIO(render_riff(seq))) as w:
        secs = w.getnframes() / w.getframerate()
    assert secs == pytest.approx(sum(ms for _, ms in seq) / 1000, abs=0.002)


def test_a_rest_is_silence_rather_than_nothing():
    """A dropped rest would not shorten the riff, it would change the rhythm —
    and the offbeat rests are what make it skank."""
    data = render_riff([(0, 100)])
    got = samples(data)
    assert len(got) == expected_frames([(0, 100)])
    assert set(got) == {0}


def test_a_note_actually_makes_a_sound():
    assert any(s != 0 for s in samples(render_riff([(440, 100)])))


def test_the_rest_inside_a_riff_lands_where_the_score_puts_it():
    """`hit` opens on a 30ms rest — the offbeat that makes it an upstroke."""
    rate = calibrate.SAMPLE_RATE
    got = samples(render_riff(SKA_RIFFS["hit"]))
    rest = int(rate * 30 / 1000)
    assert set(got[:rest]) == {0}, "the opening rest is not silent"
    assert any(s != 0 for s in got[rest:]), "nothing follows the rest"


def test_nothing_clips():
    """Every riff, not a sampled one: a clipped stab sounds worse than a quiet
    one, which is why VOLUME leaves headroom."""
    ceiling = int(calibrate.VOLUME * 32767) + 1
    for event, seq in SKA_RIFFS.items():
        peak = max(abs(s) for s in samples(render_riff(seq)))
        assert peak <= ceiling, f"{event} clips at {peak}"


def test_a_note_decays_instead_of_holding():
    """The difference between a stab and a tone. Compare the start of a long
    note against its end."""
    got = [abs(s) for s in samples(render_riff([(440, 300)]))]
    head = max(got[:len(got) // 10])
    tail = max(got[-len(got) // 10:])
    assert tail < head / 4, "the note is holding, not stabbing"


def test_volume_scales_the_result():
    loud = max(abs(s) for s in samples(render_riff([(440, 80)], volume=0.8)))
    quiet = max(abs(s) for s in samples(render_riff([(440, 80)], volume=0.2)))
    assert quiet < loud


# ---- playing it -----------------------------------------------------------

def test_a_riff_is_played_whole_in_one_call(monkeypatch):
    """One PlaySound per riff, not per note: PlaySound plays one sound at a
    time, so a note-at-a-time riff would cut itself off at every step."""
    fake = install(monkeypatch, FakeWinsound())
    play("squash")
    assert len(fake.calls) == 1


def test_it_is_played_from_memory_and_never_asynchronously(monkeypatch):
    """`winsound` refuses SND_MEMORY | SND_ASYNC — "Cannot play asynchronously
    from memory". Asking for it raises rather than degrading, which is why the
    riff blocks its thread instead."""
    fake = install(monkeypatch, FakeWinsound())
    play("hit")
    data, flags = fake.calls[0]
    assert flags == fake.SND_MEMORY
    assert not flags & fake.SND_ASYNC
    assert data[:4] == b"RIFF"


def test_the_game_loop_does_not_wait_for_the_riff(monkeypatch):
    """The whole reason for the thread: PlaySound from memory blocks for the
    length of the riff, and the caller must not."""
    started = threading.Event()
    release = threading.Event()

    class Blocking(FakeWinsound):
        def PlaySound(self, data, flags):                   # noqa: N802
            started.set()
            release.wait(10)
            super().PlaySound(data, flags)

    install(monkeypatch, Blocking())
    t = calibrate.ska("board")
    assert started.wait(10), "the riff never started"
    assert t.is_alive(), "ska waited for the sound to finish"
    release.set()
    t.join(timeout=10)


def test_each_riff_is_rendered_once_and_kept(monkeypatch):
    """Synthesis is a per-sample Python loop; it must not run again on every
    hit."""
    install(monkeypatch, FakeWinsound())
    renders = []
    real = calibrate.render_riff
    monkeypatch.setattr(calibrate, "render_riff",
                        lambda seq, **kw: renders.append(seq) or real(seq, **kw))

    for _ in range(5):
        play("hit")
    assert len(renders) == 1
    assert calibrate._RIFF_WAVS["hit"][:4] == b"RIFF"


def test_rendering_happens_off_the_game_loop(monkeypatch):
    """First hit of a session included: the render runs on the riff's thread,
    not in the caller."""
    install(monkeypatch, FakeWinsound())
    where = {}
    real = calibrate.render_riff

    def note_the_thread(seq, **kw):
        where["thread"] = threading.current_thread()
        return real(seq, **kw)

    monkeypatch.setattr(calibrate, "render_riff", note_the_thread)

    play("hit")
    assert where["thread"] is not threading.main_thread()


def test_the_kept_bytes_are_the_ones_handed_to_windows(monkeypatch):
    fake = install(monkeypatch, FakeWinsound())
    play("hit")
    play("hit")
    assert fake.calls[0][0] is fake.calls[1][0] is calibrate._RIFF_WAVS["hit"]


def test_an_unknown_event_does_nothing(monkeypatch):
    fake = install(monkeypatch, FakeWinsound())
    assert calibrate.ska("kazoo") is None
    assert fake.calls == []


# ---- #84: it must not fail in silence -------------------------------------

def test_a_failure_is_reported(monkeypatch, capsys):
    install(monkeypatch, FakeWinsound(raises=RuntimeError("no audio device")))
    play("hit")
    err = capsys.readouterr().err
    assert "SOUND FAILED" in err
    assert "RuntimeError" in err and "no audio device" in err


def test_the_asynchronous_from_memory_refusal_would_be_caught(monkeypatch, capsys):
    """The exact failure this engine hit on its first real run: asking for
    SND_MEMORY | SND_ASYNC raises, and without #84 it would have been silent."""
    install(monkeypatch, FakeWinsound(
        raises=RuntimeError("Cannot play asynchronously from memory")))
    play("hit")
    assert "Cannot play asynchronously from memory" in capsys.readouterr().err


def test_a_failure_is_reported_exactly_once(monkeypatch, capsys):
    """A warning per hit would be worse than the silence it reports."""
    install(monkeypatch, FakeWinsound(raises=RuntimeError("no audio device")))
    for _ in range(20):
        play("hit")
    assert capsys.readouterr().err.count("SOUND FAILED") == 1


def test_a_failure_does_not_reach_the_game(monkeypatch):
    install(monkeypatch, FakeWinsound(raises=RuntimeError("no audio device")))
    play("hit")                                             # must not raise


def test_after_failing_it_stops_trying(monkeypatch):
    """Once audio has proven unusable, every later riff is a no-op rather than
    another thread and another attempt."""
    fake = FakeWinsound(raises=RuntimeError("no audio device"))
    install(monkeypatch, fake)
    play("hit")
    fake.raises = None                                      # it would work now
    assert calibrate.ska("hit") is None, "it started another thread after giving up"
    assert fake.calls == [], "it went back for more after giving up"


def test_no_winsound_is_reported_as_expected_not_as_a_failure(monkeypatch, capsys):
    """Off Windows this is the normal state of affairs, and it should not read
    like something broke."""
    monkeypatch.setitem(sys.modules, "winsound", None)      # makes `import winsound` raise
    assert calibrate.ska("hit") is None
    err = capsys.readouterr().err
    assert "no sound" in err
    assert "SOUND FAILED" not in err
    assert sys.platform in err


def test_no_winsound_is_also_only_said_once(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "winsound", None)
    for _ in range(10):
        calibrate.ska("hit")
    assert capsys.readouterr().err.count("no sound") == 1
