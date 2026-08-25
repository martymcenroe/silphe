"""
calibrate.py (v2.x) — the green-garden calibration range.

Records how the operator actually moves, across four task types laid over a
GitHub-contribution-graph field of squares:

  ACQUIRE  — click the small gold square (smaller targets + visual clutter)
  TRACK    — follow a slowly-moving dot; it's quick until you lock on, then it
             settles and the clock starts (smooth pursuit)
  HOLD     — hold dead still on a single red pixel inside a white dot (tremor test)
  EVASIVE  — "Andvari": the garden reconfigures into a maze (green = walls) and
             a brood of roaches runs its corridors, ducking under silver
             hide-cells in the blind alleys (they pulse red) and dropping into
             dark tunnels that surface halfway across the field. Gold crumbs
             hold them still while they eat; purple ones are laced, and a
             poisoned roach staggers, dies, and leaves a body the next one
             eats. A gecko turns up late and hunts them too — it scores
             nothing for you. Thump them, several hits each, until the last
             one is down.

Everything stays on your machine (see silphe.analysis.recordings_dir). Each
record is stamped with device + OS + player. ESC quits; progress is saved as
you go. ESC pauses (resume / switch player / quit; ESC again quits). Press P
any time to switch players — the session file closes and a fresh session
starts in that player's own recordings-<name> directory. Rounds score arcade
points; the top 10 land on a local leaderboard shown at the end.

    silphe-play                     # mouse (default), after `pip install silphe`
    silphe-play trackpad            # tag the session as trackpad
    silphe-play --player Rebecca    # skip the player menu, record into recordings-Rebecca
    silphe-play --difficulty hard   # skip the difficulty menu (easy/normal/hard)

Launch asks WHO'S PLAYING unless --player is given, then CHOOSE DIFFICULTY
unless --difficulty is given. Sound effects are ska horn stabs via winsound
(Windows; silent elsewhere). Every plan opens with one of each of
acquire/track/hold before the roach can appear.
"""

from __future__ import annotations

import io
import json
import math
import os
import random
import struct
import sys
import threading
import time
import tkinter as tk
import wave
from collections import deque
from tkinter import simpledialog

from silphe.core import Recorder, known_players, recordings_dir
from silphe.maze import (dead_ends, generate as generate_maze,
                         render as render_maze, tunnels as maze_tunnels)

VERSION = "Andvari"
LEADERBOARD_KEEP = 10
GREENS = ["#0e4429", "#006d32", "#26a641", "#39d353"]
BG = "#0d1117"          # the near-black the window, the canvas and every menu panel share

# Difficulty shapes the motor challenge and the reward: how long you must
# hold/track, how mean the roach is, and the score multiplier. tol_mult
# scales the track lock radius.
DIFFICULTIES = {
    "easy":   {"hold_secs": 1.0, "track_secs": 3.0, "tol_mult": 1.4, "score_mult": 1.0,
               "roach_hp": (3, 4), "roach_speed": 8.0, "roaches": 2},
    "normal": {"hold_secs": 1.2, "track_secs": 4.0, "tol_mult": 1.0, "score_mult": 1.5,
               "roach_hp": (4, 6), "roach_speed": 10.0, "roaches": 3},
    "hard":   {"hold_secs": 1.8, "track_secs": 5.0, "tol_mult": 0.7, "score_mult": 2.0,
               "roach_hp": (6, 8), "roach_speed": 13.0, "roaches": 3},
}


def make_plan() -> list[str]:
    """Round plan: 4 acquire, 3 track, 3 hold, 2 evasive — but the opener is
    one of each basic type in random order, so every player is sampled on
    acquire/track/hold before the roach ever shows up."""
    opener = ["acquire", "track", "hold"]
    random.shuffle(opener)
    rest = ["acquire"] * 3 + ["track"] * 2 + ["hold"] * 2 + ["evasive"] * 2
    random.shuffle(rest)
    return opener + rest


# ---- ska horn section (stdlib synthesis; silent no-op off Windows) ---------
# (freq_hz, ms) pairs; freq 0 = rest. Offbeat rests before the stabs are what
# make it skank instead of just beep.
SKA_RIFFS = {
    "hit":    [(0, 30), (932, 45), (1245, 60)],                    # upstroke double-stab
    "miss":   [(233, 90), (0, 40), (220, 150)],                    # trombone slump
    "squash": [(622, 50), (932, 50), (1245, 50), (0, 30), (1865, 90)],  # horn run
    "board":  [(466, 70), (0, 50), (932, 70), (0, 50), (466, 70),
               (0, 50), (932, 70), (0, 50), (1397, 90), (1245, 90), (1865, 200)],
}

SAMPLE_RATE = 22050
VOLUME = 0.35            # headroom on purpose: a stab that clips sounds worse than a quiet one
ATTACK_SECS = 0.006      # short enough to read as a stab, long enough not to click
DECAY_PER_SEC = 9.0      # how fast a note falls away; this is what stops it being a tone

# Rendered riffs, kept for the life of the process. Two reasons: synthesis is a
# per-sample Python loop and has no business running inside the game loop
# twice, and SND_ASYNC hands Windows a buffer it goes on reading after the call
# returns — a buffer that gets collected plays as garbage (#83).
_RIFF_WAVS: dict[str, bytes] = {}

# Sound is never worth crashing a game over, but it should not be able to fail
# in silence either — that is indistinguishable from a game choosing to be
# quiet, and it is what made the silence in #82 take a diagnostic to narrow
# down. Say it once, then stop: a warning per hit is worse than the silence
# it reports (#84).
_sound_off = False
_sound_reported = False


def _sound_unavailable(reason: str, expected: bool = False) -> None:
    global _sound_off, _sound_reported
    _sound_off = True
    if not _sound_reported:
        _sound_reported = True
        note = "no sound" if expected else "SOUND FAILED"
        print(f"silphe: {note} — {reason}", file=sys.stderr)


def render_riff(seq, rate: int = SAMPLE_RATE, volume: float = VOLUME) -> bytes:
    """One riff as a 16-bit mono WAV, notes and rests together in one buffer.

    Rendered whole rather than note by note because PlaySound plays exactly one
    sound at a time — a second call stops the first, so a riff issued a note at
    a time would cut itself off at every step.

    The shape of a note is what separates a horn stab from a beep: a couple of
    harmonics over the fundamental, a fast attack, and an exponential decay.
    """
    frames = bytearray()
    for freq, ms in seq:
        n = int(rate * ms / 1000)
        if not freq:
            frames += bytes(2 * n)                         # a rest is silence, not nothing
            continue
        for i in range(n):
            t = i / rate
            env = min(1.0, t / ATTACK_SECS) * math.exp(-t * DECAY_PER_SEC)
            wave_ = (math.sin(2 * math.pi * freq * t)
                     + 0.5 * math.sin(4 * math.pi * freq * t)
                     + 0.25 * math.sin(6 * math.pi * freq * t)) / 1.75
            frames += struct.pack("<h", int(volume * env * wave_ * 32767))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


def ska(event: str):
    """Fire-and-forget a riff on a daemon thread.

    The thread is not optional. `winsound` refuses `SND_MEMORY | SND_ASYNC`
    outright — "Cannot play asynchronously from memory" — because it cannot
    guarantee the buffer outlives the call, so playing from memory blocks for
    the length of the riff. What did change from the Beep this replaces is that
    it blocks once per riff rather than once per note.

    Rendering happens on the thread too, so the game loop never pays for the
    first hit of a session.

    Returns the thread, which callers ignore and tests wait on — the
    alternative is a test that sleeps and hopes.
    """
    if _sound_off:
        return None
    seq = SKA_RIFFS.get(event)
    if not seq:
        return None
    try:
        import winsound
    except ImportError:
        _sound_unavailable(f"winsound is Windows-only, this is {sys.platform}",
                           expected=True)
        return None

    def run():
        try:
            wav = _RIFF_WAVS.get(event)
            if wav is None:
                wav = _RIFF_WAVS[event] = render_riff(seq)
            winsound.PlaySound(wav, winsound.SND_MEMORY)
        except Exception as exc:
            _sound_unavailable(f"{type(exc).__name__}: {exc}")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def round_score(obj: dict) -> int:
    """Arcade score for one saved round. Derived only from what the round
    already measured — accuracy pays, not speed of the machine."""
    kind = obj.get("kind")
    if kind == "acquire":
        err = obj.get("click", {}).get("err", 1e9)
        r = obj.get("target", {}).get("r", 15)
        if err > r * 1.4:                                  # a miss scores nothing
            return 0
        return max(10, 100 - int(2 * err))
    if kind == "track":
        return int(obj.get("on_target_pct", 0))
    if kind == "hold":
        return 100
    if kind == "evasive":
        # Only the player's own swats pay. Poison and the gecko take roaches
        # too, and those are not the player's work. Records written before
        # anything else could kill a roach have no `player_hits`, and for them
        # `hits` is the same number.
        return 25 * int(obj.get("player_hits", obj.get("hits", 0)))
    return 0


