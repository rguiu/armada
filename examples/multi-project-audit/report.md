# Security Audit Results

**Date:** 2026-06-21  
**Projects audited:** Armada, PGLease, SGLang  
**Scope:** Hardcoded secrets, eval/exec usage, SQL injection, input validation, sensitive data in logs

---

## Summary by Severity

| Severity | Project | Issue |
|----------|---------|-------|
| **HIGH** | SGLang | `trust_remote_code=True` hardcoded — RCE via model repos |
| **MEDIUM** | Armada | Token & DB files world-readable (any local user can steal token) |
| **MEDIUM** | Armada | Non-constant-time token comparison (timing side-channel) |
| **MEDIUM** | Armada | Auth token in URL query string (leaks via history/referer/logs) |
| **MEDIUM** | Armada | Unauthenticated `/api/report` and `/metrics` endpoints |
| **MEDIUM** | PGLease | GitHub Actions script injection via PR title |
| **MEDIUM** | SGLang | `eval()` on untrusted dataset fields (3 locations) |
| **MEDIUM** | SGLang | `eval()` on user input in demo code |
| **MEDIUM** | SGLang | `pickle.loads()` without integrity checks on IPC payloads |
| **LOW** | Armada | Dynamic SQL via f-strings (fragile, currently safe) |
| **LOW** | Armada | Weak CSP enables XSS (unsafe-inline/unsafe-eval) |
| **LOW** | Armada | Thin input validation at API boundaries |
| **LOW** | Armada | Token leaked to terminal/scrollback |
| **LOW** | PGLease | Unpinned third-party GitHub Actions |
| **LOW** | PGLease | Expression interpolation into shell |
| **LOW** | SGLang | Placeholder API keys in examples |

---

## 1. Armada (`/Users/armada/Projects/armadaai`)

### [MEDIUM] Token & DB files world-readable
- **File:** `armada_ai/infrastructure/auth_manager.py:43` — writes token with default umask, never `chmod 0o600`
- `~/.armada/token` and `*.db` are `0o644`; any local user can steal the auth token → full API/WS control
- **Fix:** `os.chmod(token_file, 0o600)` + restrict `~/.armada` to `0o700`

### [MEDIUM] Non-constant-time token comparison (timing side-channel)
- **Files:** `auth_manager.py:47` (`candidate==self._token`); `server.py:120,377,675` (`token==/!=TOKEN`)
- **Risk:** Attacker can measure response time to brute-force the token character-by-character
- **Fix:** Use `secrets.compare_digest()` for all token comparisons

### [MEDIUM] Auth token in URL query string
- **Files:** `cli.py:196,218` prints `http://<ip>:9100?token=<tok>`
- **Files:** `server.py:133,140` reads token from query string
- **Files:** `templates/index.html:1429,1916,1922,2116` embeds token in WebSocket URLs
- **Risk:** Leaks via shell history, browser history, Referer header, proxy/access logs
- **Fix:** Prefer `Authorization: Bearer` header; avoid token in printed URLs

### [MEDIUM] Unauthenticated endpoints
- **Files:** `/api/report` (writes node status to DB) and `/metrics` — auth-exempt via `AuthExemptPaths`
- **Risk:** Any local process can write status / read ops metrics with no token
- **Fix:** Require token or restrict to loopback + validate payload

### [LOW] Dynamic SQL via f-strings (fragile)
- **Files:** `database.py:170` (`ALTER TABLE ...{col} {col_type}`); `database.py:349` (`UPDATE nodes SET {','.join(parts)}`)
- Identifiers/clauses currently hardcoded constants, values parameterized → safe today, but fragile
- **Fix:** Whitelist identifiers explicitly; avoid f-string SQL construction

### [LOW] Weak CSP enables XSS
- **File:** `transport/middleware.py:36` — `script-src 'unsafe-inline' 'unsafe-eval'`
- Frontend mostly escapes via `esc()`, but some enum/colour fields at `index.html:1315-1317` are unescaped
- **Fix:** Drop `unsafe-eval`/`unsafe-inline`; nonce-based CSP; `esc()` all interpolated values

### [LOW] Thin input validation at boundaries
- Node name/agent_type, project id/path flow into DB + tmux session names + send-keys with no charset/length checks
- Mitigated by parameterized SQL & list-form subprocess (no injection), but no fail-fast validation
- **Fix:** Validate/whitelist at API boundary

### [LOW] Token leaked to terminal/scrollback
- **Files:** `cli.py:193,196,218,225` — prints token and token-bearing URLs; persists in shell history
- HTTP error logs are clean (only method+path, no query string)

### VERIFIED SAFE
- No hardcoded API keys/passwords/secrets in source
- No `eval()`/`exec()`/`os.system`/`shell=True` in Python
- SQL is parameterized (`?`) everywhere
- Token generation uses `secrets.token_hex(16)` (secure CSPRNG)

---

