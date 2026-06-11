"""
silphe.cursor — drive the REAL OS cursor along a human-fidelity path.

Importing this module is safe on **any** platform. Actually *moving* the cursor
(:meth:`HumanCursor.move_to`, :meth:`HumanCursor.click`) uses the Win32
``SendInput`` / ``SetCursorPos`` APIs via ``ctypes`` and therefore works only on
Windows; on other platforms those calls raise :class:`NotImplementedError` with a
clear message. The path *generation* lives in :mod:`silphe.model` and runs
everywhere — so you can plan, analyze, and visualize paths on any OS, and drive
them for real on Windows.

The OS-level click means the event a page sees is ``isTrusted: true`` —
indistinguishable from a physical mouse.

    from silphe.cursor import HumanCursor
    HumanCursor().click(960, 540)   # Windows: moves the real cursor and clicks
"""

from __future__ import annotations

import ctypes      # importing ctypes is cross-platform; only ctypes.windll is Windows-only
import random
import sys
import time

# Re-export the model knobs so callers can do `from silphe.cursor import TREMOR_PROFILE`.
from silphe.model import DEFAULT_PROFILE, TREMOR_PROFILE, MovementModel

_IS_WINDOWS = sys.platform == "win32"

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
INPUT_MOUSE = 0

# --- ctypes struct layouts (safe to define on any OS; basic C types only) ---


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class _INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = (("mi", _MOUSEINPUT),)

    _anonymous_ = ("i",)
    _fields_ = (("type", ctypes.c_ulong), ("i", _I))


class _POINT(ctypes.Structure):
    _fields_ = (("x", ctypes.c_long), ("y", ctypes.c_long))


_user32 = None
_winmm = None


def _ensure_win32():
    """Lazily bind the Win32 DLLs. Raises on non-Windows. Idempotent."""
    global _user32, _winmm
    if _user32 is not None:
        return
    if not _IS_WINDOWS:
        raise NotImplementedError(
            "silphe.cursor drives the real OS cursor through Win32 and runs only "
            "on Windows. To GENERATE paths on any platform, use "
            "silphe.model.MovementModel(...).plan(sx, sy, tx, ty)."
        )
    user32 = ctypes.windll.user32
    winmm = ctypes.windll.winmm
    # Make the process DPI-aware so our pixel coordinates match the cursor's —
    # the coordinate-mapping foot-gun on large / scaled displays.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE_V2-ish
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
    user32.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(_INPUT), ctypes.c_int)
    user32.SendInput.restype = ctypes.c_uint
    user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
    user32.GetCursorPos.argtypes = (ctypes.POINTER(_POINT),)
    _user32, _winmm = user32, winmm


def get_pos() -> tuple[int, int]:
    """Current cursor position in screen pixels. Windows only."""
    _ensure_win32()
    pt = _POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def set_pos(x: float, y: float) -> None:
    """Teleport the cursor to ``(x, y)`` in screen pixels. Windows only."""
    _ensure_win32()
    _user32.SetCursorPos(int(round(x)), int(round(y)))


def _send_flag(flag: int) -> None:
    extra = ctypes.c_ulong(0)
    mi = _MOUSEINPUT(0, 0, 0, flag, 0, ctypes.pointer(extra))
    inp = _INPUT(type=INPUT_MOUSE)
    inp.mi = mi
    _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


class HumanCursor:
    """Plan a human-fidelity path (via :class:`~silphe.model.MovementModel`) and
    drive the real cursor along it. Generation works anywhere; driving is
    Windows-only.
    """

    def __init__(self, profile: dict | None = None, rng: random.Random | None = None):
        self.model = MovementModel(profile, rng)
        self.rng = self.model.rng

    # ---- public API -----------------------------------------------------

    def move_to(self, tx: float, ty: float) -> list[tuple[float, float, float]]:
        """Move the real cursor to ``(tx, ty)``. Returns the waypoints driven."""
        sx, sy = get_pos()
        waypoints = self.model.plan(sx, sy, tx, ty)
        self._drive(waypoints)
        return waypoints

    def click(self, tx: float, ty: float) -> list[tuple[float, float, float]]:
        """Human-move to ``(tx, ty)``, dwell, then issue a trusted OS click."""
        waypoints = self.move_to(tx, ty)
        self._press(tx, ty)
        return waypoints

    def plan(self, sx, sy, tx, ty):
        """Generate (do not drive) the waypoints. Works on any platform."""
        return self.model.plan(sx, sy, tx, ty)

    # ---- driver ---------------------------------------------------------

    def _drive(self, waypoints):
        _ensure_win32()
        _winmm.timeBeginPeriod(1)  # 1 ms timer resolution for smooth pacing
        try:
            t0 = time.perf_counter()
            planned = 0.0
            for (x, y, dt) in waypoints:
                set_pos(x, y)
                planned += dt
                while True:
                    rem = planned - (time.perf_counter() - t0)
                    if rem <= 0:
                        break
                    time.sleep(rem - 0.0015) if rem > 0.003 else None  # then busy-spin
        finally:
            _winmm.timeEndPeriod(1)

    def _press(self, tx, ty):
        rng = self.rng
        _send_flag(MOUSEEVENTF_LEFTDOWN)
        hold = rng.uniform(0.04, 0.16)
        time.sleep(hold * 0.5)
        set_pos(tx + rng.uniform(-1.2, 1.2), ty + rng.uniform(-1.2, 1.2))  # press drift
        time.sleep(hold * 0.5)
        _send_flag(MOUSEEVENTF_LEFTUP)


class RobotCursor:
    """The foil: a straight line at constant speed, no tremor, instant click.
    Exists only so you can SEE what a human path is refusing to do.
    """

    def move_to(self, tx, ty):
        sx, sy = get_pos()
        steps = 60
        wp = [(sx + (tx - sx) * i / steps, sy + (ty - sy) * i / steps, 0.5 / steps)
              for i in range(1, steps + 1)]
        _ensure_win32()
        _winmm.timeBeginPeriod(1)
        try:
            for (x, y, dt) in wp:
                set_pos(x, y)
                time.sleep(dt)
        finally:
            _winmm.timeEndPeriod(1)
        return wp

    def click(self, tx, ty):
        wp = self.move_to(tx, ty)
        _send_flag(MOUSEEVENTF_LEFTDOWN)
        _send_flag(MOUSEEVENTF_LEFTUP)
        return wp


def _smoke_test():
    """Safe demo: wander the real cursor near where it already is. No clicks."""
    print("Smoke test: moving the cursor in a small human wander (no clicks).")
    print("Watch your pointer. Ctrl+C to stop.")
    cur = HumanCursor()
    ox, oy = get_pos()
    for _ in range(6):
        cur.move_to(ox + random.randint(-180, 180), oy + random.randint(-120, 120))
        time.sleep(0.3)
    cur.move_to(ox, oy)
    print("Done — that's the model moving the real cursor.")


if __name__ == "__main__":
    _smoke_test()
