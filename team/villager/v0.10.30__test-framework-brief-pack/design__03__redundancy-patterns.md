# Design — Encryption Redundancy Patterns (D3)

**Status:** Captured. Drives brief B04.

The "no mocks" rule is non-negotiable, but **incidental encryption
work** in tests that aren't testing encryption is wasteful. These are
five concrete patterns where encryption runs because the test needs
"a vault" or "an encrypted blob" as setup, not because it's
exercising the crypto path itself.

---

## P1 — Diff / log / blame tests building history through full commit cycles

**Symptom:** A test for `sgit diff <commit>` does
`init → write file → commit → write file → commit` to get a 2-commit
history. Each `commit` runs full encryption + tree-build + ref-write
(~400 ms × 2 = ~800 ms).

**Remediation:** Use **NF2 `vault_with_N_commits(2)`** from D2. Same
end state, ~5 ms instead of ~800 ms.

**Affected files:** `test_Vault__Diff.py`, `test_Vault__Diff__Coverage.py`,
`test_Vault__Inspector__Coverage.py`, `test_Vault__Dump_Diff.py`.

---

## P2 — Inspect tests building a vault to inspect

**Symptom:** `test_Vault__Inspector__Coverage.py` has 8 `Vault__Crypto()`
+ `Vault__Sync()` instantiations to set up vaults whose only purpose
is to be inspected. The setup encryption work is incidental.

**Remediation:** Use **NF2 `vault_with_N_commits`** or **F3
`bare_vault_workspace`** (depending on whether the inspector needs a
working copy).

---

## P3 — CLI command tests that init a vault to test a downstream command

**Symptom:** `test_CLI__Commands.py` has 9 raw setups. Each test
init's a vault to test a command like `sgit status` or `sgit branch`.
The init+commit work is purely scaffolding.

**Remediation:** Use **`Vault__Test_Env.setup_single_vault`** (post-D4
relocation) or **NF2 / NF3** depending on what state the command
needs.

---

## P4 — AppSec / crypto tests deriving keys for non-derivation work

**Symptom:** `test_AppSec__Vault_Security.py` derives keys from
passphrase to test something non-derivation (e.g., that a stored
ciphertext is non-empty). Each derivation is ~50–100 ms (PBKDF2
600k).

**Remediation:** Use the **`known_test_keys` session fixture from D4**
which exposes pre-derived `read_key_bytes` / `write_key_bytes` /
`vault_id` for a small set of canonical test vault_keys.

---

## P5 — Object-store tests building blobs to test load/save paths

**Symptom:** `test_Vault__Sub_Tree__Determinism.py` and similar tests
encrypt fresh blobs to test that they can be loaded back. The
encryption itself isn't under test — the storage round-trip is.

**Remediation:** Add a session-scoped `precomputed_encrypted_blobs`
fixture exposing a dict `{name: ciphertext_bytes}` for a small set of
known plaintexts encrypted under a known key. Tests that need "an
encrypted blob to load" use this.

```python
@pytest.fixture(scope='session')
def precomputed_encrypted_blobs():
    crypto   = Vault__Crypto()
    read_key = crypto.derive_keys_from_vault_key('coral-equal-1234')['read_key_bytes']
    return {
        'small'  : crypto.encrypt(read_key, b'small content'),
        'medium' : crypto.encrypt(read_key, b'medium content' * 100),
        'large'  : crypto.encrypt(read_key, b'large content'  * 10_000),
    }
```

---

## What this design leaves to the briefs

- Brief B04 audits the test suite against P1–P5, applies the matching
  fixture to each affected test, measures the savings.
- Brief B04 produces a short closeout doc listing any tests that still
  do incidental encryption after the pass — these become the seed for
  future redundancy-cleanup work.

## What this design is NOT

- Not a removal of any test. Every existing scenario stays.
- Not an introduction of mocks. All replacements use real (pre-built,
  shared-via-copy) objects.
- Not a complete enumeration. The five patterns are the dominant ones;
  others may surface during the audit pass.

## Acceptance for this design

- Five patterns named with at least one example file each.
- Each pattern maps to a fixture (existing F1–F6 / `Vault__Test_Env`,
  or new NF1–NF5 / `known_test_keys` / `precomputed_encrypted_blobs`).
- Brief B04 has a clear remediation for each pattern.
- The "no mocks" rule is preserved throughout.