## 2. PGLease (`/Users/armada/Projects/pglease`)

### [MEDIUM] GitHub Actions script injection via PR title
- **File:** `.github/workflows/release.yml:62`
- `PR_TITLE="${{ github.event.pull_request.title }}"` — attacker-controlled PR title inlined into shell
- Runner has `contents: write` and access to `secrets.TEST_PYPI_API_TOKEN`
- **Fix:** Pass via `env:` block, never inline `${{ }}` into shell

### [LOW] Expression interpolation into shell
- **File:** `.github/workflows/publish-pypi.yml:21` — `inputs.confirm` inlined
- **Risk:** Low (workflow_dispatch needs write access)
- **Fix:** Same env-var hygiene as above

### [LOW] Unpinned third-party actions
- `softprops/action-gh-release@v1` and `pypa/gh-action-pypi-publish@release/v1` pinned to mutable tags
- **Fix:** Pin to full commit SHAs

### VERIFIED SAFE
- SQL injection: All identifiers use `psycopg2.sql.Identifier`; all values parameterized via `%s`
- No hardcoded secrets; `.gitignore` excludes `.pypirc`, `dist/`, `.venv`
- `_scrub_exc()` redacts DSN passwords from exceptions before logging
- No `eval`/`exec`/`os.system`/`subprocess`/`pickle.loads` on untrusted input
- Input validation: TTL validated >0 at boundaries; timeout=0 rejected
- Production PyPI publish uses OIDC Trusted Publisher (no stored token)

---

## 3. SGLang (`/Users/armada/Projects/sglang`)

### [HIGH] trust_remote_code=True hardcoded — RCE via model repos
- **Files:**
  - `model_loader/loader.py:655,663,668,696,2680`
  - `models/transformers.py:619`
  - `configs/model_config.py:160` (default `True`)
  - `configs/qwen3_asr.py:33` (default `True`)
- **Risk:** Forces arbitrary Python execution from model repos, bypassing `server_args.py:383` which defaults to `False`
- **Fix:** Thread `server_args.trust_remote_code` through loaders; never hardcode `True`

### [MEDIUM] eval() on untrusted dataset fields
- **Files:**
  - `benchmark/hicache/data_processing.py:244` — `eval(data["qa_pairs"])`
  - `benchmark/mmmu/data_utils.py:175` — `eval(sample["options"])`
  - `python/sglang/test/simple_eval_mmmu_vlm.py:142` — `eval(raw_options)`
- **Risk:** Arbitrary code execution if loading attacker-crafted datasets
- **Fix:** Use `ast.literal_eval()` or `json.loads()`

### [MEDIUM] eval() on user input in demo
- **File:** `python/sglang/test/test_programs.py:188` — `eval(expression)`
- **Fix:** Use `ast.literal_eval()` or sandbox

### [MEDIUM] pickle.loads() without integrity checks
- **Files:** `distributed/utils.py:189,209`, `shm_broadcast.py:455-461`, `parallel_state.py:1230`, `managers/multi_tokenizer_mixin.py:718`
- **Risk:** Trusted intra-host channels today, but no integrity verification; risky if exposed
- **Fix:** Apply existing `safe_unpickler` helper (`utils/common.py:2436`) consistently

### [LOW] Placeholder API keys in examples
- **File:** `multimodal_gen/.../server_api.py:522` — `sk-proj-1234567890`
- **File:** `examples/sagemaker/deploy_and_serve_endpoint.py:17`
- **Fix:** Use `YOUR_API_KEY_HERE` or env var reference

### VERIFIED SAFE
- No real hardcoded credentials (all hits are test placeholders)
- SQL injection: None in request path; only local SQLite trace analysis with static queries
- No auth tokens/secrets in logs (all "token" references are NLP tokenizer tokens)
- `.eval()`/`mx.eval()` hits are PyTorch/MLX mode switches, not Python `eval()`

---

## Recommendations

1. **Immediate (Armada):** Fix token file permissions — `chmod 0o600`, restrict `~/.armada` to `0o700`
2. **Immediate (SGLang):** Remove all hardcoded `trust_remote_code=True` — this is RCE
3. **Immediate (PGLease):** Fix CI script injection in `release.yml:62`
4. **Short-term (Armada):** Replace `==` with `secrets.compare_digest()` for token comparison
5. **Short-term (Armada):** Move token from query params to `Authorization` header; drop from printed URLs
6. **Short-term (Armada):** Add auth to `/api/report` and `/metrics`, or restrict to loopback
7. **Short-term (SGLang):** Replace all `eval()` calls with `ast.literal_eval()` or `json.loads()`
8. **Short-term (SGLang):** Apply safe unpickler consistently to all IPC payloads
9. **Hardening (Armada):** Tighten CSP (drop `unsafe-eval`/`unsafe-inline`); add input validation at API boundary
10. **Hardening (PGLease):** Pin GitHub Actions to commit SHAs
