# Publishing Silphe to PyPI (and actually reserving the name)

Silphe publishes via **OIDC Trusted Publishing**: GitHub Actions mints a
short-lived token and PyPI trusts it. **No API token is stored anywhere.**

This is the silphe-specific version of AssemblyZero runbook
`0934-pypi-trusted-publisher-setup.md`, with two corrections that runbook still
needs (tracked in AssemblyZero #1582 and #1583).

## The one thing everyone gets wrong

> **Registering a "pending publisher" does NOT reserve the name.**

PyPI's own docs:

> "A 'pending' publisher does not create a project or reserve a project's name
> until it is actually used to publish. If you create a 'pending' publisher but
> another user registers the project name before you actually publish to it,
> your 'pending' publisher will be invalidated."
>
> — <https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/>

**The only action that reserves `silphe` is publishing a real release.** Until
the first `v*.*.*` tag publishes successfully, the name is free for anyone to
take — and if they take it, your pending publisher silently invalidates.

## Credentials — what you actually need

- **PyPI has no "Sign in with GitHub."** Account login is username/email +
  password + **2FA** (authenticator app or passkey) + recovery codes. It's in
  your password manager from a prior project's setup — reuse that account.
- The GitHub connection in Step 1 is only the OIDC *publish* trust, never login.
- **You need zero API token** for this path. Nothing to generate or store.

## Pre-flight (done by the library PR)

- [x] `pyproject.toml` → `[project] name = "silphe"`, `version = "0.1.0"`
- [x] `.github/workflows/release.yml` present, `environment: pypi`, tag `v*.*.*`
- [x] `poetry build` produces a wheel + sdist
- [x] Library PR merged to `main`

## Step 1 — Register the pending publisher (browser, ~2 min)

1. Log in at <https://pypi.org/manage/account/publishing/> (your existing account).
2. Under **"Add a new pending publisher,"** fill in exactly:

   | Field | Value |
   |---|---|
   | PyPI Project Name | `silphe` |
   | Owner | `martymcenroe` |
   | Repository name | `silphe` |
   | Workflow filename | `release.yml` |
   | Environment name | `pypi` |

3. Click **Add**. This configures trust. It does **not** yet reserve the name —
   Step 2 does.

## Step 2 — Publish (the tag push that reserves the name)

From `main`, with the tag matching `pyproject.toml`'s version:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Watch it:

```bash
gh run watch --repo martymcenroe/silphe
```

The workflow builds the distributions and publishes via OIDC. On success the
release is live at <https://pypi.org/project/silphe/0.1.0/> within seconds, the
name is **now reserved**, and the pending publisher promotes to a permanent
trusted publisher.

## Step 3 — Verify

```bash
pip install silphe
python -c "import silphe; print(silphe.__version__)"   # 0.1.0
silphe-analyze                                          # entry point resolves
```

## Subsequent releases

Bump the version, tag, push the tag. No browser steps ever again.

```bash
poetry version patch
git commit -am "chore: bump to $(poetry version -s)"
git tag "v$(poetry version -s)"
git push origin main "v$(poetry version -s)"
```

## If it fails

| Symptom | Cause | Fix |
|---|---|---|
| `Trusted publisher not found` | Step 1 not done, or a field mismatched | Re-check owner / repo / `release.yml` / `pypi` match exactly |
| `Project name is not available` | Someone else already took `silphe` | The name is gone; choose another in `pyproject.toml` and re-register |
| Workflow never starts | Tag isn't `v*.*.*` | `v0.1.0` matches; `0.1.0` does not |

## References

- AssemblyZero `0934-pypi-trusted-publisher-setup.md` — the fleet runbook (corrections tracked in AZ #1582, #1583)
- PyPI Trusted Publishers — <https://docs.pypi.org/trusted-publishers/>
