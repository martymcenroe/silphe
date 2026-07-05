# 0001 — Running Silphe and managing players

How to start the game on this machine, where the data goes, and how to record
more than one person.

## Starting the game

**From source** (in the repo root, bash or PowerShell):

```
poetry run silphe-play
```

`silphe-play` alone won't work outside the poetry venv — the console scripts
are installed inside it, so the `poetry run` prefix is required.

**From the release exe** (v0.1.0+): run `silphe-play.exe` from wherever you
saved the GitHub Release download (or `dist\silphe-play.exe` after a local
PyInstaller build). Double-click works.

**Variants:**

```
poetry run silphe-play trackpad            # tag the session as trackpad instead of mouse
poetry run silphe-play --player Rebecca    # start directly as a named player
poetry run silphe-play --difficulty hard   # skip the difficulty menu (easy/normal/hard)
```

## Difficulty

A CHOOSE DIFFICULTY menu opens at launch unless `--difficulty` is given.
Difficulty shapes the challenge, not the scoring: hold duration, track
duration and lock tolerance, and the roach's health and speed. Each record
is stamped with the difficulty so analysis can segment by it.

## Round order

Every session (including after a player switch) opens with one of each of
acquire / track / hold in random order before the Andvari roach round can
appear — a new player always gets the basics sampled first.

## Sound

Sound effects are ska horn stabs (offbeat skank for hits, a trombone slump
for misses, a horn run for squashing the roach, a full riff on the high-score
screen). Windows-only (`winsound`); silent no-op elsewhere. No mute flag yet —
mute the system volume if needed.

## In-game keys

| Key | Effect |
|---|---|
| ESC | Pause menu: RESUME / SWITCH PLAYER / QUIT. ESC again while paused quits. (Inactive on the launch difficulty menu.) |
| P | Switch player by typing a name (blank = default player) |
| T | Swap swatter/pick during the Andvari (evasive) round |

Pausing abandons the round in progress (no partial record); RESUME replays it.
Progress is saved round-by-round, so quitting mid-sequence loses nothing
already completed.

## Where the data lives

- Recordings: `~/.silphe/recordings/` by default, one `session-<ts>-<device>.jsonl`
  per session. The `SILPHE_RECORDINGS` environment variable overrides the base
  directory for the game AND every analysis tool.
- Leaderboard: `~/.silphe/leaderboard.json` — local top-10 (name / score / date),
  shown as the HIGH SCORES screen when a session ends. Shared by all players on
  the machine. Delete the file to reset it. A score that cracks the top 10 gets
  the arcade initials-entry screen first (type A–Z, BACKSPACE to fix, ENTER to
  confirm; prefilled from the player name) and the initials become the
  leaderboard name.
- Personal bests: `~/.silphe/personal-bests.json` — each player's best score.
  Beating yours blinks * NEW PERSONAL BEST * on the end screen; your best also
  shows on the pause menu next to the running score. Delete the file to reset.

## Players

Each player records into a `recordings-<name>` sibling of the base dir, e.g.
`~/.silphe/recordings-Rebecca`. No player = the plain `recordings` dir
(the original single-player layout — old data keeps working).

Three ways to pick a player:

1. `--player NAME` at launch.
2. ESC → SWITCH PLAYER → pick from the list (it scans the `recordings-*` dirs,
   so anyone who has played before appears) or NEW PLAYER.
3. P → type a name.

Switching closes the current session file and starts a fresh session, plan,
and score for the new hand. Every record is stamped with the player name.

## Analyzing a player's data

The analysis tools read whatever `SILPHE_RECORDINGS` points at:

```
poetry run silphe-analyze                                        # default player
SILPHE_RECORDINGS=~/.silphe/recordings-Rebecca poetry run silphe-analyze
SILPHE_RECORDINGS=~/.silphe/recordings-Rebecca poetry run silphe-arc
```

The full CLI set: `silphe-play` (the game), `silphe-analyze` (metrics: Fitts
fit, tremor, signature), `silphe-arc` (drift-over-time plot), `silphe-lag`
(pointing-lag scan), `silphe-demo` (human-vs-robot cursor demo).