def leaderboard_path() -> str:
    """The high-score table lives next to the recordings tree (local-first,
    shared by every player on this machine)."""
    return os.path.join(os.path.dirname(os.path.abspath(recordings_dir())),
                        "leaderboard.json")


def board_qualifies(path: str, score: int) -> bool:
    """Would *score* land on the top-LEADERBOARD_KEEP table?"""
    if score <= 0:
        return False
    try:
        with open(path, encoding="utf-8") as f:
            board = [r for r in json.load(f) if isinstance(r, dict)]
    except Exception:
        return True                                        # empty/corrupt board: anything lands
    if len(board) < LEADERBOARD_KEEP:
        return True
    return score > min(int(r.get("score", 0)) for r in board)


def default_initials(name: str) -> str:
    """Prefill for the initials screen: first three letters of the player
    name, uppercased; AAA when the name has none."""
    letters = "".join(ch for ch in name.upper() if "A" <= ch <= "Z")
    return letters[:3] or "AAA"


def bests_path() -> str:
    """Per-player personal bests live next to the leaderboard."""
    return os.path.join(os.path.dirname(os.path.abspath(recordings_dir())),
                        "personal-bests.json")


def personal_best(path: str, name: str) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            return int(json.load(f).get(name, {}).get("score", 0))
    except Exception:
        return 0


def update_personal_best(path: str, name: str, score: int,
                         when: str | None = None) -> tuple[int, bool]:
    """Record *score* if it beats *name*'s best. Returns (best, is_new)."""
    data: dict = {}
    try:
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            data = loaded
    except Exception:
        pass
    prev = int(data.get(name, {}).get("score", 0))
    if score <= prev:
        return prev, False
    data[name] = {"score": int(score), "date": when or time.strftime("%Y-%m-%d")}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    return int(score), True


def update_leaderboard(path: str, name: str, score: int, when: str | None = None) -> list[dict]:
    """Insert an entry, keep the top LEADERBOARD_KEEP by score, persist, and
    return the board. A corrupt or missing file starts a fresh board."""
    board: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, list):
            board = [r for r in loaded if isinstance(r, dict)]
    except Exception:
        pass
    board.append({"name": name, "score": int(score),
                  "date": when or time.strftime("%Y-%m-%d")})
    board = sorted(board, key=lambda r: -int(r.get("score", 0)))[:LEADERBOARD_KEEP]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(board, f, indent=1)
    return board


