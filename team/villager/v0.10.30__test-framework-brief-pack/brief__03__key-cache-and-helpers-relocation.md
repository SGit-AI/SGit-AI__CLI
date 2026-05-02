# Brief B03 — Key Cache + Helpers Relocation

**Owner role:** **Villager Dev**
**Status:** Ready (independent of B22).
**Prerequisites:** None.
**Estimated effort:** ~½–1 day
**Touches:** `tests/_helpers/` (new), `tests/conftest.py` (new root), `tests/unit/sync/vault_test_env.py` (becomes a forwarding shim).

---

## Why this brief exists

Per `design__04__pre-derived-keys-and-helpers.md`: two related concerns
in one small brief.

1. **`known_test_keys` session fixture** — pre-derived keys for ~5
   canonical test vault_keys. Saves ~50–100 ms per consumer × ~80
   consumers = ~4–8s suite-wide.
2. **Relocate `Vault__Test_Env`** to `tests/_helpers/` so cli/, api/,
   objects/, transfer/, appsec/ can use it without cross-namespace
   imports.

---

## Required reading

1. This brief.
2. `design__04__pre-derived-keys-and-helpers.md` (the design — read in full).
3. `tests/unit/sync/vault_test_env.py` (the file being relocated).
4. `CLAUDE.md` — note the project rule on `__init__.py` under `tests/`.

---

## Scope

### Step 1 — Create `tests/_helpers/`

No `__init__.py` — implicit namespace packages (PEP 420) handle the
imports. The project rule "no `__init__.py` under `tests/`" is preserved.

```
tests/_helpers/
└── vault_test_env.py    (moved from tests/unit/sync/)
```

Use `git mv` to preserve history.

### Step 2 — Forwarding shim

Replace `tests/unit/sync/vault_test_env.py` with:

```python
# Forwarding shim — relocated to tests/_helpers/ in v0.10.30 brief B03.
# Direct imports from this path still work; new code uses
# `from tests._helpers.vault_test_env import …` directly.
from tests._helpers.vault_test_env import *   # noqa: F401, F403
```

### Step 3 — Root `tests/conftest.py`

Create `tests/conftest.py` (root). It exports session-wide fixtures
that any test sub-directory can consume:

- `known_test_keys` — the new pre-derived-key cache (per D4).
- (placeholder for D2's NF1–NF5 — added by brief B02; add the imports here when B02 lands).
- (placeholder for D3's `precomputed_encrypted_blobs` — added by brief B04).

### Step 4 — `known_test_keys` fixture

Implement per design D4 §"Pre-derived key cache":

```python
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

Return value is the existing dict shape from
`derive_keys_from_vault_key`. No defensive copy on return; documented
in fixture docstring.

### Step 5 — Tests

Add `tests/unit/_fixtures/test_known_test_keys.py`:
- `test_known_test_keys_returns_all_five` — five keys present.
- `test_known_test_keys_values_are_correct` — derive one fresh, compare.
- `test_known_test_keys_session_scoped` — same dict identity across consumers in the same session.

Add `tests/unit/_fixtures/test_helpers_relocation.py`:
- `test_vault_test_env_imports_from_helpers` — direct import works.
- `test_vault_test_env_imports_from_old_path` — forwarding shim works.

---

## Hard constraints

- **No mocks.**
- **`tests/_helpers/__init__.py` only if Dinis approves the exception.**
- **Forwarding shim must work.** Existing imports `from tests.unit.sync.vault_test_env import …` keep working until a future cleanup removes the shim.
- **`Vault__Test_Env` semantics unchanged.** Only its import path.
- **Suite must pass under `-n auto`.**
- **Coverage must not regress.**

---

## Acceptance criteria

- [ ] `tests/_helpers/vault_test_env.py` exists; old path is a shim.
- [ ] `tests/conftest.py` (root) exports `known_test_keys`.
- [ ] At least 5 tests covering the relocation + key cache.
- [ ] Suite ≥ existing test count + 5 passing.
- [ ] Coverage delta non-negative.
- [ ] No source change to `sgit_ai/`.
- [ ] Closeout note appended to `team/villager/dev/v0.10.30__shared-fixtures-design.md` as §11.

---

## Out of scope

- Adopting `known_test_keys` into existing tests (brief B04).
- Implementing the five new fixtures from D2 (brief B02).
- Relocating any other helper file beyond `vault_test_env.py`.

---

## When done

Return a ≤ 200-word summary:
1. `_helpers/__init__.py` exception decision.
2. Forwarding shim status (working vs needed adjustment).
3. `known_test_keys` fixture verified with test count + scope.
4. Root `tests/conftest.py` shape (which fixtures it exports).
5. Coverage + suite-time delta.
