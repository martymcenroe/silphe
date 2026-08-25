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

**From the release exe:** run `silphe-play.exe` from wherever you saved the
GitHub Release download (or `dist\silphe-play.exe` after a local PyInstaller
build). Double-click works.

> **The published exe is stale.** It was built 2026-06-11, before the Andvari
> ecology landed, so it still has the flat random field and a single roach. To
> see the game as it is now, run from source. A fresh build is #16's job.

**Variants:**

```
poetry run silphe-play trackpad            # tag the session as trackpad instead of mouse
poetry run silphe-play --player Rebecca    # skip the player menu, start as a named player
poetry run silphe-play --difficulty hard   # skip the difficulty menu (easy/normal/hard)
```

## What launch asks you

Two menus, in this order, and each is skipped by the matching flag:

1. **WHO'S PLAYING?** — everyone who has played on this machine, plus
   `NEW PLAYER...` to type a name and `PLAY AS DEFAULT` to record as nobody in
   particular. Skipped by `--player NAME`.
2. **CHOOSE DIFFICULTY** — easy / normal / hard. Skipped by `--difficulty`.

ESC does nothing on either one; there is no round yet to pause or abandon.

Answering the first menu matters more than it looks. Every record is stamped
with the player name and each player writes into their own
`recordings-<name>` directory, so a session played as the default is a session
filed under nobody. Switching player later does not move it: that closes the
session file and starts a fresh plan and score, leaving the rounds already
played behind under `default`.

## Difficulty

A CHOOSE DIFFICULTY menu opens at launch unless `--difficulty` is given.
Difficulty shapes the challenge AND the reward: hold duration, track duration
and lock tolerance, the roaches' health and speed, **how many roaches are in a
round** (two on easy, three on normal and hard), and a score multiplier
(easy x1, normal x1.5, hard x2). Each record is stamped with the difficulty so
analysis can segment by it.

The roach count is the biggest single difference in how a round feels, and it
compounds: a hard round is three roaches at six to eight hits each, so clearing
one takes several times longer than it used to.

## Round order

Every session (including after a player switch) opens with one of each of
acquire / track / hold in random order before the Andvari roach round can
appear — a new player always gets the basics sampled first.

## Reading the Andvari round

When the roach round starts the garden reconfigures into a maze; it goes back
to its planted scatter when the round ends. What is on the field:

| What you see | What it is |
|---|---|
| Green squares | Walls. The roaches run the corridors between them |
| Silver cells | Hide-holes. A roach ducks under one and it pulses red; only the PICK (`T`) reaches in, and a stab always drives it out but only wounds one time in four |
| Dark holes | Tunnel mouths. A bolting roach drops in and surfaces at the far one, halfway across the field. It cannot be hit while underground — you have to find where it comes up |
| Gold dots | Crumbs. A roach nearby breaks off to eat and stands still with its head down, which is your best chance at it |
| Purple dots | Laced crumbs. Whatever finishes one sickens, slows, staggers and dies |
| A brown body with a purple outline | A poisoned corpse. It is still poison — the next roach to eat it goes the same way, having never touched the bait |
| A cyan lizard | The gecko. It turns up a few seconds in and hunts the roaches too. **It is not something to swat**, and the roaches run from whichever is nearer, it or your cursor |

The round runs until the **last** roach is down, not the first.

**Only your own swats score.** Poison and the gecko take roaches as well, and
neither earns you anything — if the gecko clears the field your score does not
move. That is deliberate, not a bug.

## Sound

Sound effects are ska horn stabs (offbeat skank for hits, a trombone slump
for misses, a horn run for squashing the roach, a full riff on the high-score
screen). Each riff is synthesized as a short WAV the first time it is needed
and played through `winsound`. Windows-only; silent no-op elsewhere. No mute
flag yet — mute the system volume if needed (#85).

**If you hear nothing, look at the terminal you launched from.** The game says
why, once, on stderr: `no sound` when there is no `winsound` to play through,
which is the ordinary state off Windows, and `SOUND FAILED` with the error when
it is Windows and the sound did not work. It says it once rather than once per
hit, and it never interrupts the game. Silence with nothing printed means the
audio reached Windows and Windows played it — check the output device and the
volume rather than the game.

## In-game keys

| Key | Effect |
|---|---|
| ESC | Pause menu: RESUME / SWITCH PLAYER / QUIT. ESC again while paused quits. (Inactive on both launch menus.) |
| P | Switch player by typing a name (blank = default player) |
| T | Swap swatter/pick during the Andvari (evasive) round. The swatter catches one in the open; the pick is the only thing that reaches into a hide-hole |

On the initials screen P and T are just letters — they type, and do not switch
player or swap tool.

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
  the arcade initials-entry screen first, and the initials become the
  leaderboard name. It is prefilled from the player name — `DEF` if you played
  as the default — and **the first letter you type replaces the prefill
  outright**, so you never have to clear it first. After that, letters fill the
  remaining slots, BACKSPACE fixes, ENTER confirms. Every letter works,
  including T and P, which the tool swap and the player switch otherwise claim.
- Personal bests: `~/.silphe/personal-bests.json` — each player's best score.
  Beating yours blinks * NEW PERSONAL BEST * on the end screen; your best also
  shows on the pause menu next to the running score. Delete the file to reset.

## Players

Each player records into a `recordings-<name>` sibling of the base dir, e.g.
`~/.silphe/recordings-Rebecca`. No player = the plain `recordings` dir
(the original single-player layout — old data keeps working).

Four ways to pick a player. The first two settle it before anything is
recorded, which is where you want to settle it:

1. The WHO'S PLAYING? menu at launch (it scans the `recordings-*` dirs, so
   anyone who has played before appears).
2. `--player NAME` at launch, which skips that menu.
3. ESC → SWITCH PLAYER → pick from the list or NEW PLAYER.
4. P → type a name.

The last two are mid-session switches, and they cost you the session: each
closes the current session file and starts a fresh session, plan and score for
the new hand, so rounds already played stay filed under whoever played them.
Every record is stamped with the player name.

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
