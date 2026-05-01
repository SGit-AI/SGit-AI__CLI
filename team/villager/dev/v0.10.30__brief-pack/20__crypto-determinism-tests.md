# Brief 20 — Crypto-determinism tests

**Owner role:** **Villager AppSec** (test-vector design, M1/M2 closure) +
**Villager Dev** (implementation)
**Status:** Ready to execute.
**Prerequisites:** None.
**Estimated effort:** ~3–4 hours
**Touches:** new tests under `tests/unit/crypto/`; possibly under
`tests/unit/objects/`. No source.

---

## Why this brief exists

All three Villager angles independently flagged this in the deep
analysis:

- **Architect finding 01 + 08**: HMAC-IV change shipped with zero direct
  tests for the determinism property. The debrief's "3 determinism
  assertions" do not exist.
- **Dev finding 09**: `encrypt_deterministic` and
  `encrypt_metadata_deterministic` have zero direct tests across 8 call
  sites in `Vault__Sub_Tree`. No browser interop vector.
- **AppSec mutation matrix M1, M2**: replacing `hmac.new(key, plaintext,
  sha256)` with plain `hashlib.sha256(plaintext)` in
  `Vault__Crypto.py:169` would NOT be detected by any current test.

QA brief 01 nuanced this: `encrypt_deterministic` is *line-covered*
(99.2%) via tree-encryption call sites, but no test asserts the actual
**determinism property**. This is a behavioural gap, not a coverage gap.

The fix: add direct tests for the deterministic-encryption primitive,
including a cross-vault divergence test that closes M1/M2.

---

## Required reading

1. This brief.
2. `team/villager/architect/v0.10.30/01__hmac-iv-crypto-boundary.md`
   — five concrete test cases listed.
3. `team/villager/dev/v0.10.30/09__crypto-determinism-test-coverage.md`.
4. `team/villager/appsec/v0.10.30/F01__hmac-iv-determinism.md` —
   leakage envelope.
5. `team/villager/appsec/v0.10.30/M00__mutation-test-matrix.md` rows
   M1, M2, M3.
6. `team/humans/dinis_cruz/claude-code-web/05/01/v0.10.30/07__deterministic-hmac-iv-tree-deduplication.md`.
7. `sgit_ai/crypto/Vault__Crypto.py` — `encrypt_deterministic`,
   `encrypt_metadata_deterministic`. (~line 169)
8. `sgit_ai/objects/Vault__Sub_Tree.py` — the 8 call sites.

---

## Scope

**In scope:**
- Direct test of `encrypt_deterministic`:
  1. **Same input → same output** (determinism, line-by-line).
  2. **Different keys → different outputs** for the same plaintext
     (cross-vault divergence; closes M1/M2).
  3. **Round-trip** (decrypt undoes encrypt for the same key).
  4. **IV derivation property** — IV bytes match the HMAC-derived
     spec (closes M3 partial).
  5. **Browser interop vector** — at least one known-input → known-
     output pair, expressed as a JSON test vector that the browser-side
     implementation can verify against. Use the existing
     `test_Vault__Crypto__Cross_Language_Vectors` pattern if present;
     otherwise create one.
- Same five tests for `encrypt_metadata_deterministic`.
- A tree-id-determinism property test on `Vault__Sub_Tree.build*`:
  same plaintext map → same tree id; different `read_key` → different
  tree id.
- Update mutation matrix M1, M2, M3 rows.

**Out of scope:**
- Replacing the HMAC primitive.
- Documenting the leakage envelope in user-facing docs (separate brief
  if Dinis chooses).

**Hard rules:**
- Test vectors must be **reproducible** — fixed inputs, asserted exact
  outputs. No random data without fixed seeds.
- No mocks.
- Tests under Phase B parallel CI shape.
- Round-trip invariant: every encrypted output decrypts back to its
  input.

---

## Acceptance criteria

- [ ] At least 10 tests across the two functions.
- [ ] Cross-key divergence test exists and would fail if HMAC were
      replaced by SHA-256 (closes M1, M2).
- [ ] Tree-id-determinism property test exists.
- [ ] At least 1 browser interop vector recorded (JSON file or in-test
      hex literals).
- [ ] Mutation matrix M1, M2 → "D"; M3 → "D" (no longer partial).
- [ ] Coverage: `Vault__Crypto.py` ≥ 99.2% (no regression);
      `Vault__Sub_Tree.py` direct-method coverage on `build*` increases.
- [ ] Suite ≥ 2,105 + N passing.
- [ ] No new mocks.

---

## Deliverables

1. Test file `tests/unit/crypto/test_Vault__Crypto__Deterministic.py`.
2. Test additions to `tests/unit/objects/test_Vault__Sub_Tree.py` for
   tree-id determinism property.
3. Browser interop vector file or constants.
4. Mutation matrix updates.
5. Closeout entries on Dev finding 09 and Architect finding 01.

Commit message:
```
test(crypto): determinism + cross-vault divergence vectors

Closes Dev finding 09, Architect finding 01, AppSec mutations M1/M2/M3.
encrypt_deterministic and encrypt_metadata_deterministic now have
direct tests for: determinism, round-trip, IV-derivation property,
cross-key divergence, browser interop vector. Tree-id determinism
property added to Vault__Sub_Tree tests.

A SHA-256-for-HMAC swap or a key-independent IV change is now caught.

https://claude.ai/code/session_<id>
```

---

## When done

Return a ≤ 250-word summary:
1. Test count + names.
2. Mutation matrix rows updated.
3. Coverage delta.
4. Browser interop vector format chosen + one example hex pair.
5. Anything that surfaced about `encrypt_deterministic` correctness
   (escalate to AppSec if the cross-key divergence test FAILS — that
   would be a real cryptographic finding).
