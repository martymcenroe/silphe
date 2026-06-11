"""Tests for silphe.cursor — most importantly, that importing it (and the whole
package) is safe on any OS, and that driving is cleanly guarded off Windows.
"""

import pytest

import silphe
import silphe.cursor as cursor


def test_package_imports_and_exposes_api():
    # Importing silphe must NOT require Windows (the bug this package was born to
    # avoid: a top-level ctypes.windll call that crashes on macOS/Linux).
    assert silphe.__version__
    for name in ("MovementModel", "HumanCursor", "RobotCursor", "session_signature"):
        assert hasattr(silphe, name)


def test_driving_is_guarded_off_windows(monkeypatch):
    # Simulate a non-Windows platform and confirm the driver refuses clearly
    # instead of blowing up with an opaque ctypes error.
    monkeypatch.setattr(cursor, "_IS_WINDOWS", False)
    monkeypatch.setattr(cursor, "_user32", None)
    monkeypatch.setattr(cursor, "_winmm", None)
    with pytest.raises(NotImplementedError):
        cursor._ensure_win32()


def test_humancursor_can_plan_without_driving():
    # Generation works everywhere; this never touches the OS cursor.
    import random
    wp = cursor.HumanCursor(rng=random.Random(0)).plan(0, 0, 250, 120)
    assert len(wp) > 10
    assert abs(wp[-1][0] - 250) < 8
