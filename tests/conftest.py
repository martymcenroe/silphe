"""Project test bootstrap.

Adds `src/` to `sys.path` so test files can import the project's
package without a full Poetry package install. Mirrors the pattern
used across the AssemblyZero fleet.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
