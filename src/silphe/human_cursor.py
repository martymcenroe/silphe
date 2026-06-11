"""
human_cursor.py — the keystone of ADR 0202 (Human-Fidelity Input).

Moves the *real* Windows cursor to a target and issues an OS-level click, so the
event the page sees is `isTrusted: true` — indistinguishable from a physical
mouse. The motion is deliberately NOT a smooth Bezier curve: it is a ballistic
launch that overshoots, a few corrective sub-movements homing in, continuous
low-amplitude tremor, and a pre-click dwell — sampled fresh every call, never
the same path twice.

Pure standard library: ctypes drives Win32 SendInput/SetCursorPos. No pip.

Run it directly for a safe, click-free smoke test (it moves the cursor in a
small wander near where it already is):

    poetry run python talos-mouse-host/human_cursor.py
"""

from __future__ import annotations

import ctypes
import math
import random
import time
from ctypes import wintypes

# --------------------------------------------------------------------------
# Win32 plumbing (stdlib ctypes)
# --------------------------------------------------------------------------

_user32 = ctypes.windll.user32
_winmm = ctypes.windll.winmm

# Make the process DPI-aware so our pixel coordinates match the cursor's.
# This is the coordinate-mapping foot-gun ADR 0202 flags for large/scaled
# displays; setting it here keeps tkinter coords and SetCursorPos in agreement.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE_V2-ish
except Exception:
    try:
        _user32.SetProcessDPIAware()
    except Exception:
        pass

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
INPUT_MOUSE = 0
_PUL = ctypes.POINTER(ctypes.c_ulong)


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _PUL),
    )


class _INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = (("mi", _MOUSEINPUT),)

    _anonymous_ = ("i",)
    _fields_ = (("type", wintypes.DWORD), ("i", _I))


_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT
_user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
_user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)


def get_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def set_pos(x: float, y: float) -> None:
    _user32.SetCursorPos(int(round(x)), int(round(y)))


def _send_flag(flag: int) -> None:
    extra = ctypes.c_ulong(0)
    mi = _MOUSEINPUT(0, 0, 0, flag, 0, ctypes.pointer(extra))
    inp = _INPUT(type=INPUT_MOUSE)
    inp.mi = mi
    _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


# --------------------------------------------------------------------------
# Movement profiles (calibration target: replace DEFAULT with the operator's
# fitted parameters once #187 records real movement)
# --------------------------------------------------------------------------

DEFAULT_PROFILE = {
    "tremor_amp": 2.0,     # px — physiological micro-tremor amplitude
    "tremor_hz": 6.0,      # Hz — slowed per operator feedback ("vibrates too fast")
    "dwell_amp": 1.6,      # px — jitter while hovering before the click
    "dwell_mean": 0.18,    # s  — heavy-tailed dwell, centered near ~0.2 s
    "overshoot": (0.02, 0.09),   # ballistic overshoot as fraction of distance
    "corrections": ([1, 2, 3, 4], [0.25, 0.40, 0.25, 0.10]),  # nudge-overshoot-retry hops
    "settle": (0.03, 0.09),      # s — brief pause between hops (the "try again")
    "bow": 0.06,           # max sideways arc as fraction of segment length
    "speed": 1.0,          # global time multiplier (smaller = faster)
}

# A heavier-tremor profile — a placeholder standing in for the operator's own
# signature (62, a palsy) until real calibration data is fitted in #187.
TREMOR_PROFILE = {
    **DEFAULT_PROFILE,
    "tremor_amp": 5.5,
    "tremor_hz": 5.0,
    "dwell_amp": 3.0,
    "dwell_mean": 0.35,
    "corrections": ([2, 3, 4, 5], [0.25, 0.35, 0.25, 0.15]),
}


