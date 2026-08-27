"""It has to sound like a horn section, not a beep — issue #90.

Whether it sounds like ska is a question only the operator can answer. What a
test CAN settle is whether the chord is actually in the signal, whether the
spectrum behaves like brass, and whether anything aliases — and those are the
things that were wrong.

The measurements here are a one-bin DFT: correlate the samples against a sine
and cosine at the frequency of interest and take the magnitude. Enough to ask
"is this pitch present", which is the whole question.
"""

import io
import math
import struct
import wave

import pytest

from silphe.calibrate import (BB, EB, PARTIALS, SAMPLE_RATE, SKA_RIFFS, VOLUME,
                              render_riff)


def samples(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        raw = w.readframes(w.getnframes())
    return list(struct.unpack(f"<{len(raw) // 2}h", raw))


def energy_at(sig, freq, rate=SAMPLE_RATE):
    """Magnitude of one DFT bin — how much of *freq* is in *sig*."""
    re = im = 0.0
    for i, s in enumerate(sig):
        a = 2 * math.pi * freq * i / rate
        re += s * math.cos(a)
        im += s * math.sin(a)
    return math.hypot(re, im) / max(1, len(sig))


# ---- the chord is really there --------------------------------------------

def test_a_chord_slot_puts_every_note_in_the_signal():
    """The heart of #90. A single pitch cannot be a horn section, so the test
    is that all three notes of the triad are actually present."""
    sig = samples(render_riff([(BB, 300)]))
    present = [energy_at(sig, f) for f in BB]
    absent = [energy_at(sig, f) for f in (520, 640, 750)]   # between the notes
    assert min(present) > 8 * max(absent), \
        f"the chord is not all there: {present} against {absent}"


def test_the_notes_are_within_reach_of_each_other():
    """A 'chord' whose upper notes are a whisper is a single note with
    decoration. They should be in the same league."""
    sig = samples(render_riff([(BB, 300)]))
    present = [energy_at(sig, f) for f in BB]
    assert min(present) > max(present) / 4


def test_a_bare_frequency_still_works():
    """The old single-pitch form stays valid — most of the suite uses it."""
    sig = samples(render_riff([(440, 200)]))
    assert energy_at(sig, 440) > 8 * energy_at(sig, 523)


def test_a_rest_is_still_silence():
    assert set(samples(render_riff([(0, 80)]))) == {0}


def test_two_different_chords_are_different_signals():
    assert samples(render_riff([(BB, 120)])) != samples(render_riff([(EB, 120)]))


# ---- it behaves like brass ------------------------------------------------

def test_the_spectrum_is_rich_not_three_partials():
    """A fundamental with two friends is a soft square wave, which is the
    1980s-game sound this replaces. Check well up the series."""
    sig = samples(render_riff([(440, 300)]))
    fundamental = energy_at(sig, 440)
    for h in (4, 5, 6):
        assert energy_at(sig, 440 * h) > fundamental / 200, f"partial {h} is missing"


def test_it_starts_bright_and_darkens():
    """The bright-to-dark sweep is what a horn does and a synth tone does not:
    the upper partials must die faster than the fundamental."""
    sig = samples(render_riff([(440, 400)]))
    half = len(sig) // 2
    head, tail = sig[:half], sig[half:]

    def brightness(part):
        return energy_at(part, 440 * 5) / max(energy_at(part, 440), 1e-9)

    assert brightness(head) > 2 * brightness(tail)


def test_the_attack_is_not_instant():
    """A horn takes a moment to speak. An instant onset is what sounds
    synthetic — this is why ATTACK_SECS grew."""
    sig = [abs(s) for s in samples(render_riff([(440, 300)]))]
    first_2ms = max(sig[:int(SAMPLE_RATE * 0.002)])
    by_30ms = max(sig[:int(SAMPLE_RATE * 0.030)])
    assert first_2ms < by_30ms / 5


def test_nothing_aliases_back_down_the_spectrum():
    """Partials at or above Nyquist are dropped, not folded back as noise.
    At 22050 the 9th partial of 1397 Hz is 12573, which would fold to 9477.
    """
    high = 1397
    assert high * PARTIALS > SAMPLE_RATE / 2, "pick a pitch that would actually alias"
    sig = samples(render_riff([(high, 250)]))
    folded = SAMPLE_RATE - high * PARTIALS
    assert energy_at(sig, folded) < energy_at(sig, high) / 50


# ---- level ----------------------------------------------------------------

@pytest.mark.parametrize("event", sorted(SKA_RIFFS))
def test_every_riff_uses_the_headroom_it_is_given(event):
    """Normalized to the requested peak. A worst-case divisor left the old
    render at a third of the allowance, which just sounds quiet."""
    peak = max(abs(s) for s in samples(render_riff(SKA_RIFFS[event])))
    assert peak == pytest.approx(VOLUME * 32767, rel=0.01)


@pytest.mark.parametrize("event", sorted(SKA_RIFFS))
def test_no_riff_clips(event):
    ceiling = int(VOLUME * 32767) + 1
    assert max(abs(s) for s in samples(render_riff(SKA_RIFFS[event]))) <= ceiling


def test_a_chord_does_not_clip_where_a_single_note_would_not():
    """Three voices summed is where clipping would have crept in."""
    ceiling = int(VOLUME * 32767) + 1
    assert max(abs(s) for s in samples(render_riff([(BB, 200)]))) <= ceiling


def test_volume_still_means_something():
    loud = max(abs(s) for s in samples(render_riff([(BB, 120)], volume=0.8)))
    quiet = max(abs(s) for s in samples(render_riff([(BB, 120)], volume=0.2)))
    assert loud > 3 * quiet


# ---- the score ------------------------------------------------------------

@pytest.mark.parametrize("event", sorted(SKA_RIFFS))
def test_the_riffs_are_written_as_chords(event):
    """If a riff went back to single notes it would stop being a section."""
    pitched = [p for p, _ in SKA_RIFFS[event] if p]
    chords = [p for p in pitched if not isinstance(p, (int, float))]
    assert chords == pitched, f"{event} has bare notes where a stab belongs"


@pytest.mark.parametrize("event", ("hit", "board"))
def test_the_skank_keeps_its_offbeat_rests(event):
    """Take the rests out and it is noise on the beat, not ska."""
    assert any(not p for p, _ in SKA_RIFFS[event])
