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
| `kind` | string | `"acquire"`, `"track"`, `"hold"`, or `"evasive"` |
| `samples` | `[[t, x, y], ...]` | the cursor trace; `t` = seconds from trial start, `x`/`y` = screen pixels |
| `reaction_s` | number | seconds to first movement |
| `device` | string | `"mouse"`, `"trackpad"`, … (as tagged at launch) |
| `os` | string | `platform.system()` |

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

## Privacy

These files are local biometric data. The repo's `recordings/` directory is
gitignored and never leaves your machine. The analysis helpers return aggregate
numbers only — never raw coordinates.
