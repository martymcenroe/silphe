"""silphe.core — THE CAPTURE KERNEL.

The one part of silphe that must never fork. Every build in the silphe family
records through this exact module, so movement data stays byte-comparable and a
person's movement signature stays portable across versions and across the
family. Extend the shell around the kernel (games, analysis, applications);
never diverge the kernel itself.

Public surface:
- ``SCHEMA_VERSION`` / ``KERNEL_FIELDS`` — the recording contract (see #49).
- ``recordings_dir`` / ``player_recordings_dir`` / ``known_players`` — where
  recordings live, install-location independent so the game and the analyzers
  always agree.
- ``Recorder`` — open a session, write records (kernel fields stamped), close.
"""

from __future__ import annotations

import json
import os
import platform
import time

__all__ = [
    "SCHEMA_VERSION",
    "KERNEL_FIELDS",
    "recordings_dir",
    "player_recordings_dir",
    "known_players",
    "Recorder",
]

# The recording schema version. Bump ONLY on a breaking change (a field renamed
# or removed, or its meaning changed). Additive fields do NOT bump it — the
# compatibility promise is additive-only within a major version. The contract
# test in tests/test_core.py fails fast if the kernel's stamped fields drift
# without this constant changing. See docs/0005-session-schema.md.
SCHEMA_VERSION = 1

# The fields the kernel itself stamps on every record. Games add their own
# fields on top (kind, samples, difficulty, score, ...); these four plus the
# version are the invariant the whole family shares.
KERNEL_FIELDS = ("schema_version", "device", "os", "player")


# --------------------------------------------------------------------------
# Where recordings live
# --------------------------------------------------------------------------

def recordings_dir() -> str:
    """Where session recordings live. ``$SILPHE_RECORDINGS`` if set, else
    ``~/.silphe/recordings``. Install-location independent, so the game and the
    analyzers always agree regardless of where the package is installed.
    """
    env = os.environ.get("SILPHE_RECORDINGS")
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), ".silphe", "recordings")


def player_recordings_dir(player: str | None = None) -> str:
    """Recordings dir for *player*: a ``recordings-<name>`` sibling of
    :func:`recordings_dir` (e.g. ``~/.silphe/recordings-Rebecca``). No player
    (or a name that sanitizes to nothing) means the base dir — the historical
    single-player layout. Names are restricted to ``[A-Za-z0-9_-]``.
    """
    base = recordings_dir()
    if not player:
        return base
    safe = "".join(ch for ch in player if ch.isalnum() or ch in "-_")
    return f"{base}-{safe}" if safe else base


def known_players() -> list[str]:
    """Players who already have a ``recordings-<name>`` sibling dir next to
    :func:`recordings_dir`. Sorted; does not include the default player.
    """
    base = os.path.abspath(recordings_dir())
    parent, name = os.path.split(base)
    prefix = name + "-"
    if not os.path.isdir(parent):
        return []
    return sorted(d[len(prefix):] for d in os.listdir(parent)
                  if d.startswith(prefix) and os.path.isdir(os.path.join(parent, d)))


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------

class Recorder:
    """Writes a session's movement records as JSONL, stamping the kernel fields
    (:data:`KERNEL_FIELDS`) on every record. A session file is named
    ``session-<epoch>-<device>.jsonl`` in the player's recordings dir.

    The file is not created until the first :meth:`write`. A session that
    records nothing leaves nothing behind — which is the common case at launch,
    since the game builds a recorder for the default player before asking who
    is playing, and again for whoever is chosen (#78).

    Usage::

        rec = Recorder(device="mouse", player="Rebecca")
        rec.write({"kind": "hold", "samples": [...]})   # kernel fields added
        rec.close()
    """

    def __init__(self, device: str = "mouse", player: str | None = None):
        self.device = (device or "mouse").lower()
        self.player = player
        self.os = platform.system()
        self.path: str | None = None
        self._fh = None
        self._closed = False
        self.open_session()

    def open_session(self) -> str:
        """Name (or rename) this session's file for the current player and
        return its path. The path is settled now — the timestamp in it is when
        the session began, not when the first round landed — but nothing is
        created on disk until something is written."""
        self.close()                                       # never leak a handle on reopen
        rec_dir = player_recordings_dir(self.player)
        os.makedirs(rec_dir, exist_ok=True)                # so known_players sees them
        self.path = os.path.join(rec_dir, f"session-{int(time.time())}-{self.device}.jsonl")
        self._fh = None
        self._closed = False
        return self.path

    def write(self, record: dict) -> dict:
        """Stamp the kernel fields onto *record* and append it as one JSONL
        line. Returns the stamped record (the caller may read back the score
        etc. it added). Flushes so an interrupted session keeps every round.
        Creates the session file if this is the first record."""
        record["schema_version"] = SCHEMA_VERSION
        record["device"] = self.device
        record["os"] = self.os
        record["player"] = self.player or ""
        if self._closed:
            # Deferring the open must not quietly resurrect a finished session.
            raise ValueError("write to a closed Recorder")
        if self._fh is None:
            self._fh = open(self.path, "a", encoding="utf-8")
        self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()
        return record

    def close(self) -> None:
        try:
            if self._fh is not None:
                self._fh.close()
        except Exception:
            pass
        self._fh = None
        self._closed = True
