"""
Silphe — your pointer-movement signature, captured and quantified.

Your mouse has a signature as personal as your handwriting: the overshoot, the
correction, the tremor, the chase. Silphe generates human-fidelity pointer paths
and measures the ones *you* leave — locally, on your own machine.

Two halves, both pure standard library:

* :mod:`silphe.model` — generate human-fidelity paths (overshoot, corrective
  sub-movements, tremor, dwell). Cross-platform.
* :mod:`silphe.analysis` — quantify a recorded session into an aggregate
  movement signature (Fitts fit, tremor, tracking lag/offset). Cross-platform.

And one Windows-only convenience:

* :mod:`silphe.cursor` — drive the real OS cursor along a generated path
  (``isTrusted`` clicks via Win32). Import is safe everywhere; driving needs
  Windows.
"""

from __future__ import annotations

from silphe.analysis import (
    acquire_stats,
    fitts_fit,
    hold_stats,
    lag_scan,
    load_recordings,
    load_session,
    player_recordings_dir,
    recordings_dir,
    session_signature,
)
from silphe.cursor import HumanCursor, RobotCursor
from silphe.model import DEFAULT_PROFILE, TREMOR_PROFILE, MovementModel

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # generation
    "MovementModel",
    "DEFAULT_PROFILE",
    "TREMOR_PROFILE",
    # driving (Windows)
    "HumanCursor",
    "RobotCursor",
    # analysis
    "session_signature",
    "acquire_stats",
    "hold_stats",
    "fitts_fit",
    "lag_scan",
    "load_session",
    "load_recordings",
    "recordings_dir",
    "player_recordings_dir",
]
