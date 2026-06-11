# CLAUDE.md - silphe Project

You are a team member on the silphe project, not a tool.

## Project Identifiers

- **Repository:** `martymcenroe/silphe`
- **Project Root (Windows):** `C:\Users\mcwiz\Projects\silphe`
- **Project Root (Unix):** `/c/Users/mcwiz/Projects/silphe`
- **Worktree Pattern:** `silphe-{IssueID}` (e.g., `silphe-45`)

## Project-Specific Context

_TODO: Add tech stack, architecture, file map, project-type-specific notes,
and any workflow overrides specific to this project. The universal
CLAUDE.md (auto-loaded by Claude Code's parent-directory traversal) covers
fleet-wide rules -- this file only adds what's true for THIS repo
specifically. Restating universal content here creates drift on every
universal-CLAUDE.md edit (ADR 0219)._

## Data Directories

- `data/`: ephemeral session artifacts (transcripts, run logs, pickup state). Ignored by the fleet-wide global gitignore; not committed.
- `data-g/`: source-of-truth data the runtime treats as authoritative (rosters, corpora, configs). Git-tracked for durability. See `data-g/README.md`. (AssemblyZero #1563.)

## Workflow Overrides

_None yet. If this project needs to override any universal CLAUDE.md
rule (e.g., a custom merge tool, a special test convention), document
the override here with explicit language ("override") per ADR 0219._
