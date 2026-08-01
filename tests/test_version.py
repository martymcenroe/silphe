"""The version lives in two files and must agree — issue #60.

`poetry version <rule>` rewrites `pyproject.toml` and nothing else, so a bump
that stops there ships a package reporting the previous release. PyPI never
lets a version be re-uploaded, so that mistake costs a whole version number to
undo. This is the guard that makes a half-done bump fail here instead.
"""

import pathlib
import tomllib

import silphe

PYPROJECT = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"


def declared_version() -> str:
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_package_version_matches_pyproject():
    assert silphe.__version__ == declared_version(), (
        "silphe.__version__ and pyproject.toml disagree — a version bump has to "
        "change src/silphe/__init__.py as well as pyproject.toml"
    )


def test_version_looks_like_a_release():
    parts = declared_version().split(".")
    assert len(parts) == 3, "expected major.minor.patch"
    assert all(p.isdigit() for p in parts), "no dev/rc suffixes on a published version"
