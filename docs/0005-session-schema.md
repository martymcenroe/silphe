# Session recording schema

A **session** is a JSON Lines file named `session-<unixtime>-<device>.jsonl`,
written by the calibration game (`silphe-play`) into the recordings directory
(`$SILPHE_RECORDINGS`, default `~/.silphe/recordings`). Each line is one JSON
object — a **trial**.

Load them with `silphe.analysis.load_session(path)` or
`silphe.analysis.load_recordings()`.

## Common keys (every trial)

| Key | Type | Meaning |
|---|---|---|
| `schema_version` | int | recording schema version (see below); stamped by the capture kernel |
| `kind` | string | `"acquire"`, `"track"`, `"hold"`, or `"evasive"` |
| `samples` | `[[t, x, y], ...]` | the cursor trace; `t` = seconds from trial start, `x`/`y` = screen pixels |
| `reaction_s` | number | seconds to first movement |
| `device` | string | `"mouse"`, `"trackpad"`, … (as tagged at launch) |
| `os` | string | `platform.system()` |
| `player` | string | player name (`""` for the default player) |

## Schema version and compatibility (the family contract)

The recording schema is the one invariant shared by every build in the silphe
family — the open toy and any downstream instrument all record byte-comparably
so movement data and a person's signature stay portable across versions. It is
therefore versioned and frozen:

- **`silphe.core.SCHEMA_VERSION`** is the authoritative version, stamped on every
  record by the capture kernel (`silphe.core.Recorder`).
- **`silphe.core.KERNEL_FIELDS`** (`schema_version, device, os, player`) are the
  fields the kernel guarantees on every record, regardless of game.
- **Compatibility promise: additive-only within a major version.** New optional
  fields may appear without a bump; a field is never renamed, removed, or
  repurposed without incrementing `SCHEMA_VERSION`.
- `tests/test_core.py` fails fast if the kernel-stamped field set drifts from
  `KERNEL_FIELDS` without a conscious change — the guard that keeps the family
  comparable.

## Per kind

**acquire** — hit a small target.

| Key | Meaning |
|---|---|
| `target` | `{x, y, r}` — target center + radius |
| `home` | `{x, y}` — where the cursor started |
| `click` | `{x, y, err}` — click point + miss distance (px) |

**hold** — stay still on a pixel (tremor test).

| Key | Meaning |
|---|---|
| `target` | `{x, y, r}` — the pixel + tolerance |

**track** — follow a smoothly drifting dot (smooth pursuit).

| Key | Meaning |
|---|---|
| `dot` | `[[t, x, y], ...]` — the target's trace |
| `locked_at` | seconds when the player first locked on (analysis uses only the post-lock tail) |
| `on_target_pct` | percent of post-lock time on the dot |

**evasive** ("Andvari") — hunt a maze roach.

| Key | Meaning |
|---|---|
| `path` | `[[t, x, y], ...]` — the roach's trace |
| `hits` | total hits to kill it |
| `switches` | `[[t, tool], ...]` — tool switches |
| `maze` | `["#####", "#...#", ...]` — the round's field, one string per grid row, `#` wall and `.` open |

The `maze` field (added #43) is what lets analysis separate *anticipating a
corner* from *reacting in the open* — the same chase over a corridor and over a
chamber are different measurements, and the trace alone cannot tell them apart.
Rows are top-to-bottom and characters left-to-right over the same grid the
`samples` coordinates fall on; `silphe.maze.render` produces it and
`silphe.maze.generate` guarantees every open cell is reachable from every other.

## Privacy

These files are local biometric data. The repo's `recordings/` directory is
gitignored and never leaves your machine. The analysis helpers return aggregate
numbers only — never raw coordinates.
