# Publishing Armada to PyPI

This covers publishing workflow — both manually and via the automated GitHub Actions pipeline.

## One-Time Setup

### 1. Create PyPI accounts

- Production: https://pypi.org/account/register/
- Test: https://test.pypi.org/account/register/

### 2. Create API tokens

- Production token: https://pypi.org/manage/account/token/
- Test token: https://test.pypi.org/manage/account/token/

Save them — they're shown only once.

### 3. Configure GitHub secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Secret name | Value |
|---|---|
| `TEST_PYPI_API_TOKEN` | Your Test PyPI token (starts with `pypi-`) |

Production PyPI uses **Trusted Publisher (OIDC)** — no token needed. The workflow authenticates via GitHub's identity.

### 4. Configure PyPI Trusted Publisher (one-time)

1. Go to https://pypi.org/manage/project/armada-ai/settings/publishing/ (create the project first if needed)
2. Add a **pending publisher**:
   - Owner: `rguiu`
   - Repository: `armada`
   - Workflow: `publish-pypi.yml`
   - Environment: (leave blank)

---

## Automated Pipeline

### How it works

```
PR merged to main
  └→ release.yml triggers
       ├→ Reads version from armada_ai/constants.py
       ├→ Creates git tag (v0.2.0)
       ├→ Builds wheel + sdist
       ├→ Publishes to Test PyPI
       └→ Creates draft GitHub Release
            └→ You test the Test PyPI install
                 └→ Manually run publish-pypi.yml
                      └→ Builds + publishes to production PyPI
```

### Release checklist

1. **Bump version** in two files:
   - `pyproject.toml` → `version = "0.2.1"`
   - `armada_ai/constants.py` → `VERSION = "0.2.1"`

2. **Update RELEASING.md** with any new steps if needed.

3. **Run tests and lint locally:**
   ```bash
   make test
   make lint
   ```

4. **Create PR to `main`.** CI runs lint + tests.

5. **Merge PR.** The `release.yml` workflow automatically:
   - Tags `v0.2.1`
   - Builds and publishes to Test PyPI
   - Creates a draft GitHub Release with install instructions

6. **Test the Test PyPI install:**
   ```bash
   pip install --index-url https://test.pypi.org/simple/ armada-ai==0.2.1
   armada version
   ```

7. **Publish to production:** Go to Actions → "Publish to Production PyPI" → Run workflow → type `publish`.

---

## Manual Publishing

If the automated pipeline isn't available, publish manually:

```bash
# 1. Build
make build

# 2. Test PyPI
twine upload --repository testpypi dist/*
# Username: __token__
# Password: <test-pypi-token>

# 3. Test install
pip install --index-url https://test.pypi.org/simple/ armada-ai
armada version

# 4. Production PyPI
twine upload dist/*
```

### Using ~/.pypirc (optional)

```ini
[distutils]
index-servers = pypi, testpypi

[pypi]
username = __token__
password = pypi-YOUR-TOKEN

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-YOUR-TEST-TOKEN
```

Then: `twine upload -r testpypi dist/*`

---

## Makefile Commands

```bash
make test          # Run tests
make test-cov      # Tests with coverage
make lint          # Ruff lint
make format        # Ruff format + fix
make build         # Clean + build wheel and sdist
make publish       # Build + twine upload to PyPI
make clean         # Remove build artifacts
```

---

## Version Policy

Armada uses manual versioning. Bump both files before release:

| Change | Version bump |
|---|---|
| Bug fixes | `0.2.0` → `0.2.1` |
| New features | `0.2.0` → `0.3.0` |
| Breaking changes | `0.2.0` → `1.0.0` |

---

## Troubleshooting

**"Package already exists"**: You can't overwrite a version on PyPI. Bump the version.

**"Invalid distribution"**: `twine check dist/*`

**Test PyPI upload fails in CI**: The version might already exist on Test PyPI. The workflow has `|| echo` fallback — check the release draft for the install command.

**Trusted Publisher fails**: Verify the publisher is configured at https://pypi.org/manage/project/armada-ai/settings/publishing/
