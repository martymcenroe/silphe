# Publishing Silphe to PyPI

How to cut a release today. The name is already ours — `silphe` 0.1.0 went live
2026-06-11 — so this is the runbook for **every release after the first**.

> **Automated tag-push publishing is not available yet.** `release.yml` exists
> in the working tree but is not on `origin`; landing it is blocked on a PAT
> scope issue tracked in #6. Until that lands, a release is the manual twine
> upload below. The OIDC path is documented at the end so it is ready to switch
> on, but do not tag-and-wait expecting a workflow to run — nothing will.

## Before you start

- **Everything intended for the release is merged to `main`, and `main` is
  green.** `poetry run python -m pytest tests/ -q`.
- You are on `main` with nothing uncommitted that belongs in the release.
- You have the PyPI account credentials (username/email + password + 2FA). PyPI
  has no "Sign in with GitHub"; the account is in your password manager from a
  prior project — reuse it, do not make a second.

## 1. Bump the version — in both places

The version is written twice, and `poetry version` only rewrites the first:

| File | What |
|---|---|
| `pyproject.toml` | `version = "…"` — what the built artifacts are named |
| `src/silphe/__init__.py` | `__version__ = "…"` — what the installed package reports |

```bash
poetry version minor                  # or: major / patch / an explicit 0.2.0
poetry version -s                     # read back the new number
```

Then edit `src/silphe/__init__.py` to match by hand, and prove it:

```bash
poetry run python -m pytest tests/test_version.py -q
```

That test exists precisely to catch a half-done bump (#60). **PyPI never allows
a version to be re-uploaded**, so shipping a mismatch costs a whole version
number to undo — there is no fixing it in place.

Pick the number by what actually changed: a new field on a recording or a new
game behaviour is a minor bump; a renamed entry point, a removed public
function, or a `SCHEMA_VERSION` change in `silphe.core` is a major one.

## 2. Write the changelog entry

`CHANGELOG.md`, newest section at the top, following the existing 0.1.0 entry's
shape. Write it for someone deciding whether to upgrade, not for the git log.

## 3. Commit the release prep

```bash
git checkout -b release-$(poetry version -s)
git commit -am "Release $(poetry version -s) (Closes #NN)"
```

Push and merge it the normal way. The tag comes later, off `main`, once the
upload has actually succeeded.

## 4. Build

```bash
poetry build
ls dist/
```

You want exactly two new files: `silphe-<version>.tar.gz` and
`silphe-<version>-py3-none-any.whl`.

## 5. Upload — name the files, never glob

```bash
poetry run twine upload dist/silphe-<version>.tar.gz dist/silphe-<version>-py3-none-any.whl
# username: __token__
# password: <paste the pypi-… token at the prompt>
```

**Do not run `twine upload dist/*`.** `dist/` is gitignored working space that
accumulates whatever has been built there: the previous release's artifacts,
`SHA256SUMS.txt`, and the PyInstaller `silphe-play.exe` from #16. A glob
re-submits already-published files, which PyPI refuses, and hands twine an exe
and a text file it will reject. Name the two artifacts for the version you are
releasing.

`poetry run twine` is deliberate — twine is a dev dependency of this project, so
there is no separate install, and it avoids a bare `python -m pip` that can
resolve to the Microsoft Store stub on this machine.

### The token, and getting rid of it

Create one at <https://pypi.org/manage/account/token/>, scoped to the **silphe
project** (the project exists now, so account-wide scope is no longer needed).
It looks like `pypi-…`.

Paste it at twine's prompt. Do **not** put it in the command, an environment
variable, a file, or anywhere shell history captures it. When the upload
succeeds: delete the token on PyPI, and clear your clipboard
(`Set-Clipboard -Value $null` in PowerShell).

## 6. Verify — in a throwaway environment

Installing into whatever environment happens to be active tells you very little
and can shadow the real package with the working tree. Use a clean one:

```bash
python -m venv /c/Users/mcwiz/Projects/silphe/data/verify-venv
/c/Users/mcwiz/Projects/silphe/data/verify-venv/Scripts/pip install "silphe==<version>"
/c/Users/mcwiz/Projects/silphe/data/verify-venv/Scripts/python -c "import silphe; print(silphe.__version__)"
/c/Users/mcwiz/Projects/silphe/data/verify-venv/Scripts/silphe-play
```

The printed version must be the one you just released, and `silphe-play` must
open the green garden. `data/` is gitignored, so the throwaway venv lives there;
delete it afterwards.

## 7. Tag it

Only after the upload has succeeded and verified:

```bash
git checkout main && git pull
git tag "v$(poetry version -s)"
git push origin "v$(poetry version -s)"
```

## If it fails

| Symptom | Cause | Fix |
|---|---|---|
| `403 Forbidden` | Bad or expired token, or wrong username | Username must be literally `__token__`; regenerate the token |
| `File already exists` | That version is already on PyPI | Bump again — PyPI never permits re-uploading a version, even a deleted one |
| twine rejects a file | A glob picked up the exe or `SHA256SUMS.txt` | Name the two artifacts explicitly (step 5) |
| Installed package reports the old version | The bump missed `src/silphe/__init__.py` | Bump again and ship a new version; the published one cannot be corrected |
| `Trusted publisher not found` on a tag push | The OIDC path is not wired up | Expected — `release.yml` is not on origin yet (#6). Use the manual upload above |

## Later: the OIDC path, once #6 lands

When `release.yml` is on `origin`, publishing becomes a tag push with no token
anywhere:

1. On the PyPI project → **Manage → Publishing → Add a trusted publisher**:
   owner `martymcenroe`, repo `silphe`, workflow `release.yml`, environment
   `pypi`.
2. Then steps 4-7 above collapse into:

   ```bash
   git tag "v$(poetry version -s)" && git push origin "v$(poetry version -s)"
   ```

Steps 1-3 — bump both files, changelog, merge — stay exactly the same.

## History

The first release was uploaded manually with twine on 2026-06-11, which is what
reserved the name. Registering a Trusted-Publisher "pending publisher" reserves
nothing: PyPI's own docs say a pending publisher "does not create a project or
reserve a project's name until it is actually used to publish."

## References

- `docs/runbooks/0001-running-silphe-and-players.md` — running the game locally
- AssemblyZero `0934-pypi-trusted-publisher-setup.md` — the fleet OIDC runbook
  (corrections tracked in AZ #1582, #1583)
- PyPI Trusted Publishers — <https://docs.pypi.org/trusted-publishers/>
