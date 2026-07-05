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
```

## In-game keys

| Key | Effect |
|---|---|
| ESC | Pause menu: RESUME / SWITCH PLAYER / QUIT. ESC again while paused quits. |
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
  the machine. Delete the file to reset it.

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
