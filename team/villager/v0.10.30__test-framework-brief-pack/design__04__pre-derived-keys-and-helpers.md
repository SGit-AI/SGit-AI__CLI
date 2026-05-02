# Design — Pre-Derived Keys + Helpers Relocation (D4)

**Status:** Captured. Drives brief B03.

Two related concerns wrapped in one design:

1. A session-scoped fixture exposing **pre-derived keys** for a small
   set of canonical test vault_keys.
2. **Relocate `Vault__Test_Env`** from `tests/unit/sync/` to
   `tests/_helpers/` so test sub-directories outside `sync/` can use it.

---

## Pre-derived key cache (`known_test_keys`)

### Why

PBKDF2 with 600k iterations costs ~50–100 ms per derivation. The
existing `lru_cache(maxsize=256)` on `_pbkdf2_cached` blunts this
within a process — but only for repeat calls with the same passphrase.
Tests use unique passphrases by convention (each test class picks its
own), so cache hit rate is low across tests.

### What

A session-scoped fixture exposing pre-derived keys for ~5 canonical
test vault_keys:

```python
# tests/conftest.py
@pytest.fixture(scope='session')
def known_test_keys():
    crypto = Vault__Crypto()
    return {
        'coral-equal-1234'  : crypto.derive_keys_from_vault_key('coral-equal-1234'),
        'give-foul-8361'    : crypto.derive_keys_from_vault_key('give-foul-8361'),
        'azure-hat-7-9912'  : crypto.derive_keys_from_vault_key('azure-hat-7-9912'),
        'plum-stack-4-5566' : crypto.derive_keys_from_vault_key('plum-stack-4-5566'),
        'olive-fern-2-1133' : crypto.derive_keys_from_vault_key('olive-fern-2-1133'),
    }
```

Each entry is the dict already returned by `derive_keys_from_vault_key`:
`vault_id`, `read_key_bytes`, `write_key_bytes`, `branch_index_file_id`, etc.

### Estimated savings

~50–100 ms per consumer. If ~80 tests across the suite consume known
keys, that's **~4–8 s suite-wide**.

### Consumers

Any test that:
- Needs `read_key_bytes` / `write_key_bytes` for a known vault_key.
- Uses a pre-built fixture (F3–F6, NF1–NF5) and wants to look up the
  derived keys for assertions.
- Tests a non-derivation crypto path that needs key bytes as input.

### Mutation contract

`derive_keys_from_vault_key` returns immutable bytes-and-strings only;
the fixture returns the same dict to every consumer (no defensive
copy). If a test mutates the returned bytes-objects in place (Python
won't let them, since `bytes` is immutable), there's no pollution.
For dict-level mutation, the consumer is expected to copy if needed —
documented in the fixture's docstring.

---

## `Vault__Test_Env` relocation

### Why

`Vault__Test_Env` lives at `tests/unit/sync/vault_test_env.py`. Tests
in `cli/`, `api/`, `objects/`, `transfer/`, `appsec/` would benefit
but currently don't import it (cross-namespace test imports are
awkward). This is THE reason `test_CLI__Commands.py` has 9 raw setups
instead of using `setup_single_vault`.

### Where it goes

```
tests/
├── _helpers/                          NEW
│   ├── __init__.py                    (yes — _helpers/ is helper code, not tests)
│   ├── vault_test_env.py              moved from tests/unit/sync/
│   ├── snapshot_helpers.py            (any shared snapshot/copytree utilities that emerge from D2's NF1–NF5)
│   └── crypto_helpers.py              (pre-derived key helpers if they grow beyond a fixture)
│
├── conftest.py                        NEW (root) — exports session-wide fixtures
│
├── unit/                              existing
│   ├── sync/conftest.py               existing — keeps sync-only fixtures
│   ├── cli/conftest.py                existing — keeps cli-only fixtures
│   └── ...
│
└── integration/                       existing
```

**Note on `__init__.py`:** project rule says "no `__init__.py` under
`tests/`". `tests/_helpers/__init__.py` is the **only** exception we
accept, scoped to that one folder. Reasoning: `_helpers/` is helper
code, not tests; pytest test collection rules don't apply to it; and
the leading underscore signals "not a test directory". **Confirm with
Dinis before B03 ships this exception.** If Dinis prefers no
exceptions, `_helpers/` becomes a flat module set with no package
boundary (acceptable but slightly less clean).

### Forwarding shim during transition

`tests/unit/sync/vault_test_env.py` becomes a one-line forwarding import:

```python
# tests/unit/sync/vault_test_env.py
from tests._helpers.vault_test_env import *   # noqa: F401, F403
```

Existing imports keep working; new code uses `tests._helpers.vault_test_env`
directly. The shim can be deleted in a future cleanup pass.

### Acceptance

- `Vault__Test_Env` accessible from any test file via
  `from tests._helpers.vault_test_env import Vault__Test_Env`.
- Existing sync tests still work without modification (forwarding shim).
- `tests/conftest.py` (root) re-exports `known_test_keys`, the new
  fixtures from D2 (NF1–NF5), and the precomputed-blob fixture from D3.

---

## Where the fixtures live, post-relocation

| Fixture | Location |
|---|---|
| F1, F2 (PKI) | `tests/unit/cli/conftest.py` (cli-only — stays) |
| F3, F4 (bare vault) | `tests/unit/sync/conftest.py` (sync-only — stays) |
| F5 `probe_vault_env` | move to `tests/conftest.py` (used by sync; could be cross-cutting) |
| F6 `simple_token_origin_pushed` | `tests/unit/sync/conftest.py` (narrow consumer set — stays) |
| NF1 `two_clones_pushed` | `tests/conftest.py` (cross-cutting) |
| NF2 `vault_with_N_commits` | `tests/conftest.py` |
| NF3 `vault_with_pending_changes` | `tests/conftest.py` |
| NF4 `vault_with_branches` | `tests/conftest.py` |
| NF5 `read_only_clone` | `tests/conftest.py` |
| `known_test_keys` | `tests/conftest.py` |
| `precomputed_encrypted_blobs` | `tests/conftest.py` |

## Acceptance for this design

- `known_test_keys` fixture signature locked.
- `Vault__Test_Env` relocation path agreed (with the one
  `tests/_helpers/__init__.py` exception, pending Dinis confirmation).
- Forwarding shim strategy agreed.
- Brief B03 implements both concerns.
