# Finding 09 — Crypto Determinism Test Coverage (HMAC-IV)

**Author:** Villager Dev
**Date:** 2026-05-01
**Severity:** **major** (blocker if AppSec confirms semantic risk)
**Owners:** **AppSec** (cryptographic review), Villager Dev (test
additions once AppSec approves)

---

## Summary

The sprint's headline crypto change (commit `4d53f79`, "deterministic
HMAC IV for tree objects enables true CAS deduplication") added two
new methods to `Vault__Crypto`:

- `encrypt_deterministic(key, plaintext) -> bytes` (Vault__Crypto.py:162)
- `encrypt_metadata_deterministic(key, plaintext) -> str` (Vault__Crypto.py:172)

These are now used at **8 call sites** in `Vault__Sub_Tree.py` (lines
81, 82, 83, 84, 106, 156, 157, 158, 159, 181, 245).

**There is zero direct test coverage for these new methods.**

```
$ grep -rn 'encrypt_deterministic' tests/
(no output)
```

## What the contract demands

For HMAC-IV deterministic encryption to be a correct CAS-dedup
primitive, three properties must hold:

1. **Determinism:** `encrypt_deterministic(K, P) == encrypt_deterministic(K, P)` byte-for-byte.
2. **Decryptability:** `decrypt(K, encrypt_deterministic(K, P)) == P`.
3. **IV-derivation isolation:** `encrypt_deterministic(K, P)` for two
   different `K` keys must produce different IVs (otherwise an attacker
   reusing IVs across keys could exploit AES-GCM IV-reuse weaknesses
   if the keys leak).

A fourth security-sensitive property (AppSec-owned, not Villager Dev):

4. **Backward compatibility** — old random-IV ciphertexts produced
   pre-sprint must still decrypt with the new code (no migration
   needed). The change is on the encrypt side only; decrypt is
   IV-prefix-agnostic, so this should hold, but a test must
   prove it.

## Test gap

| Property | Test exists? |
|----------|--------------|
| 1. Determinism (same key + same plaintext → same ciphertext) | **NO** |
| 2. Round-trip decryptability | **NO** (transitively yes via Sub_Tree tests, but not direct) |
| 3. Different keys → different IVs | **NO** |
| 4. Old random-IV ciphertext still decrypts | **NO direct test**; pre-sprint test files exist with stored fixtures, but those use random IV at write time so they re-encrypt every run |
| Cross-language interop vector (matches browser Web Crypto + HMAC-SHA256[:12]) | **NO** |

The closest existing test is
`tests/unit/crypto/test_Vault__Crypto__Hardening.py:52`:

```python
def test_encrypt__deterministic_with_same_iv(self):
    ...
```

This tests the **non-deterministic** `encrypt(key, plaintext, iv=...)`
path with an explicitly supplied IV — i.e., it confirms that "if I
pass the IV, ciphertext is the same". It does **not** cover the new
`encrypt_deterministic` (which derives the IV via HMAC). Verbatim
search confirms the new method has no test.

## Test-vectors gap

CLAUDE.md "Crypto Interop Requirement":

> All crypto operations (AES-256-GCM, HKDF-SHA256, PBKDF2) must
> produce output that matches the browser (Web Crypto API)
> byte-for-byte given the same inputs. **Test vectors are mandatory.**

`encrypt_deterministic` is a new crypto operation. **No browser test
vector exists in the repo** (verified by searching for
`encrypt_deterministic` and `hmac` in `tests/`). Per the
mandatory-test-vectors rule, this is a **rule violation**.

## Coverage gap on call-sites

`Vault__Sub_Tree.py` writes 9 fields per tree (folder name, file name,
size, content_hash, content_type, plus the tree object itself) using
`encrypt_metadata_deterministic` and `encrypt_deterministic`. The
existing `test_Vault__Sub_Tree.py` has 16 tests but **none assert
that two builds of the same tree from the same flat-map produce the
same `tree_id`** — the entire point of the sprint change. The
"true CAS deduplication" claim from commit message `4d53f79` has no
test that locks it.

## Suggested next-action

This finding is **handoff-ready for AppSec**. Recommended test set
(to be drafted by AppSec or Villager Dev under AppSec review):

1. `test_encrypt_deterministic_same_input_same_output`
2. `test_encrypt_deterministic_different_keys_different_iv` (assert
   IV byte-prefix differs)
3. `test_encrypt_deterministic_round_trip`
4. `test_encrypt_deterministic_iv_is_hmac_prefix` (lock the IV
   construction: `iv == hmac.new(key, plaintext, sha256).digest()[:12]`)
5. `test_encrypt_deterministic_browser_interop` — must match the
   Web Crypto API output for a fixed `(key, plaintext)` pair. The
   browser test vector file location and format is AppSec-owned.
6. `test_sub_tree_build_from_flat_is_deterministic` — same flat_map
   → same `tree_id` (locks the CAS dedup property end-to-end).
7. `test_decrypt_pre_sprint_random_iv_blob` — keep one stored
   ciphertext from pre-sprint as a fixture, assert it still decrypts.

## Severity rationale

**major** (escalation candidate to **blocker** pending AppSec). The
core sprint feature introduces new cryptographic primitives without
any direct tests, in violation of the "test vectors mandatory" rule.
The 8 call sites in `Vault__Sub_Tree` mean any silent regression in
`encrypt_deterministic` will corrupt the entire vault tree-object
graph, which is the substrate for refs, branches, and CAS dedup.

## Escalations

- **AppSec** owns this finding. Villager Dev hand-off is
  contained here; the file is structured for AppSec to file the
  cryptographic-correctness review and to define what counts as
  "browser-interop" coverage.
