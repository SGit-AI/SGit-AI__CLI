# QA Test Split Refactoring (2026-05-05)

## Why

Some unit tests were taking 1–4 seconds each even though all work was
in-memory or local-disk. The cause: cryptographic operations that are
intentionally expensive.

### Root causes identified

| Root cause | Example test | Duration |
|---|---|---|
| PBKDF2 (100k iterations, by design) | `test_Simple_Token__Vault_Keys` | ~1.1 s/test |
| RSA-4096 keygen (inherently slow) | `test_CLI__PKI` export/import tests | 0.6–1.9 s/test |
| NF fixtures: full init+commit+push setup | `test_Vault__Sync__Probe`, `test_Vault__Sync__Simple_Token` | 2.2 s/class |
| PBKDF2 KDF cache bounded-size test | `test_Vault__Crypto__KDF_Cache` | ~1.0 s |
| Known-test-keys fixture (5× PBKDF2) | `test_known_test_keys` | ~1.0 s |

These are **valid, non-removable tests** — the slowness reflects real
system behaviour that must be verified. Moving them out of the default
unit path keeps `pytest tests/unit/` fast for development feedback loops.

## What was moved

Files moved from `tests/unit/` to `tests/qa/`:

```
tests/unit/cli/test_CLI__PKI.py
    → tests/qa/crypto/test_CLI__PKI.py

tests/unit/crypto/test_Vault__Crypto__KDF_Cache.py
    → tests/qa/crypto/test_Vault__Crypto__KDF_Cache.py

tests/unit/transfer/test_Simple_Token__Vault_Keys.py
    → tests/qa/crypto/test_Simple_Token__Vault_Keys.py

tests/unit/sync/test_Vault__Sync__Simple_Token.py
    → tests/qa/sync/test_Vault__Sync__Simple_Token.py

tests/unit/sync/test_Vault__Sync__Probe.py
    → tests/qa/sync/test_Vault__Sync__Probe.py

tests/unit/sync/test_Vault__Sync__Probe_Artefacts.py
    → tests/qa/sync/test_Vault__Sync__Probe_Artefacts.py

tests/unit/_fixtures/test_known_test_keys.py
    → tests/qa/_fixtures/test_known_test_keys.py
```

Conftest fixtures were re-exported via thin shim files:
- `tests/qa/crypto/conftest.py` — re-exports `pki_keypair_snapshot`, `pki_workdir`
- `tests/qa/sync/conftest.py` — re-exports `bare_vault_snapshot`, `bare_vault_workspace`,
  `probe_vault_env`, `simple_token_origin_pushed`

## Coverage impact

| Scope | Coverage |
|---|---|
| Before split (unit + QA mixed) | 95.9% |
| After split (unit only) | 94.4% |
| Delta | −1.5 pp |

The 1.5 pp drop comes from `CLI__PKI.py` (RSA paths), sync probe paths,
and simple-token PBKDF2 paths that are now exercised only in QA runs.

## How to run each tier

```bash
# Fast unit tests (development loop — ~2.5 min)
pytest tests/unit/

# QA tests (CI mutation/slow phase — ~40 s additional)
pytest tests/qa/

# Full combined coverage measurement
pytest tests/unit/ tests/qa/ --cov=sgit_ai --cov-report=term-missing
```

## What was NOT moved

`tests/unit/crypto/test_Vault__Crypto.py` was kept in unit despite having
three simple-token tests (~1 s each). The majority of that file exercises
fast KDF-cache paths, so the overall file is still fast enough for the unit
tier.

## Invariant to maintain

When adding new tests that invoke PBKDF2, RSA keygen, or NF fixtures
(fixtures that do `sync.init + commit + push`), place them in `tests/qa/`
rather than `tests/unit/`. The criterion: **if a single test class setup
takes >500 ms, it belongs in QA**.