class HumanCursor:
    """Generates and drives a human-fidelity cursor path to a screen target."""

    def __init__(self, profile: dict | None = None, rng: random.Random | None = None):
        self.rng = rng or random.Random()  # no fixed seed in real use
        self.p = {**DEFAULT_PROFILE, **(profile or {})}

    # ---- public API -----------------------------------------------------

    def move_to(self, tx: float, ty: float) -> list[tuple[float, float, float]]:
        """Move the real cursor to (tx, ty). Returns the waypoints used."""
        sx, sy = get_pos()
        waypoints = self._plan(sx, sy, tx, ty)
        self._drive(waypoints)
        return waypoints

    def click(self, tx: float, ty: float) -> list[tuple[float, float, float]]:
        """Human-move to (tx, ty), dwell, then issue a trusted OS click."""
        waypoints = self.move_to(tx, ty)
        self._press(tx, ty)
        return waypoints

    # ---- path model (ADR 0202 §4) --------------------------------------

    def _aims(self, sx, sy, tx, ty):
        """Aim points: a ballistic overshoot, then shrinking corrections."""
        rng, p = self.rng, self.p
        dist = math.hypot(tx - sx, ty - sy)
        ang = math.atan2(ty - sy, tx - sx)

        ov = rng.uniform(*p["overshoot"]) * dist
        a1 = ang + rng.uniform(-0.25, 0.25)
        aims = [(tx + math.cos(a1) * ov, ty + math.sin(a1) * ov)]

        n = rng.choices(p["corrections"][0], weights=p["corrections"][1])[0]
        residual = ov
        for _ in range(n):
            residual *= rng.uniform(0.25, 0.5)
            a = rng.uniform(0, 2 * math.pi)
            aims.append((tx + math.cos(a) * residual, ty + math.sin(a) * residual))
        # final settle: essentially on target, sub-pixel imperfect
        aims.append((tx + rng.uniform(-0.7, 0.7), ty + rng.uniform(-0.7, 0.7)))
        return aims

    def _segment(self, x0, y0, x1, y1, first):
        """Timed waypoints for one sub-movement: S-curve position (=> bell
        velocity), a slight randomized sideways bow (NOT a fixed curve)."""
        rng, p = self.rng, self.p
        d = math.hypot(x1 - x0, y1 - y0)
        steps = max(2, min(220, int(d / rng.uniform(6, 12))))
        T = (0.07 + 0.0011 * d) * p["speed"] * rng.uniform(0.8, 1.25)

        # perpendicular unit vector for the bow
        if d > 1e-6:
            px, py = -(y1 - y0) / d, (x1 - x0) / d
        else:
            px = py = 0.0
        bow = rng.uniform(-1, 1) * d * rng.uniform(0.0, p["bow"])
        skew = 0.85 if first else 1.0  # ballistic launch accelerates harder

        seg = []
        for i in range(1, steps + 1):
            t = (i / steps) ** skew
            u = t * t * (3 - 2 * t)  # smoothstep -> bell-shaped speed
            bx = x0 + (x1 - x0) * u + px * bow * math.sin(math.pi * u)
            by = y0 + (y1 - y0) * u + py * bow * math.sin(math.pi * u)
            dt = (T / steps) * rng.uniform(0.75, 1.3)
            seg.append((bx, by, dt))
        return seg

    def _apply_tremor(self, raw):
        """Overlay continuous, non-periodic micro-tremor across the path."""
        rng, p = self.rng, self.p
        amp = p["tremor_amp"]
        w = p["tremor_hz"] * 2 * math.pi
        ph1, ph2 = rng.uniform(0, 2 * math.pi), rng.uniform(0, 2 * math.pi)
        rwx = rwy = 0.0
        out = []
        for (x, y, dt) in raw:
            ph1 += w * dt * rng.uniform(0.85, 1.15)        # frequency drift
            ph2 += w * 1.7 * dt * rng.uniform(0.85, 1.15)  # => no clean period
            rwx = max(-amp, min(amp, rwx + rng.gauss(0, 0.3)))
            rwy = max(-amp, min(amp, rwy + rng.gauss(0, 0.3)))
            ox = amp * math.sin(ph1) + 0.4 * amp * math.sin(ph2) + rwx
            oy = amp * math.cos(ph1 * 1.05) + 0.4 * amp * math.cos(ph2) + rwy
            out.append((x + ox, y + oy, dt))
        return out

    def _dwell(self, tx, ty):
        """Hover-and-jitter around the target before clicking (heavy-tailed)."""
        rng, p = self.rng, self.p
        dur = min(1.0, 0.05 + rng.expovariate(1.0 / p["dwell_mean"]))
        ph = rng.uniform(0, 2 * math.pi)
        out, t = [], 0.0
        while t < dur:
            dt = rng.uniform(0.005, 0.012)
            ph += p["tremor_hz"] * 2 * math.pi * dt * rng.uniform(0.8, 1.2)
            ox = p["dwell_amp"] * math.sin(ph) + rng.gauss(0, 0.6)
            oy = p["dwell_amp"] * math.cos(ph) + rng.gauss(0, 0.6)
            out.append((tx + ox, ty + oy, dt))
            t += dt
        return out

    def _settle(self, x, y):
        """A brief near-still pause between corrective hops — the 'try again'."""
        rng, p = self.rng, self.p
        dur, out, t = rng.uniform(*p["settle"]), [], 0.0
        while t < dur:
            dt = rng.uniform(0.006, 0.013)
            out.append((x + rng.gauss(0, 0.5), y + rng.gauss(0, 0.5), dt))
            t += dt
        return out

    def _plan(self, sx, sy, tx, ty):
        aims = self._aims(sx, sy, tx, ty)
        raw, (cx, cy) = [], (sx, sy)
        for i, (ax, ay) in enumerate(aims):
            raw += self._segment(cx, cy, ax, ay, first=(i == 0))
            cx, cy = ax, ay
            if i < len(aims) - 1:
                raw += self._settle(cx, cy)   # pause before the next correction
        return self._apply_tremor(raw) + self._dwell(tx, ty)

    # ---- driver ---------------------------------------------------------

    def _drive(self, waypoints):
        _winmm.timeBeginPeriod(1)  # 1ms timer resolution for smooth pacing
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
    Exists only so you can SEE what we're refusing to do."""

    def move_to(self, tx, ty):
        sx, sy = get_pos()
        steps = 60
        wp = [(sx + (tx - sx) * i / steps, sy + (ty - sy) * i / steps, 0.5 / steps)
              for i in range(1, steps + 1)]
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


if __name__ == "__main__":
    # Safe smoke test: wander near the current position, NO clicks.
    print("Smoke test: moving the cursor in a small human wander (no clicks).")
    print("Watch your pointer. Ctrl+C to stop.")
    cur = HumanCursor()
    ox, oy = get_pos()
    for _ in range(6):
        cur.move_to(ox + random.randint(-180, 180), oy + random.randint(-120, 120))
        time.sleep(0.3)
    cur.move_to(ox, oy)
    print("Done — that's the keystone moving the real cursor.")
