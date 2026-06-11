# Publishing Silphe to PyPI (and actually reserving the name)

The **first** release is uploaded manually with `twine` — that's what reserves
the name. **Automated OIDC tag-push publishing comes later**, once the release
workflow lands (currently blocked on a PAT scope issue, tracked in #6).

## The one thing everyone gets wrong

> **Nothing reserves a PyPI name except publishing an actual release.**

Registering a Trusted-Publisher "pending publisher" reserves *nothing* — PyPI's
own docs say so:

> "A 'pending' publisher does not create a project or reserve a project's name
> until it is actually used to publish."
>
> — <https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/>

So `silphe` is unclaimed until the upload below succeeds.

## Credentials — what you need

- **PyPI has no "Sign in with GitHub."** Account login is username/email +
  password + **2FA** (authenticator app or passkey) + recovery codes — in your
  password manager from a prior project. Reuse that account; don't make a second.
- For this manual first upload you need a **PyPI API token**: create one at
  <https://pypi.org/manage/account/token/> ("Entire account" scope works for the
  first upload, since the project doesn't exist yet). It looks like `pypi-…`.
- **Secret hygiene:** paste the token at twine's password prompt — do **not** put
  it in the command, an env var, or anywhere shell history captures it. Delete or
  re-scope the token after the first upload.

## Reserve the name — first release (you run this)

```bash
cd /c/Users/mcwiz/Projects/silphe
poetry build                          # fresh wheel + sdist in dist/
python -m pip install --upgrade twine
twine upload dist/*
# username: __token__
# password: <paste the pypi-… token at the prompt>
```

On success the release is live at <https://pypi.org/project/silphe/0.1.0/> and
**the name is now reserved.**

## Verify

```bash
pip install silphe
python -c "import silphe; print(silphe.__version__)"   # 0.1.0
silphe-analyze                                          # entry point resolves
```

Then: clear your clipboard, and delete or project-scope the API token.

## Future releases — switch to OIDC (no token, ever)

Once the release workflow lands (#6):

1. On the now-existing PyPI project → **Manage → Publishing → Add a trusted
   publisher**: owner `martymcenroe`, repo `silphe`, workflow `release.yml`,
   environment `pypi`.
2. From then on every release is just a tag push — no token, no browser:

   ```bash
   poetry version patch
   git commit -am "chore: bump to $(poetry version -s)"
   git tag "v$(poetry version -s)"
   git push origin main "v$(poetry version -s)"
   ```

## If it fails

| Symptom | Cause | Fix |
|---|---|---|
| `403 Forbidden` on upload | Bad/expired token, or wrong username | Username must be `__token__`; regenerate the token |
| `Project name is not available` | Someone else already took `silphe` | The name is gone; pick another in `pyproject.toml` |
| `File already exists` | That version was already uploaded | Bump the version; PyPI never lets you re-upload a version |

## References

- AssemblyZero `0934-pypi-trusted-publisher-setup.md` — the fleet OIDC runbook (corrections tracked in AZ #1582, #1583)
- PyPI Trusted Publishers — <https://docs.pypi.org/trusted-publishers/>
