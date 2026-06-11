# 00003 - silphe File Inventory

**Status:** Active
**Created:** 2026-06-11
**Last Updated:** 2026-06-11

---

## Purpose

This document provides a complete inventory of files in the silphe project, organized by directory. It serves as a quick reference for agents and developers to understand the project structure.

---

## Directory Structure

```
silphe/
├── .claude/                    # Claude Code configuration
├── data/                       # Ephemeral data (git-ignored fleet-wide)
├── data-g/                     # Git-tracked source-of-truth data (see data-g/README.md)
├── docs/                       # All documentation
│   ├── adrs/                   # Architecture Decision Records
│   ├── standards/              # Project-specific standards
│   ├── templates/              # Document templates
│   ├── lld/                    # Low-Level Designs
│   │   ├── active/             # In-progress LLDs
│   │   └── done/               # Completed LLDs
│   ├── reports/                # Implementation & test reports
│   │   ├── active/             # In-progress reports
│   │   └── done/               # Completed reports
│   ├── runbooks/               # Operational procedures
│   ├── session-logs/           # Agent session context
│   ├── audit-results/          # Historical audit outputs
│   ├── media/                  # Artwork, videos, tutorials
│   ├── legal/                  # ToS, privacy policy, regulatory
│   └── design/                 # UI mockups, style guides
├── src/                        # Application source code
├── tests/                      # Test suites
│   ├── unit/                   # Fast, isolated tests
│   ├── integration/            # Multiple components together
│   ├── e2e/                    # End-to-end tests
│   ├── smoke/                  # Quick sanity/environment tests
│   ├── contract/               # API contract tests
│   ├── visual/                 # Visual regression tests
│   ├── benchmark/              # Performance tests
│   ├── security/               # Security tests
│   ├── accessibility/          # Accessibility tests
│   ├── compliance/             # Compliance tests
│   ├── fixtures/               # Test data
│   └── harness/                # Test utilities
├── tools/                      # Development utilities
├── CLAUDE.md                   # Claude agent instructions
├── GEMINI.md                   # Gemini agent instructions
├── README.md                   # Project overview
├── LICENSE                     # PolyForm Noncommercial 1.0.0
├── .gitignore                  # Git ignore rules
└── .unleashed.json             # Unleashed wrapper config (model, effort)
```

---

## Key Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Instructions for Claude agents working on this project |
| `GEMINI.md` | Instructions for Gemini agents working on this project |
| `README.md` | Project overview and quick start guide |
| `.claude/project.json` | Project variables for AssemblyZero template generation |

---

## Documentation Numbering

This project uses the AssemblyZero numbering scheme:

| Range | Category | Location |
|-------|----------|----------|
| `0xxxx` | Foundational (ADRs, standards) | `docs/adrs/`, `docs/standards/` |
| `1xxxx` | Issue-specific (LLDs, reports) | `docs/lld/`, `docs/reports/` |
| `3xxxx` | Runbooks | `docs/runbooks/` |
| `4xxxx` | Media | `docs/media/` |

---

## Maintenance

This inventory should be updated when:
- New directories are added
- Significant new files are created
- Project structure changes

Use `/audit` to verify structure compliance with AssemblyZero standards.
