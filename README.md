# Silphe

> Your mouse has a signature as personal as your handwriting. Silphe learns it — and shows you how it moves, holds, hunts, and drifts over time.

**Silphe** (σίλφη — Ancient Greek for the small creature that runs in the dark) is a tiny, **fully local** instrument for your own visuomotor signature: how *you, specifically,* move a pointer. Not whether you hit the target — *how you miss it on the way there:* the overshoot, the correction, the tremor, the chase.

It has two halves:

- a **library** that *generates* human-fidelity pointer movement and *quantifies* the movement you record, and
- a **game** that captures your movement while you play.

It began as a mouse-calibration chore and turned into something more interesting.

## Why it's interesting

- **Everyone clones voices; nobody clones movement.** Your pointer path is as individual as a fingerprint — and far less guarded.
- **Predictive vs. reactive.** Track a smooth target and you ride it with ~zero lag. Chase an evasive one and you're ~200 ms behind — pure human reaction time. Silphe measures both, separately.
- **It drifts.** Reaction, accuracy, tremor, tracking — they shift with the time of day, fatigue, a new medication, and the years. Silphe plots the **arc**.
- **Your data never leaves your machine.** Local capture, local model, local analysis. No cloud, no telemetry. Your silly walk is nobody's business but yours.

## Install

```bash
pip install silphe
```

Pure standard library — no third-party runtime dependencies. Generating and analyzing movement works on **any** OS; driving the real OS cursor (`silphe.cursor`) is Windows-only.

## Use the library

Generate a human-fidelity path — overshoot, corrections, tremor, dwell — on any platform:

```python
import random
from silphe import MovementModel

model = MovementModel(rng=random.Random(0))     # seed for reproducibility
path = model.plan(0, 0, 400, 250)               # -> [(x, y, dt), ...]
```

Drive the real cursor with a trusted OS click (Windows):

```python
from silphe import HumanCursor
HumanCursor().click(960, 540)
```

Quantify a recorded session into an aggregate signature:

```python
from silphe import load_recordings, session_signature

trials, _ = load_recordings()                   # ~/.silphe/recordings by default
sig = session_signature(trials)
print(sig["acquire"]["fitts"], sig["hold"]["tremor_hz"], sig["track"]["lag_ms"])
```

See the [session schema](https://github.com/martymcenroe/silphe/blob/main/docs/0005-session-schema.md).

## Play (calibration in a clown costume)

A green-garden field with four tasks:

- **Acquire** — hit the small gold target (Fitts's law: distance × size)
- **Track** — follow a slowly drifting dot (smooth pursuit)
- **Hold** — keep dead still on a single red pixel (tremor)
- **Andvari** — hunt the roach through the maze: it runs the dark, hides under silver cells, and you switch tools (swatter → pick, press **T**) to flush it out and finish it

```bash
silphe-play            # play (mouse)
silphe-play trackpad   # tag the session as a trackpad
```

Then see yourself:

```bash
silphe-analyze   # this session's aggregate signature
silphe-lag       # are you late? temporal lag vs spatial offset vs noise
silphe-arc       # the longitudinal dashboard — your fingerprint over time
silphe-demo      # human vs robot cursor, side by side (Windows)
```

From a source checkout, the same modules run via `python -m silphe.calibrate`, `python -m silphe.analyze`, and so on.

## The science, briefly

Fitts's law, corrective sub-movements, physiological tremor (4–12 Hz), smooth-pursuit lag, and the difference between getting *faster* and merely *learning the board*. See [the science](https://github.com/martymcenroe/silphe/blob/main/docs/0003-the-science.md).

## Privacy

Local-first, always — your movement never leaves your computer. See [the privacy note](https://github.com/martymcenroe/silphe/blob/main/docs/0002-privacy.md).

## License

[Apache-2.0](https://github.com/martymcenroe/silphe/blob/main/LICENSE) — permissive, with a patent grant. Use it, fork it, build on it.
