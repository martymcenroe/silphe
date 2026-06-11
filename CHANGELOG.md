# Changelog

All notable changes to Silphe are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is
[Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-06-11

First public release: the reusable instrument.

### Added
- `silphe.model.MovementModel` — cross-platform generation of human-fidelity
  pointer paths (ballistic overshoot, corrective sub-movements, continuous
  micro-tremor, heavy-tailed dwell). Pure standard library; deterministic with a
  seeded RNG.
- `silphe.cursor.HumanCursor` / `RobotCursor` — drive the real OS cursor with a
  trusted (`isTrusted`) click on Windows. Import is safe on any platform;
  driving is cleanly guarded off Windows.
- `silphe.analysis` — quantify a recorded session into an aggregate movement
  signature: Fitts fit, corrective reversals, hold tremor (amplitude +
  dominant frequency), and a tracking lag / offset / noise decomposition.
- Calibration game and dashboards as console entry points: `silphe-play`,
  `silphe-arc`, `silphe-analyze`, `silphe-lag`, `silphe-demo`.
- Apache-2.0 license; PyPI publishing via OIDC Trusted Publishing (no stored
  token).
