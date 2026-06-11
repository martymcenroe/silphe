# Silphe

> Your mouse has a signature as personal as your handwriting. Silphe learns it — and shows you how it moves, holds, hunts, and drifts over time.

**Silphe** (σίλφη — Ancient Greek for the small creature that runs in the dark) is a tiny, fun, **fully local** desktop game that captures how *you, specifically,* move a pointer. Not whether you hit the target — *how you miss it on the way there:* the overshoot, the correction, the tremor, the chase.

It began as a mouse-calibration chore and turned into something more interesting: a privacy-first instrument for your own visuomotor signature, and how it changes.

## Why it's interesting

- **Everyone clones voices; nobody clones movement.** Your pointer path is as individual as a fingerprint — and far less guarded.
- **Predictive vs. reactive.** Track a smooth target and you ride it with ~zero lag. Chase an evasive one and you're ~200 ms behind — pure human reaction time. Silphe measures both, separately.
- **It drifts.** Reaction, accuracy, tremor, tracking — they shift with the time of day, fatigue, a new medication, and the years. Silphe plots the **arc**.
- **Your data never leaves your machine.** Local capture, local model, local analysis. No cloud, no telemetry. Your silly walk is nobody's business but yours.

## The games (calibration in a clown costume)

A green-garden field with four tasks:

- **Acquire** — hit the small gold target (Fitts's law: distance × size)
- **Track** — follow a slowly drifting dot (smooth pursuit)
- **Hold** — keep dead still on a single red pixel (tremor)
- **Andvari** — hunt the roach through the maze: it runs the dark, hides under silver cells, and you switch tools (swatter → pick, press **T**) to flush it out and finish it

```bash
python src/silphe/calibrate.py            # play (mouse)
python src/silphe/calibrate.py trackpad   # tag the session as trackpad
```

## See yourself

```bash
python src/silphe/analyze.py       # this session's aggregate signature
python src/silphe/analyze_lag.py   # are you late? temporal lag vs spatial offset vs noise
python src/silphe/arc.py           # the longitudinal dashboard — your fingerprint over time
python src/silphe/human_cursor.py  # the cursor model: a human-fidelity move (Windows)
python src/silphe/range_demo.py    # human vs robot cursor, side by side (Windows)
```

Everything is pure standard library (tkinter + ctypes) — nothing to install to play.

## The science, briefly

Fitts's law, corrective sub-movements, physiological tremor (4–12 Hz), smooth-pursuit lag, and the difference between getting *faster* and merely *learning the board*. See [`docs/0003-the-science.md`](docs/0003-the-science.md).

## Privacy

Local-first, always — your movement never leaves your computer. See [`docs/0002-privacy.md`](docs/0002-privacy.md).

## Install (soon)

```bash
pip install silphe
```

Coming — see the launch plan in [`docs/0001-launch-plan.md`](docs/0001-launch-plan.md).

## License

PolyForm Noncommercial 1.0.0 — see [LICENSE](LICENSE).
