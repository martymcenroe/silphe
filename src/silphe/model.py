"""
silphe.model — cross-platform generation of human-fidelity pointer paths.

Pure standard library, no OS calls: this module runs anywhere (Windows, macOS,
Linux). It produces timed waypoints — a list of ``(x, y, dt)`` — that *overshoot*
the target, *correct* with a few shrinking sub-movements, carry a continuous
low-amplitude *tremor*, and end in a heavy-tailed *dwell*. Sampled fresh every
call; never the same path twice.

Drive these waypoints onto the real OS cursor with :mod:`silphe.cursor` (Windows
only), feed them to a GUI, or quantify them with :mod:`silphe.analysis` — the
generation itself is platform-independent.

The motion is deliberately NOT a smooth Bezier curve. It is a ballistic launch
that overshoots, corrective homing hops, physiological micro-tremor, and a
pre-click dwell — the texture a real hand leaves and a straight-line robot never
does.
"""

from __future__ import annotations

import math
import random

# A waypoint is (x_px, y_px, dt_seconds_to_dwell_here).
Waypoint = tuple[float, float, float]

# Movement profile — the knobs that shape a path's "hand". Override any subset
# when constructing a MovementModel; unspecified keys fall back to these.
DEFAULT_PROFILE: dict = {
    "tremor_amp": 2.0,     # px — physiological micro-tremor amplitude
    "tremor_hz": 6.0,      # Hz — tremor frequency
    "dwell_amp": 1.6,      # px — jitter while hovering before a click
    "dwell_mean": 0.18,    # s  — heavy-tailed dwell, centered near ~0.2 s
    "overshoot": (0.02, 0.09),   # ballistic overshoot as a fraction of distance
    "corrections": ([1, 2, 3, 4], [0.25, 0.40, 0.25, 0.10]),  # # of homing hops
    "settle": (0.03, 0.09),      # s — brief pause between hops (the "try again")
    "bow": 0.06,           # max sideways arc as a fraction of segment length
    "speed": 1.0,          # global time multiplier (smaller = faster)
}

# A heavier-tremor profile — wider tremor, longer dwell, more corrective hops.
# Useful for modelling an unsteady hand, or just to *see* the texture exaggerated.
TREMOR_PROFILE: dict = {
    **DEFAULT_PROFILE,
    "tremor_amp": 5.5,
    "tremor_hz": 5.0,
    "dwell_amp": 3.0,
    "dwell_mean": 0.35,
    "corrections": ([2, 3, 4, 5], [0.25, 0.35, 0.25, 0.15]),
}


class MovementModel:
    """Plans human-fidelity pointer paths. Pure and platform-independent.

    Pass a :class:`random.Random` with a fixed seed for reproducible paths
    (handy in tests); leave it out for fresh randomness every run.

        >>> import random
        >>> model = MovementModel(rng=random.Random(0))
        >>> path = model.plan(0, 0, 400, 250)
        >>> abs(path[-1][0] - 400) < 6 and abs(path[-1][1] - 250) < 6
        True
    """

    def __init__(self, profile: dict | None = None, rng: random.Random | None = None):
        self.rng = rng or random.Random()   # no fixed seed in real use
        self.p = {**DEFAULT_PROFILE, **(profile or {})}

    # ---- public API -----------------------------------------------------

    def plan(self, sx: float, sy: float, tx: float, ty: float) -> list[Waypoint]:
        """Return timed waypoints for moving from ``(sx, sy)`` to ``(tx, ty)``."""
        aims = self._aims(sx, sy, tx, ty)
        raw, (cx, cy) = [], (sx, sy)
        for i, (ax, ay) in enumerate(aims):
            raw += self._segment(cx, cy, ax, ay, first=(i == 0))
            cx, cy = ax, ay
            if i < len(aims) - 1:
                raw += self._settle(cx, cy)   # pause before the next correction
        return self._apply_tremor(raw) + self._dwell(tx, ty)

    # ---- path model -----------------------------------------------------

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