class Garden:
    # How much closer (px) another roach has to be before the record calls it a
    # target switch. A cursor drifting between two of them is not a decision.
    ENGAGE_MARGIN = 25.0

    # Crumbs. A roach that smells one inside BAIT_RANGE cells breaks off its
    # evasion to go and eat, and stands still for FEED_SECS with its head down —
    # which is the whole point, because a baited roach and a bolting one are two
    # different things to chase.
    MAX_BAIT = 2
    BAIT_EVERY = (3.0, 6.0)
    BAIT_RANGE = 6
    FEED_SECS = (1.0, 1.8)

    # Tunnels. A roach bolting over a mouth usually drops in and surfaces at the
    # far end, which is halfway across the field — so you lose it, and have to
    # work out where it comes up.
    TUNNEL_PAIRS = 2
    TUNNEL_SECS = (0.6, 1.2)
    TUNNEL_ODDS = 0.7

    # Poison, and the domino it starts. A roach that finishes a poisoned crumb
    # sickens, slows, staggers and dies — and its corpse is itself poisoned
    # bait, so the next roach to eat it goes the same way. That horizontal
    # transfer is the whole trick of a real gel bait like Advion.
    POISON_ODDS = 0.4
    SICK_SPEED = 0.55
    SICK_SECS = (3.0, 6.0)

    # The gecko. Ambient hazard and theatre — it hunts the same roaches and
    # they run from it as they run from you, but only your own swats score.
    # Its pursuit is also a robot chasing a robot, which is a movement sample
    # no human hand produced.
    GECKO_AFTER = 6.0
    GECKO_SPEED = 7.0
    GECKO_REACH = 12.0

    def __init__(self, root: tk.Tk, device: str = "mouse", player: str | None = None,
                 difficulty: str | None = None):
        self.root = root
        root.title(f"The Ministry of Silly Mice — {VERSION}")
        root.configure(bg=BG)
        self.W, self.H = 1200, 760
        self.canvas = tk.Canvas(root, width=self.W, height=self.H,
                                bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.CELL, self.GAP, self.COLS, self.ROWS = 30, 6, 30, 15
        gw = self.COLS * (self.CELL + self.GAP) - self.GAP
        gh = self.ROWS * (self.CELL + self.GAP) - self.GAP
        self.ox, self.oy = (self.W - gw) // 2, (self.H - gh) // 2 + 12

        self.device = device.lower()
        self.player = player
        self.recorder = Recorder(device=self.device, player=self.player)

        self.cells, self.base = {}, {}
        self._draw_field()

        self.plan = self._make_plan()
        self.i = 0
        self.state = "idle"
        self.samples = []
        self.t0 = 0.0
        self.first_move = None
        self.last = (self.W // 2, self.H // 2)
        self.target = None
        self.inside_since = None
        self.hides = set()
        self.walls = set()
        self.maze_base = {}
        self.roaches = []
        self.engaged = None
        self.baits, self.bait_log = {}, []
        self.next_bait = 0.0
        self.tunnels = {}
        self.gecko = None
        self.tool = "swatter"
        self.tool_switches = []
        self.target_switches = []
        self.path = []
        self.hit_n = 0
        self.score = 0
        self._menu_buttons = []

        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Button-1>", self._click)
        root.bind("<Escape>", self._pause)
        root.bind("t", self._switch_tool)
        root.bind("T", self._switch_tool)
        root.bind("p", self._switch_player)
        root.bind("P", self._switch_player)
        root.bind("<Key>", self._initials_key)
        self.difficulty = difficulty if difficulty in DIFFICULTIES else None
        self.diff = DIFFICULTIES[self.difficulty or "normal"]
        if player is None:
            self._draw_launch_player_menu()                 # ask before anything is recorded
        else:
            self._after_launch_player()

    # ---- difficulty ------------------------------------------------------

    def _draw_difficulty_menu(self):
        self.state = "difficulty_menu"
        self._menu("CHOOSE DIFFICULTY",
                   [(k.upper(), lambda k=k: self._choose_difficulty(k))
                    for k in DIFFICULTIES])

    def _choose_difficulty(self, name: str):
        self.difficulty = name
        self.diff = DIFFICULTIES[name]
        self.canvas.delete("menu")
        self.state = "idle"
        self._next()

    # ---- players ---------------------------------------------------------

    def _switch_player(self, e=None):
        if self.state == "initials" and e is not None:
            return self._initials_key(e)                    # P is a letter here, not the switch
        if self.state in ("done", "paused", "player_menu", "launch_player_menu",
                          "difficulty_menu", "initials"):
            return
        self._new_player()

    def _choose_player(self, name: str | None):
        if name == self.player:
            return self._resume()
        self.recorder.close()
        self.player = name
        self.recorder = Recorder(device=self.device, player=self.player)
        self.canvas.delete("menu")
        self.state = "idle"
        self.plan = self._make_plan()                      # fresh session for the new hand
        self.i = 0
        self.score = 0
        self._next()

    def _new_player(self, e=None, then=None):
        name = simpledialog.askstring(
            "Switch player", "Player name (blank = default player):", parent=self.root)
        if name is None:                                   # cancelled
            return
        name = "".join(ch for ch in name.strip() if ch.isalnum() or ch in "-_") or None
        (then or self._choose_player)(name)

    # ---- who's playing, at launch ----------------------------------------
    # The mid-session switch above closes the recorder, reshuffles the plan and
    # resets the score, because it is abandoning a session for a new hand. At
    # launch there is nothing to abandon, so this path only settles who is
    # playing and moves on to the difficulty menu (#75).

    def _draw_launch_player_menu(self):
        self.state = "launch_player_menu"
        entries = [(n, lambda n=n: self._choose_launch_player(n)) for n in known_players()[:7]]
        entries.append(("NEW PLAYER...", lambda: self._new_player(then=self._choose_launch_player)))
        entries.append(("PLAY AS DEFAULT", lambda: self._choose_launch_player(None)))
        self._menu("WHO'S PLAYING?", entries)

    def _choose_launch_player(self, name: str | None):
        if name != self.player:
            self.recorder.close()
            self.player = name
            self.recorder = Recorder(device=self.device, player=self.player)
        self.canvas.delete("menu")
        self._after_launch_player()

    def _after_launch_player(self):
        """Who is playing is settled; --difficulty may still skip the next menu."""
        if self.difficulty:
            self.state = "idle"
            self._next()
        else:
            self._draw_difficulty_menu()

    # ---- pause menu (ESC) ------------------------------------------------

    def _menu(self, title, entries):
        """Draw a clickable menu. entries = [(label, callback), ...]."""
        self._restore()
        self.canvas.delete("hud", "menu")
        self._menu_buttons = []
        self.canvas.create_text(self.W // 2, self.H // 2 - 150, text=title,
                                fill="#e3b341", font=("Consolas", 26, "bold"), tag="menu")
        for j, (label, cb) in enumerate(entries):
            y = self.H // 2 - 80 + j * 52
            self.canvas.create_rectangle(self.W // 2 - 160, y - 19, self.W // 2 + 160, y + 19,
                                         fill=BG, outline="#39d353", width=2, tag="menu")
            self.canvas.create_text(self.W // 2, y, text=label, fill="#f0f6fc",
                                    font=("Consolas", 13, "bold"), tag="menu")
            self._menu_buttons.append((self.W // 2 - 160, y - 19, self.W // 2 + 160, y + 19, cb))

    def _pause(self, e=None):
        if self.state in ("done", "difficulty_menu", "launch_player_menu", "initials"):
            return
        if self.state == "paused":                         # ESC twice = quit
            return self._quit()
        if self.state == "player_menu":                    # ESC backs out to pause
            return self._draw_pause()
        self._draw_pause()                                 # abandons the round; no partial record

    def _draw_pause(self):
        self.state = "paused"
        who = self.player or "default"
        best = personal_best(bests_path(), who)
        self._menu("PAUSED", [
            (f"RESUME  ({who} · {self.score} pts · best {best})", self._resume),
            ("SWITCH PLAYER", self._draw_player_menu),
            ("QUIT", self._quit),
        ])

    def _draw_player_menu(self):
        self.state = "player_menu"
        entries = [("default", lambda: self._choose_player(None))]
        entries += [(n, lambda n=n: self._choose_player(n)) for n in known_players()[:7]]
        entries.append(("NEW PLAYER...", self._new_player))
        entries.append(("BACK", self._draw_pause))
        self._menu("WHO'S PLAYING?", entries)

    def _resume(self):
        self.canvas.delete("menu")
        self.state = "idle"
        self._next()                                       # replays the abandoned round

    def _quit(self):
        self.canvas.delete("menu")
        self._finish()

    # ---- geometry / field ----------------------------------------------

    def _cell_xy(self, r, c):
        return self.ox + c * (self.CELL + self.GAP), self.oy + r * (self.CELL + self.GAP)

    def _center(self, r, c):
        x0, y0 = self._cell_xy(r, c)
        return x0 + self.CELL / 2, y0 + self.CELL / 2

    def _draw_field(self):
        for r in range(self.ROWS):
            for c in range(self.COLS):
                x0, y0 = self._cell_xy(r, c)
                col = random.choice(GREENS) if random.random() < 0.16 else "#161b22"
                self.cells[(r, c)] = self.canvas.create_rectangle(
                    x0, y0, x0 + self.CELL, y0 + self.CELL, fill=col, outline=BG)
                self.base[(r, c)] = col

    def _paint_field(self):
        """The garden as planted — the scatter every non-roach round sits on."""
        for rc, item in self.cells.items():
            self.canvas.itemconfig(item, fill=self.base[rc])

    def _paint_maze(self):
        """Reconfigure the garden into this round's maze. Walls keep the
        contribution-graph greens, so it still reads as the same garden. The
        colours are kept because mid-round repaints (a burnt-out hide-hole)
        have to go back to the maze, not to the garden underneath it."""
        self.maze_base = {}
        for rc, item in self.cells.items():
            col = random.choice(GREENS) if rc in self.walls else "#161b22"
            self.canvas.itemconfig(item, fill=col)
            self.maze_base[rc] = col

    def _pick(self):
        return random.randint(0, self.ROWS - 1), random.randint(0, self.COLS - 1)

    # ---- flow -----------------------------------------------------------

    def _make_plan(self):
        return make_plan()

    def _hud(self, msg, color="#8b949e", sub=None):
        self.canvas.delete("hud")
        self.canvas.create_text(self.W // 2, 22, text=msg, fill=color, tag="hud",
                                font=("Consolas", 15, "bold"))
        who = self.player or "default"
        self.canvas.create_text(70, 22, text=f"{self.score:06d}", fill="#e3b341",
                                tag="hud", font=("Consolas", 14, "bold"))
        self.canvas.create_text(self.W // 2, self.H - 12, fill="#6e7681", tag="hud",
                                font=("Consolas", 10),
                                text=f"round {min(self.i + 1, len(self.plan))}/{len(self.plan)}"
                                     f"   ·   player: {who} (P to switch)"
                                     f"   ·   {self.difficulty or 'normal'}"
                                     f"   ·   ESC to stop (saved as you go)")
        if sub:
            self.canvas.create_text(self.W // 2, 46, fill="#6e7681", tag="hud",
                                    font=("Consolas", 11), text=sub)

    def _toast(self, rc, text, good):
        cx, cy = self._center(*rc)
        self._toast_xy(cx, cy, text, good)

    def _toast_xy(self, x, y, text, good):
        ska("squash" if text == "SQUASHED" else ("hit" if good else "miss"))
        self.canvas.delete("toast")                       # only the latest message — no more clogging
        tid = self.canvas.create_text(x, y - self.CELL, text=text, tags=("toast",),
                                      fill="#39d353" if good else "#f85149",
                                      font=("Consolas", 12, "bold"))
        self.root.after(700, lambda: self.canvas.delete(tid))

    def _hit_mark(self, x, y, n):                          # persistent numbered hit — stays for the round
        self.canvas.create_oval(x - 8, y - 8, x + 8, y + 8, outline="#f0f6fc", width=1, tag="hitmark")
        self.canvas.create_text(x, y, text=str(n), fill="#f0f6fc",
                                font=("Consolas", 9, "bold"), tag="hitmark")

    def _restore(self):
        self._paint_field()                                # undoes targets, hides and any maze
        self.hides = set()
        self.walls = set()
        self.maze_base = {}
        self.roaches = []
        self.engaged = None
        self.baits = {}
        self.tunnels = {}
        self.gecko = None
        self.canvas.delete("mark", "ring", "dot", "roach", "tool", "toast",
                           "hitmark", "bait", "tunnel", "gecko")

    def _next(self):
        self._restore()
        self.canvas.delete("hud")
        if self.i >= len(self.plan):
            return self._finish()
        self.samples, self.t0 = [], time.perf_counter()
        self.first_move, self.inside_since = None, None
        getattr(self, "_begin_" + self.plan[self.i])()

    # ---- recording ------------------------------------------------------

    def _motion(self, e):
        self.last = (e.x, e.y)
        if self.state in ("acquire", "track", "hold", "evasive"):
            t = time.perf_counter() - self.t0
            self.samples.append((round(t, 4), e.x, e.y))
            if self.first_move is None:
                self.first_move = t

    def _save(self, obj):
        obj["difficulty"] = self.difficulty or "normal"
        obj["score"] = int(round_score(obj) * self.diff["score_mult"])
        self.score += obj["score"]
        self.recorder.write(obj)   # kernel stamps schema_version, device, os, player

    def _save_evasive(self):
        """The whole round: what the player chased, what each roach did on its
        own, and when their attention moved between them.

        `path` stays exactly what it has always been — the trace of the target
        being pursued — which is what pursuit lag is measured against. With one
        roach that is the only roach; with several it follows the player's
        attention, so the measurement keeps its meaning instead of correlating
        a cursor against a roach nobody was chasing. The field layout rides
        along too: anticipating a corner and reacting in the open are different
        measurements, and the trace alone cannot tell them apart. So is each
        roach's mode timeline, because chasing something drawn to a crumb and
        chasing something bolting from you are also different measurements."""
        self._save({"kind": "evasive",
                    "hits": sum(tg["hp0"] for tg in self.roaches),
                    "player_hits": self.hit_n,
                    "switches": self.tool_switches,
                    "target_switches": self.target_switches,
                    "bait": self.bait_log,
                    "gecko": None if self.gecko is None else
                             {"arrived": self.gecko["arrived"],
                              "path": self.gecko["path"],
                              "kills": self.gecko["kills"]},
                    "roaches": [{"id": tg["id"], "hp0": tg["hp0"], "path": tg["path"],
                                 "modes": tg["modes"], "tunnels": tg["tunnels"],
                                 "sickened_at": tg["sickened_at"], "died": tg["died"]}
                                for tg in self.roaches],
                    "reaction_s": round(self.first_move or 0, 4),
                    "path": self.path, "samples": self.samples,
                    "maze": render_maze(self.walls, self.ROWS, self.COLS)})

    # ---- ACQUIRE --------------------------------------------------------

    def _begin_acquire(self):
        rc = self._pick()
        cx, cy = self._center(*rc)
        self.target = {"cell": rc, "x": cx, "y": cy, "r": self.CELL / 2}
        self.canvas.itemconfig(self.cells[rc], fill="#e3b341")
        self._hud("Click the GOLD square.", "#e3b341",
                  sub="small target, in the weeds — find it and hit it")
        self.state = "acquire"

    # ---- TRACK (follow the slowly-moving dot) --------------------------

    def _begin_track(self):
        sq = 90
        x0 = random.randint(self.ox + 20, self.W - 20 - sq)
        y0 = random.randint(72, self.H - 64 - sq)
        cx, cy = x0 + sq / 2, y0 + sq / 2
        self.target = {
            "x0": x0, "y0": y0, "sq": sq, "cx": cx, "cy": cy,
            "rd": sq / 8, "tol": (sq / 8 + 5) * self.diff["tol_mult"],  # dot = 1/4 the square's width
            "w1": 2 * math.pi * 0.18, "w2": 2 * math.pi * 0.13,   # slow, incommensurate -> smooth wander
            "ph1": random.uniform(0, 6.28), "ph2": random.uniform(0, 6.28),
            "locked": False, "lock_t": 0.0, "last_tick": time.perf_counter(),
            "dot": [], "on": 0, "tot": 0,
        }
        self.canvas.create_rectangle(x0, y0, x0 + sq, y0 + sq,
                                     fill="#241a3d", outline="#a371f7", width=2, tag="mark")
        self.canvas.create_oval(0, 0, 0, 0, fill="#d2a8ff", outline="", tag="dot")
        self._hud("Catch the moving dot to start.", "#a371f7",
                  sub="it's quick until you lock on — then it settles and the clock runs")
        self.state = "track"
        self._track_tick()

    def _track_tick(self):
        if self.state != "track":
            return
        tg = self.target
        now = time.perf_counter()
        dt = now - tg["last_tick"]
        tg["last_tick"] = now
        sf = 1.0 if tg["locked"] else 2.4                 # fast until you lock on
        tg["ph1"] += tg["w1"] * dt * sf
        tg["ph2"] += tg["w2"] * dt * sf
        amp = tg["sq"] / 2 - tg["rd"] - 3
        dx = tg["cx"] + amp * math.sin(tg["ph1"])
        dy = tg["cy"] + amp * math.sin(tg["ph2"])
        rd = tg["rd"]
        self.canvas.coords("dot", dx - rd, dy - rd, dx + rd, dy + rd)
        tg["dot"].append((round(now - self.t0, 4), round(dx, 1), round(dy, 1)))
        x, y = self.last
        on = math.hypot(x - dx, y - dy) <= tg["tol"]
        self.canvas.itemconfig("dot", fill="#39d353" if on else "#d2a8ff")

        if not tg["locked"]:
            if on:
                tg["locked"], tg["lock_t"] = True, now
                self._hud("Locked — now STAY on it.", "#39d353", sub="follow it as it drifts")
            return self.root.after(16, self._track_tick)

        tg["tot"] += 1
        tg["on"] += 1 if on else 0
        el = now - tg["lock_t"]
        self.canvas.delete("ring")
        self.canvas.create_rectangle(tg["x0"], tg["y0"] + tg["sq"] + 6,
                                     tg["x0"] + tg["sq"] * min(1.0, el / self.diff["track_secs"]),
                                     tg["y0"] + tg["sq"] + 10, fill="#a371f7", outline="", tag="ring")
        if el >= self.diff["track_secs"]:
            pct = round(100 * tg["on"] / max(1, tg["tot"]))
            self._save({"kind": "track", "square": {"x": tg["x0"], "y": tg["y0"], "size": tg["sq"]},
                        "reaction_s": round(self.first_move or 0, 4),
                        "locked_at": round(tg["lock_t"] - self.t0, 4),
                        "on_target_pct": pct, "dot": tg["dot"], "samples": self.samples})
            self.canvas.delete("dot")
            self._hud(f"Tracked - {pct}% glued to it.", "#39d353")
            self.state = "idle"
            self.i += 1
            return self.root.after(800, self._next)
        self.root.after(16, self._track_tick)

    # ---- HOLD (single red pixel — the tremor test) ---------------------

    def _begin_hold(self):
        rc = self._pick()
        cx, cy = self._center(*rc)
        self.target = {"cell": rc, "x": cx, "y": cy, "r": 5.0}
        self.canvas.itemconfig(self.cells[rc], fill="#1f6feb")
        self.canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5,
                                outline="#f0f6fc", width=1, tag="mark")
        self.canvas.create_rectangle(cx, cy, cx + 1, cy + 1,
                                     fill="#ff3b30", outline="", tag="mark")
        self._hud("Hold STEADY on the single red pixel.", "#ff7b72",
                  sub="one pixel, inside the white dot — your hand vs the mouse's inertia")
        self.state = "hold"
        self._dwell_tick("hold", self.diff["hold_secs"], "STEADY")

    def _dwell_tick(self, kind, secs, ok_text):
        if self.state != kind:
            return
        cx, cy, tol = self.target["x"], self.target["y"], self.target["r"]
        x, y = self.last
        now = time.perf_counter()
        self.canvas.delete("ring")
        if math.hypot(x - cx, y - cy) <= tol:
            if self.inside_since is None:
                self.inside_since = now
            frac = min(1.0, (now - self.inside_since) / secs)
            rr = tol + 9
            self.canvas.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=90,
                                   extent=-360 * frac, style="arc",
                                   outline="#39d353", width=3, tag="ring")
            if now - self.inside_since >= secs:
                self._save({"kind": kind, "target": {"x": cx, "y": cy, "r": tol},
                            "reaction_s": round(self.first_move or 0, 4),
                            "samples": self.samples})
                self._toast(self.target["cell"], ok_text, True)
                self.state = "idle"
                self.i += 1
                return self.root.after(700, self._next)
        else:
            self.inside_since = None
        self.root.after(20, lambda: self._dwell_tick(kind, secs, ok_text))

    # ---- EVASIVE: "Andvari" — the Pac-Man maze roach ------------------

    def _begin_evasive(self):
        self.walls = generate_maze(self.ROWS, self.COLS)
        self._paint_maze()
        paths = [rc for rc in self.cells if rc not in self.walls]
        # Tunnels first — their mouths must sit on plain open ground, so they
        # claim their cells before anything else can.
        self.tunnels = {}
        for mouth, far in maze_tunnels(self.walls, self.ROWS, self.COLS,
                                       pairs=self.TUNNEL_PAIRS):
            self.tunnels[mouth], self.tunnels[far] = far, mouth
        for rc in self.tunnels:
            self._draw_tunnel(rc)
        # Hide-holes belong in the blind alleys — cornering it in a crevice is
        # what the maze is for. Top up from open ground when the field braided
        # most of its dead ends away.
        crevices = [rc for rc in dead_ends(self.walls, self.ROWS, self.COLS)
                    if rc not in self.tunnels]
        random.shuffle(crevices)
        hides = crevices[:5]
        spare = [rc for rc in paths if rc not in set(hides) and rc not in self.tunnels]
        hides += random.sample(spare, min(5 - len(hides), len(spare)))
        self.hides = set(hides)
        for rc in self.hides:
            self.canvas.itemconfig(self.cells[rc], fill="#b1bac4")   # silver hide-holes
        open_ground = [rc for rc in paths if rc not in self.hides
                       and rc not in self.tunnels] or paths
        now = time.perf_counter()
        count = min(self.diff["roaches"], len(open_ground))
        self.roaches = [self._hatch(i, cell, now) for i, cell
                        in enumerate(random.sample(open_ground, count))]
        self.target = None                                 # each roach carries its own state
        self.engaged = None
        self.tool = "swatter"
        self.tool_switches, self.target_switches = [], []
        self.path, self.hit_n = [], 0
        self.baits, self.bait_log = {}, []
        self.next_bait = now + random.uniform(*self.BAIT_EVERY)
        self.gecko = None
        quarry = "the roach" if count == 1 else f"all {count} roaches"
        self._hud(f"ANDVARI — hunt {quarry}.", "#d29922",
                  sub="SWATTER for a runner, T for the PICK; gold crumbs feed them and "
                      "purple ones kill them, dark holes come up somewhere else")
        self.state = "evasive"
        self._show_tool()
        self._roach_tick()

    def _hatch(self, idx, cell, now):
        """One roach on *cell*, running its own evasion from everyone else's."""
        cx, cy = self._center(*cell)
        health = random.randint(*self.diff["roach_hp"])
        return {"id": idx, "cell": cell, "to": cell, "from": None, "prog": 1.0,
                "px": cx, "py": cy, "heading": (cx, cy, cx, cy),
                "health": health, "hp0": health, "speed": self.diff["roach_speed"],
                "hidden": False, "hide_cell": None, "burst_until": 0.0,
                "pause_until": 0.0, "want_hide": False, "last": now,
                "bait_cell": None, "feed_until": 0.0, "mode": None, "modes": [],
                "under": False, "tunnel_until": 0.0, "tunnel_exit": None,
                "tunnels": [], "path": [], "dead": False,
                "sick": False, "sickened_at": None, "dies_at": 0.0, "died": None}

    def _live(self):
        return [tg for tg in self.roaches if not tg["dead"]]

    def _switch_tool(self, e=None):
        if self.state == "initials" and e is not None:
            return self._initials_key(e)                    # T is a letter here, not the tool swap
        if self.state != "evasive":
            return
        self.tool = "pick" if self.tool == "swatter" else "swatter"
        self.tool_switches.append((round(time.perf_counter() - self.t0, 4), self.tool))
        self._show_tool()

    def _show_tool(self):
        self.canvas.delete("tool")
        if self.state != "evasive":
            return
        name = "SWATTER" if self.tool == "swatter" else "PICK (sharp)"
        self.canvas.create_text(self.W - 120, 22, text=f"[T] tool: {name}", fill="#e3b341",
                                tag="tool", font=("Consolas", 12, "bold"))

    def _neighbors(self, rc):
        r, c = rc
        out = []
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (r + dr, c + dc)
            if 0 <= nb[0] < self.ROWS and 0 <= nb[1] < self.COLS and nb not in self.walls:
                out.append(nb)
        return out

    def _wander(self, rc, mx, my, fleeing, came_from=None, sick=False):
        nb = self._neighbors(rc)
        if not nb:
            return rc
        if sick:
            # Poisoned: it staggers. No sense of direction left, not even
            # enough to keep running the way it was already going.
            return random.choice(nb)
        if fleeing:
            # Bolting, it takes whatever puts the most floor between it and the
            # cursor — including straight back past you when you've cut it off.
            return max(nb, key=lambda cell: math.hypot(self._center(*cell)[0] - mx,
                                                       self._center(*cell)[1] - my))
        # Ambling, it runs the corridor instead of dithering in it. Mid-corridor
        # the only choices are onward or back the way it came, and a roach that
        # coin-flips between them just vibrates on the spot; it turns around
        # only where the corridor genuinely ends.
        onward = [cell for cell in nb if cell != came_from]
        return random.choice(onward or nb)

    def _toward(self, rc, goal):
        """The next cell on the shortest path through the maze. Greedy
        manhattan steps walk straight into the blind alleys the maze is built
        from, so this follows the corridors properly."""
        if goal is None or goal == rc:
            return None
        prev = {rc: None}
        queue = deque([rc])
        while queue:
            cur = queue.popleft()
            if cur == goal:
                break
            for nb in self._neighbors(cur):
                if nb not in prev:
                    prev[nb] = cur
                    queue.append(nb)
        if goal not in prev:
            return None
        step = goal
        while prev[step] != rc:
            step = prev[step]
        return step

    def _nearest_hide(self, rc):
        if not self.hides:
            return None
        return min(self.hides, key=lambda h: abs(h[0] - rc[0]) + abs(h[1] - rc[1]))

    def _draw_roaches(self):
        self.canvas.delete("roach")
        for tg in self._live():
            if not tg["hidden"] and not tg["under"]:
                self._draw_roach(tg)

    def _draw_roach(self, tg):
        ax, ay, bx, by = tg["heading"]
        x, y = tg["px"], tg["py"]
        ang = math.atan2(by - ay, bx - ax) if (bx != ax or by != ay) else 0.0
        body = "#a9712f" if tg["health"] < tg["hp0"] else "#6e4b1f"
        self.canvas.create_oval(x - 8, y - 5, x + 8, y + 5, fill=body, outline="#3d2b12", tag="roach")
        dx, dy = math.cos(ang), math.sin(ang)
        px, py = -dy, dx
        self.canvas.create_line(x + dx * 7, y + dy * 7, x + dx * 15 - px * 4, y + dy * 15 - py * 4,
                                fill="#3d2b12", width=2, tag="roach")
        self.canvas.create_line(x + dx * 7, y + dy * 7, x + dx * 15 + px * 4, y + dy * 15 + py * 4,
                                fill="#3d2b12", width=2, tag="roach")
        self.canvas.create_text(x, y - 14, text="•" * tg["health"], fill="#f85149",
                                font=("Consolas", 9, "bold"), tag="roach")

    def _quarry(self, now, mx, my):
        """Whichever roach the player is going for. A roach that has ducked
        into a hole still counts — waiting over the hole it vanished into is
        part of the pursuit, not a break in it.

        The hysteresis is what makes this a measurement rather than noise: a
        cursor sitting midway between two roaches would otherwise flap the
        record back and forth every frame, and a switch is only a switch if
        the player actually committed to the other one.
        """
        live = self._live()
        if not live:
            return None
        pick = min(live, key=lambda tg: math.hypot(mx - tg["px"], my - tg["py"]))
        held = next((tg for tg in live if tg["id"] == self.engaged), None)
        if held is not None and held is not pick:
            gain = (math.hypot(mx - held["px"], my - held["py"])
                    - math.hypot(mx - pick["px"], my - pick["py"]))
            if gain < self.ENGAGE_MARGIN:
                pick = held
        if pick["id"] != self.engaged:
            self.engaged = pick["id"]
            self.target_switches.append((round(now - self.t0, 4), pick["id"]))
        return pick

    # ---- the gecko ------------------------------------------------------

    def _threat(self, mx, my, tg):
        """What this roach is running from — the hand, or the gecko if the
        gecko is closer. A roach does not care which of you means it harm."""
        if self.gecko is None:
            return mx, my
        gx, gy = self.gecko["px"], self.gecko["py"]
        if (math.hypot(gx - tg["px"], gy - tg["py"])
                < math.hypot(mx - tg["px"], my - tg["py"])):
            return gx, gy
        return mx, my

    def _hatch_gecko(self, now, live):
        """It comes in from the far side of the field, so the round has been
        the player's alone up to here."""
        ground = [rc for rc in self.cells if rc not in self.walls]
        if not ground:
            return
        far = max(ground, key=lambda rc: min(abs(rc[0] - tg["cell"][0])
                                             + abs(rc[1] - tg["cell"][1]) for tg in live))
        cx, cy = self._center(*far)
        self.gecko = {"cell": far, "to": far, "from": None, "prog": 1.0,
                      "px": cx, "py": cy, "heading": (cx, cy, cx, cy),
                      "last": now, "path": [], "kills": [],
                      "arrived": round(now - self.t0, 4)}
        self._toast(far, "a gecko!", False)

    def _gecko_tick(self, now):
        live = self._live()
        if not live:
            return
        if self.gecko is None:
            if now - self.t0 >= self.GECKO_AFTER:
                self._hatch_gecko(now, live)
            return
        g = self.gecko
        dt = now - g["last"]
        g["last"] = now
        g["prog"] += self.GECKO_SPEED * dt
        if g["prog"] >= 1.0:
            g["prog"], g["from"], g["cell"] = 0.0, g["cell"], g["to"]
            prey = min(live, key=lambda tg: abs(tg["cell"][0] - g["cell"][0])
                       + abs(tg["cell"][1] - g["cell"][1]))
            g["to"] = (self._toward(g["cell"], prey["cell"])
                       or self._wander(g["cell"], g["px"], g["py"], False, g["from"]))
        ax, ay = self._center(*g["cell"])
        bx, by = self._center(*g["to"])
        g["px"] = ax + (bx - ax) * g["prog"]
        g["py"] = ay + (by - ay) * g["prog"]
        g["heading"] = (ax, ay, bx, by)
        g["path"].append((round(now - self.t0, 4), round(g["px"], 1), round(g["py"], 1)))
        for tg in live:
            if tg["hidden"] or tg["under"]:
                continue                                   # it cannot reach down a hole either
            if math.hypot(g["px"] - tg["px"], g["py"] - tg["py"]) <= self.GECKO_REACH:
                g["kills"].append((round(now - self.t0, 4), tg["id"]))
                self._toast(tg["cell"], "the gecko got one", False)
                self._roach_down(tg, now, "gecko")
                break

    def _draw_gecko(self):
        self.canvas.delete("gecko")
        g = self.gecko
        if g is None:
            return
        ax, ay, bx, by = g["heading"]
        ang = math.atan2(by - ay, bx - ax) if (bx != ax or by != ay) else 0.0
        dx, dy = math.cos(ang), math.sin(ang)
        px, py = -dy, dx
        x, y = g["px"], g["py"]
        self.canvas.create_line(x - dx * 7, y - dy * 7, x - dx * 21, y - dy * 21,
                                fill="#39c5cf", width=3, tag="gecko")
        for side in (1, -1):
            for along in (0.6, -0.6):
                bx0, by0 = x + dx * along * 7, y + dy * along * 7
                self.canvas.create_line(bx0, by0, bx0 + px * side * 9, by0 + py * side * 9,
                                        fill="#164e52", width=2, tag="gecko")
        self.canvas.create_oval(x - 10, y - 6, x + 10, y + 6, fill="#39c5cf",
                                outline="#164e52", tag="gecko")
        hx, hy = x + dx * 10, y + dy * 10
        self.canvas.create_oval(hx - 5, hy - 4, hx + 5, hy + 4, fill="#39c5cf",
                                outline="#164e52", tag="gecko")

    # ---- tunnels --------------------------------------------------------

    def _draw_tunnel(self, rc):
        cx, cy = self._center(*rc)
        self.canvas.create_oval(cx - 9, cy - 9, cx + 9, cy + 9, fill="#010409",
                                outline="#484f58", width=2, tag="tunnel")

    def _dive(self, tg, now):
        """Down the hole. It is gone from the field until it surfaces at the
        far end, which is the point — you lose it and have to work out where
        it comes back up."""
        mouth = tg["cell"]
        tg["under"] = True
        tg["tunnel_until"] = now + random.uniform(*self.TUNNEL_SECS)
        tg["tunnel_exit"] = self.tunnels[mouth]
        tg["bait_cell"], tg["feed_until"] = None, 0.0
        tg["tunnels"].append({"in": round(now - self.t0, 4), "from": list(mouth),
                              "out": None, "to": None})
        self._set_mode(tg, "tunnelling", now)              # stamped at the dive, not a frame later
        self._toast(mouth, "down a tunnel!", False)

    def _surface(self, tg, now):
        """Up at the far mouth, already running."""
        cell = tg["tunnel_exit"]
        cx, cy = self._center(*cell)
        tg["cell"], tg["to"], tg["from"], tg["prog"] = cell, cell, None, 1.0
        tg["px"], tg["py"], tg["heading"] = cx, cy, (cx, cy, cx, cy)
        tg["under"], tg["tunnel_until"], tg["tunnel_exit"] = False, 0.0, None
        tg["burst_until"] = now + 0.3                      # it comes out at a bolt
        if tg["tunnels"] and tg["tunnels"][-1]["out"] is None:
            tg["tunnels"][-1]["out"] = round(now - self.t0, 4)
            tg["tunnels"][-1]["to"] = list(cell)

    # ---- bait -----------------------------------------------------------

    def _drop_bait(self, now):
        """Scatter a crumb somewhere the roaches can get to and nobody is
        standing. Some of it is laced."""
        taken = (set(self.baits) | self.hides | set(self.tunnels)
                 | {tg["cell"] for tg in self._live()})
        ground = [rc for rc in self.cells if rc not in self.walls and rc not in taken]
        if not ground:
            return
        rc = random.choice(ground)
        poison = random.random() < self.POISON_ODDS
        cx, cy = self._center(*rc)
        item = self.canvas.create_oval(
            cx - 4, cy - 4, cx + 4, cy + 4, tag="bait",
            fill="#a371f7" if poison else "#d29922",
            outline="#553098" if poison else "#8b6914")
        self.baits[rc] = {"item": item, "poison": poison, "kind": "crumb"}
        self.bait_log.append({"cell": list(rc), "spawned": round(now - self.t0, 4),
                              "poison": poison, "kind": "crumb",
                              "eaten": None, "by": None})

    def _leave_corpse(self, tg, now):
        """A poisoned roach leaves a poisoned meal behind. Whatever eats it
        next goes the same way — that is the domino, and it is why a gel bait
        reaches roaches that never touched the bait."""
        rc = tg["cell"]
        if rc in self.baits or rc in self.walls:
            return
        cx, cy = self._center(*rc)
        item = self.canvas.create_oval(cx - 7, cy - 5, cx + 7, cy + 5,
                                       fill="#6e4b1f", outline="#a371f7", width=2,
                                       tag="bait")
        self.baits[rc] = {"item": item, "poison": True, "kind": "corpse"}
        self.bait_log.append({"cell": list(rc), "spawned": round(now - self.t0, 4),
                              "poison": True, "kind": "corpse",
                              "eaten": None, "by": None})

    def _lure(self, tg):
        """The crumb this roach is going for, if any. It stays with the one it
        committed to, and only notices a fresh one within smelling distance."""
        if tg["bait_cell"] in self.baits:
            return tg["bait_cell"]
        if not self.baits:
            return None
        r, c = tg["cell"]
        near = min(self.baits, key=lambda rc: abs(rc[0] - r) + abs(rc[1] - c))
        gap = abs(near[0] - r) + abs(near[1] - c)
        return near if gap <= self.BAIT_RANGE else None

    def _eat_bait(self, tg, now):
        """It finishes the meal. Swat it mid-mouthful and the food survives for
        whoever comes along next."""
        rc = tg["bait_cell"]
        tg["bait_cell"], tg["feed_until"] = None, 0.0
        food = self.baits.pop(rc, None)
        if food is None:
            return
        self.canvas.delete(food["item"])
        for entry in self.bait_log:
            if tuple(entry["cell"]) == rc and entry["eaten"] is None:
                entry["eaten"], entry["by"] = round(now - self.t0, 4), tg["id"]
                break
        if food["poison"]:
            self._sicken(tg, now)

    def _sicken(self, tg, now):
        """It has taken the poison. Slower, staggering, and on a clock."""
        if tg["sick"]:
            return
        tg["sick"] = True
        tg["sickened_at"] = round(now - self.t0, 4)
        tg["speed"] *= self.SICK_SPEED
        tg["dies_at"] = now + random.uniform(*self.SICK_SECS)
        self._toast(tg["cell"], "poisoned", False)

    def _set_mode(self, tg, mode, now):
        """A roach's mode timeline, so analysis can segment the chase: pursuing
        something baited is a different measurement from pursuing something
        bolting."""
        if tg["mode"] == mode:
            return
        tg["mode"] = mode
        tg["modes"].append((round(now - self.t0, 4), mode))

    def _roach_tick(self):
        if self.state != "evasive":
            return
        now = time.perf_counter()
        mx, my = self.last
        if len(self.baits) < self.MAX_BAIT and now >= self.next_bait:
            self._drop_bait(now)
            self.next_bait = now + random.uniform(*self.BAIT_EVERY)
        for tg in self._live():
            self._advance(tg, now, mx, my)
        self._gecko_tick(now)
        quarry = self._quarry(now, mx, my)
        if quarry is not None:
            self.path.append((round(now - self.t0, 4),
                              round(quarry["px"], 1), round(quarry["py"], 1)))
        self._draw_roaches()
        self._draw_gecko()
        if not self._live():                               # poison or the gecko finished it
            return self._finish_evasive()
        self.root.after(16, self._roach_tick)

    def _advance(self, tg, now, mx, my):
        """One roach, one frame."""
        dt = now - tg["last"]
        tg["last"] = now
        if tg["under"]:                                    # somewhere under the field
            if now < tg["tunnel_until"]:
                self._set_mode(tg, "tunnelling", now)
                return
            self._surface(tg, now)
        if tg["sick"] and now >= tg["dies_at"]:            # the poison finishes it
            return self._roach_down(tg, now, "poison")
        if tg["hidden"]:            # lurks under the silver cell — pulses, won't leave on its own
            self._set_mode(tg, "hidden", now)
            self.canvas.itemconfig(self.cells[tg["hide_cell"]],
                                   fill="#f85149" if (now * 4) % 2 < 1 else "#b1bac4")
            return
        mx, my = self._threat(mx, my, tg)                  # the hand, or the gecko
        fleeing = now < tg["burst_until"]
        if fleeing and tg["bait_cell"] is not None:
            tg["bait_cell"], tg["feed_until"] = None, 0.0   # a scare beats an appetite
        elif tg["bait_cell"] is not None and tg["feed_until"] and now >= tg["feed_until"]:
            self._eat_bait(tg, now)
        feeding = now < tg["feed_until"]
        self._set_mode(tg, "fleeing" if fleeing else
                       "feeding" if feeding else
                       "baited" if tg["bait_cell"] is not None else "wander", now)

        speed = tg["speed"] * (2.0 if fleeing else 1.0)
        if not fleeing and (feeding or now < tg["pause_until"]):
            speed = 0.0
        tg["prog"] += speed * dt
        if tg["prog"] >= 1.0:                              # arrived in the next cell — decide
            tg["prog"], tg["from"], tg["cell"] = 0.0, tg["cell"], tg["to"]
            ccx, ccy = self._center(*tg["cell"])
            if math.hypot(mx - ccx, my - ccy) < 95 and now > tg["burst_until"]:
                tg["burst_until"] = now + 0.5
                tg["want_hide"] = random.random() < 0.3
                tg["bait_cell"], tg["feed_until"] = None, 0.0
                fleeing = True
            elif random.random() < 0.12 and now > tg["burst_until"]:
                tg["burst_until"] = now + random.uniform(0.2, 0.5)   # chaotic random darts
            if fleeing and tg["cell"] in self.tunnels and random.random() < self.TUNNEL_ODDS:
                return self._dive(tg, now)
            if tg["cell"] in self.hides and (tg["want_hide"] or random.random() < 0.4):
                tg["hidden"], tg["hide_cell"] = True, tg["cell"]
                tg["want_hide"] = False
                return
            crumb = None if (fleeing or tg["want_hide"]) else self._lure(tg)
            if crumb is not None:
                tg["bait_cell"] = crumb
                if tg["cell"] == crumb:                    # head down, and vulnerable
                    tg["feed_until"] = now + random.uniform(*self.FEED_SECS)
                    tg["to"] = tg["cell"]
                else:
                    tg["to"] = (self._toward(tg["cell"], crumb)
                                or self._wander(tg["cell"], mx, my, False, tg["from"], tg["sick"]))
            elif tg["want_hide"]:
                tg["to"] = (self._toward(tg["cell"], self._nearest_hide(tg["cell"]))
                            or self._wander(tg["cell"], mx, my, True, tg["from"], tg["sick"]))
            else:
                if random.random() < 0.02:
                    tg["pause_until"] = now + random.uniform(0.1, 0.3)
                tg["to"] = self._wander(tg["cell"], mx, my, fleeing, tg["from"], tg["sick"])
        ax, ay = self._center(*tg["cell"])
        bx, by = self._center(*tg["to"])
        tg["px"] = ax + (bx - ax) * tg["prog"]
        tg["py"] = ay + (by - ay) * tg["prog"]
        tg["heading"] = (ax, ay, bx, by)
        tg["path"].append((round(now - self.t0, 4), round(tg["px"], 1), round(tg["py"], 1)))

    # ---- click router ---------------------------------------------------

    def _click(self, e):
        if self.state in ("paused", "player_menu", "launch_player_menu", "difficulty_menu"):
            for x0, y0, x1, y1, cb in self._menu_buttons:
                if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                    return cb()
            return
        if self.state == "acquire":
            tx, ty, r = self.target["x"], self.target["y"], self.target["r"]
            err = math.hypot(e.x - tx, e.y - ty)
            start = self.samples[0] if self.samples else (0, e.x, e.y)
            self._save({"kind": "acquire", "target": {"x": tx, "y": ty, "r": r},
                        "home": {"x": start[1], "y": start[2]},
                        "click": {"x": e.x, "y": e.y, "err": round(err, 1)},
                        "reaction_s": round(self.first_move or 0, 4), "samples": self.samples})
            self._toast(self.target["cell"], "GOT IT" if err <= r * 1.4 else "missed", err <= r * 1.4)
            self.state = "idle"
            self.i += 1
            self.root.after(700, self._next)
        elif self.state == "evasive":
            self._click_evasive(e)

    def _in_cell(self, e, rc):
        x0, y0 = self._cell_xy(*rc)
        return x0 <= e.x <= x0 + self.CELL and y0 <= e.y <= y0 + self.CELL

    def _click_evasive(self, e):
        """One swing. The pick reaches into a hole, the swatter only catches
        one in the open, and either way it lands on whichever roach is nearest
        the swing — you commit to a target by aiming at it."""
        live = self._live()
        if not live:
            return
        if self.tool == "pick":
            holed = [tg for tg in live if tg["hidden"] and self._in_cell(e, tg["hide_cell"])]
            if not holed:
                return self._toast_xy(e.x, e.y, "nothing in that hole", False)
            return self._stab(min(holed, key=lambda tg: tg["health"]), e)
        loose = [tg for tg in live if not tg["hidden"] and not tg["under"]]
        if not loose:
            if any(tg["under"] for tg in live):
                return self._toast_xy(e.x, e.y, "it's in the tunnels — wait for it", False)
            return self._toast_xy(e.x, e.y, "it's down a hole — need the PICK [T]", False)
        tg = min(loose, key=lambda r: math.hypot(e.x - r["px"], e.y - r["py"]))
        if math.hypot(e.x - tg["px"], e.y - tg["py"]) > 14:
            return
        self._wound(tg, e, "hit!")

    def _stab(self, tg, e):
        """A stab into the big hole ALWAYS scares it out and burns the hole for
        good, but only lands a wound one time in four."""
        hc = tg["hide_cell"]
        self.canvas.itemconfig(self.cells[hc], fill=self.maze_base[hc])
        self.hides.discard(hc)                            # it won't hide here again this round
        tg["hidden"], tg["hide_cell"] = False, None
        tg["prog"], tg["burst_until"] = 0.0, time.perf_counter() + 0.4
        tg["to"] = self._wander(tg["cell"], e.x, e.y, True, tg["from"])
        if random.random() < 0.25:
            return self._wound(tg, e, "STABBED it!")
        self._toast_xy(e.x, e.y, "missed — it bolted out", False)

    def _roach_down(self, tg, now, cause):
        """One roach out of the round, however it went — swatted, poisoned, or
        taken by the gecko."""
        tg["dead"] = True
        tg["died"] = {"t": round(now - self.t0, 4), "cause": cause}
        if tg["id"] == self.engaged:
            self.engaged = None                           # re-home onto whatever is left
        if cause == "poison":
            self._leave_corpse(tg, now)

    def _finish_evasive(self):
        if self.state != "evasive":
            return
        self._save_evasive()
        self.canvas.delete("roach", "gecko")
        self.state = "idle"
        self.i += 1
        self.root.after(800, self._next)

    def _wound(self, tg, e, text):
        tg["health"] -= 1
        tg["speed"] *= 0.88                               # wounded wood roach slows down
        self.hit_n += 1
        self._hit_mark(e.x, e.y, self.hit_n)
        if tg["health"] > 0:
            return self._toast_xy(e.x, e.y, text, True)
        self._roach_down(tg, time.perf_counter(), "swat")
        left = len(self._live())
        if left:
            return self._toast_xy(e.x, e.y, f"SQUASHED — {left} to go", True)
        self._toast_xy(e.x, e.y, "SQUASHED", True)
        self._finish_evasive()

    # ---- end ------------------------------------------------------------

    def _finish(self):
        self.recorder.close()
        who = self.player or "default"
        try:
            qualifies = board_qualifies(leaderboard_path(), self.score)
        except Exception:
            qualifies = False
        if qualifies:                                      # the arcade ritual
            return self._begin_initials(who)
        self._conclude(who, entry_name=who)

    # ---- initials entry (top-10 only) -----------------------------------

    def _begin_initials(self, who):
        self.state = "initials"
        self.initials = default_initials(who)
        # The prefill fills all three slots, so an append-only editor would
        # swallow every letter typed (#74). Until the player touches the
        # entry, the first letter they type replaces it outright — the way an
        # arcade cabinet treats the initials it guessed for you.
        self.initials_untouched = True
        self.canvas.delete("all")
        ska("squash")                                      # a little fanfare for making the board
        self._draw_initials()

    def _draw_initials(self):
        cx = self.W // 2
        self.canvas.delete("initials")
        self.canvas.create_text(cx, self.H // 2 - 130, text="TOP 10!", fill="#39d353",
                                font=("Consolas", 34, "bold"), tag="initials")
        self.canvas.create_text(cx, self.H // 2 - 80, text=f"{self.score} PTS — ENTER YOUR INITIALS",
                                fill="#e3b341", font=("Consolas", 18, "bold"), tag="initials")
        slots = "".join((self.initials[j] if j < len(self.initials) else "_") + "  "
                        for j in range(3))
        self.canvas.create_text(cx, self.H // 2, text=slots.strip(), fill="#f0f6fc",
                                font=("Consolas", 48, "bold"), tag="initials")
        self.canvas.create_text(cx, self.H // 2 + 70, fill="#6e7681", tag="initials",
                                font=("Consolas", 12),
                                text="type A-Z · BACKSPACE to fix · ENTER to confirm")

    def _initials_key(self, e):
        if self.state != "initials":
            return
        if e.keysym == "Return" and self.initials:
            who = self.player or "default"
            return self._conclude(who, entry_name=self.initials)
        if e.keysym == "BackSpace":
            self.initials = self.initials[:-1]
            self.initials_untouched = False
        elif len(e.char) == 1 and e.char.isalpha():
            if self.initials_untouched:                    # first letter replaces the prefill
                self.initials = e.char.upper()
                self.initials_untouched = False
                ska("hit")
            elif len(self.initials) < 3:
                self.initials += e.char.upper()
                ska("hit")
        self._draw_initials()

    def _conclude(self, who, entry_name):
        self.state = "done"
        self.canvas.delete("all")
        final_score = self.score
        best, is_new_best = final_score, False
        try:
            best, is_new_best = update_personal_best(bests_path(), who, final_score)
        except Exception:
            pass
        board, mine = [], None
        if final_score > 0:                                # empty runs don't clutter the table
            mine = {"name": entry_name, "score": final_score, "date": time.strftime("%Y-%m-%d")}
            try:
                board = update_leaderboard(leaderboard_path(), entry_name, final_score, mine["date"])
            except Exception:
                board = [mine]
        ska("board")
        self._draw_high_scores(board, mine, who=who, best=best, is_new_best=is_new_best)

    def _draw_high_scores(self, board, mine, who="default", best=0, is_new_best=False):
        cx = self.W // 2
        self.canvas.create_text(cx, 90, text="H I G H   S C O R E S", fill="#e3b341",
                                font=("Consolas", 30, "bold"))
        self.canvas.create_text(cx, 130, text=f"{'RANK':<6}{'NAME':<16}{'SCORE':>8}   DATE",
                                fill="#6e7681", font=("Consolas", 14, "bold"))
        highlighted = False
        for j, row in enumerate(board):
            is_mine = (not highlighted and mine is not None
                       and row.get("name") == mine["name"]
                       and row.get("score") == mine["score"]
                       and row.get("date") == mine["date"])
            highlighted = highlighted or is_mine
            color = "#39d353" if is_mine else ("#f0f6fc" if j < 3 else "#8b949e")
            line = (f"{j + 1:<6}{str(row.get('name', '?'))[:15]:<16}"
                    f"{int(row.get('score', 0)):>8}   {row.get('date', '')}")
            self.canvas.create_text(cx, 168 + j * 30, text=line, fill=color,
                                    font=("Consolas", 15, "bold"))
        y = 168 + max(1, len(board)) * 30 + 30
        msg = (f"{mine['name']} — {mine['score']} pts" if mine
               else "no scored rounds this run")
        self.canvas.create_text(cx, y, text=msg, fill="#e3b341",
                                font=("Consolas", 16, "bold"))
        if is_new_best:
            self._blink_best(cx, y + 32)
            y += 32
        elif best and mine:
            self.canvas.create_text(cx, y + 32, text=f"{who}'s best: {best}",
                                    fill="#8b949e", font=("Consolas", 12, "bold"))
            y += 32
        self.canvas.create_text(cx, y + 34, fill="#6e7681", font=("Consolas", 11),
                                text=f"movement saved · {os.path.basename(self.recorder.path)}")

    def _blink_best(self, x, y, on=True):
        if self.state != "done":
            return
        self.canvas.delete("newbest")
        self.canvas.create_text(x, y, text="* NEW PERSONAL BEST *",
                                fill="#39d353" if on else BG,
                                font=("Consolas", 16, "bold"), tag="newbest")
        self.root.after(450, lambda: self._blink_best(x, y, not on))


def main() -> None:
    device, player, difficulty = "mouse", None, None
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--player":
            i += 1
            player = argv[i] if i < len(argv) else None
        elif a.startswith("--player="):
            player = a.split("=", 1)[1]
        elif a == "--difficulty":
            i += 1
            difficulty = argv[i].lower() if i < len(argv) else None
        elif a.startswith("--difficulty="):
            difficulty = a.split("=", 1)[1].lower()
        else:
            device = a
        i += 1
    root = tk.Tk()
    Garden(root, device=device, player=player, difficulty=difficulty)
    root.mainloop()


if __name__ == "__main__":
    main()
