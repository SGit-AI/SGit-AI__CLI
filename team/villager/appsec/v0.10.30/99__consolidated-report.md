# 99 — Villager AppSec v0.10.30 Consolidated Report

**Author:** Villager AppSec
**Date:** 2026-05-01
**Branch:** `claude/villager-multi-agent-setup-sUBO6`
**Phase:** 1 (deep analysis, read-only)

## 1. Headline

The v0.10.30 capability set (deterministic HMAC IV, `probe`, `delete-on-remote`,
`rekey`, sparse clone, surgical `write`) is **cryptographically sound** under
the documented threat model. **No reachable plaintext-leak path was found.**
Two real bugs and a handful of hardening opportunities are listed below.

The most consequential finding is that the **adversarial test suite is
materially weaker than the new attack surface deserves**: 6 of 10 planned
adversarial mutations would slip through current tests undetected (see
M00).

## 2. Findings Summary

| # | Topic | Severity | Disposition |
|---|-------|----------|-------------|
| F01 | Deterministic HMAC IV — leakage map | MEDIUM (residual) | DOCUMENT |
| F02 | Rekey key-material lifecycle | MEDIUM | REAL-FIX (secure-unlink) + DOCUMENT |
| F03 | PBKDF2 LRU memory residency | MEDIUM (CLI) / HIGH (agent) | REAL-FIX for agent contexts |
| F04 | Probe leakage | LOW | DOCUMENT + small UX |
| F05 | Delete-on-remote auth | LOW (CLI) / TEST GAP | TEST (real-server) |
| F06 | Sparse clone access patterns | LOW | DOCUMENT |
| F07 | `clone_mode.json` plaintext read_key | MEDIUM | ACCEPTED (per Dinis) + chmod 0600 |
| F08 | `write_file` encryption equivalence | LOW | OK + 3 tests |
| F09 | `push_state.json` contents | LOW | OK + schema-allowlist test |
| F10 | Logging / error / debug-log | LOW | OK + 3 capsys tests |
| F11 | Token handling | LOW | DOCUMENT + chmod 0600 |
| F12 | Dependency CVE / version audit | MEDIUM (env divergence) | REAL-FIX (CI integration) |

## 3. HMAC-IV Concrete Leakage Map (F01 summary)

The deterministic IV `iv = HMAC(read_key, plaintext)[:12]` enables tree-level
CAS deduplication. Under this scheme:

- **Server CAN learn (ciphertext-only):**
  - Equality of any two encrypted metadata fields within a vault (same
    `name_enc` ⇒ same plaintext name; same for `size_enc`, `content_hash_enc`,
    `content_type_enc`).
  - Equality of any two encrypted tree objects within a vault (same tree-id
    ⇒ same tree contents).
  - Per-commit subtree churn pattern (which folders changed between commits).
  - Per-vault structural fingerprint over time (size of tree, number of
    distinct subtrees, etc.).
- **Server CANNOT learn (without the read_key):**
  - The plaintext of any encrypted field — names, sizes, hashes, MIME, file
    bodies. AES-GCM IND-CPA is preserved.
  - Any key material — read_key, write_key, vault_key, passphrase — none
    flow into the ciphertext or IV in a key-recoverable way.
  - Cross-vault correlation. Two vaults with **the same filename** produce
    **different `name_enc`** because their `read_key`s are different.
- **Realistic attacker scenarios documented:** server detective (defeated
  without key), CAS-dedup pattern correlation (intended; mitigation = put
  high-churn data in a separate vault), filename-equality dictionary within
  one vault (marginal info-leak).

**No code change required.** The construction is sound. The leakage surface
should be added to the user-facing security model so users can decide
whether to put highly sensitive small files in separate vaults.

## 4. Top 3 Findings

### 4.1 Test-suite mutation coverage gap (cross-cutting; see M00)

**Severity:** MEDIUM. 6 of 10 adversarial mutations slip through. Notable:
- **M7** — replacing `crypto.encrypt(read_key, file_content)` with the
  identity in `write_file` (`sgit_ai/sync/Vault__Sync.py:282`) would NOT be
  detected by any current test.
- **M1/M2** — replacing HMAC with plain SHA-256 in `encrypt_deterministic`
  (`sgit_ai/crypto/Vault__Crypto.py:169`) would NOT be detected.
- **M9** — making `probe_token` write disk artefacts undetected.

**Concrete code reference:** `Vault__Sync.py:282`, `Vault__Crypto.py:169`,
`Vault__Sync.py:1820-1830`.

### 4.2 PBKDF2 LRU passphrase residency (F03)

**Severity:** MEDIUM (CLI), HIGH (long-running agent). Old passphrases and
derived keys remain in `_pbkdf2_cached` until process exit OR LRU eviction
(maxsize=256). Critical for v0.10.30's agent-friendly use cases.

**Concrete code reference:** `sgit_ai/crypto/Vault__Crypto.py:26-32`.

### 4.3 Filesystem-mode hygiene (F07, F11, F02)

**Severity:** MEDIUM aggregated. Files holding key material in `.sg_vault/local/`
are written with default umask (typically `0644`). Multi-user host enables
key theft by any local user.

**Concrete code references:** `Vault__Sync.py:1551, 1655` (clone_mode.json),
`CLI__Token_Store.py:42-43` (token), `Vault__Storage` callers (vault_key).

## 5. Real-Fix-Needed vs Accepted-Risk-Document-Only

### Real fixes (small, well-scoped)

1. **`os.chmod(path, 0o600)`** on every save in `.sg_vault/local/` (F02, F07,
   F11). Single helper.
2. **`_secure_unlink(path)`** helper that overwrites then unlinks; apply in
   `rekey_wipe` (F02).
3. **`Vault__Crypto.clear_kdf_cache()`** + wire into rekey/probe/delete (F03).
4. **Defensive `if not c.write_key: raise` at top of `write_file`** (F08).
5. **Add `pip-audit` step to CI** + investigate why dev env has
   `cryptography 41.0.7` instead of `>=43.0.0` (F12).

### Accepted-risk / document-only

- `clone_mode.json` storing `read_key_hex` (F07; per Dinis).
- New `vault_key` printed to stdout during `sgit rekey` (F11; per Dinis).
- HMAC-IV structural leakage to server (F01; per Dinis).
- `delete-on-remote` cannot guarantee server-side ciphertext destruction (F05).
- Sparse-clone access pattern visible to server (F06).
- `probe_token` is a token-existence oracle by design (F04).

## 6. Escalations

### To Architect

- **F04** — Confirm Simple_Token spec mandates server-side rate-limiting on
  `bare/indexes/...` GET to prevent token enumeration.
- **F03** — If multi-tenant agent host is a v0.11.x target, design a proper
  passphrase-scope abstraction with explicit lifetime management. Today's
  module-level LRU is a leak.
- **F11** — Decide on osbot-utils pin policy (`>=` vs `~`).

### To Dev

- **F08** — Defensive `write_file` read-only guard.
- **F02 / F07 / F11** — chmod 0600 helper + secure-unlink helper. One small PR.
- **F03** — `Vault__Crypto.clear_kdf_cache()` method.
- **Type_Safe modelling** for `clone_mode.json` and `push_state.json`
  (currently dicts, no schema). A `Schema__Clone_Mode` and
  `Schema__Push_State` would let the round-trip invariant guarantee the
  field allowlist (closes M8 mutation gap structurally).

### To QA Phase 3

- Execute the full M00 mutation matrix; for each U/P entry, write the
  missing test before reverting the mutation.
- Add the `capsys` regression tests from F10 / F11.

### To DevOps

- Add `pip-audit --strict` to CI (F12).
- Add `pip check` to CI to catch resolver divergence.
- F05 M10: integration test for `delete_vault` write-key enforcement against
  a real `sgraph-ai-app-send` instance.

## 7. Test-Suite Bugs Not Found / Not Found

I scanned the unit tests for "wrong-reason passing" patterns. None of the
security-relevant tests I read (`test_AppSec__Vault_Security.py`,
`test_Vault__Crypto__Hardening.py`, `test_Vault__Sync__Delete_Rekey.py`,
`test_Vault__Sync__Probe.py`, `test_Vault__Sync__Write_File.py`) compared
the wrong objects or asserted trivially-true conditions. They are correct;
they are merely **incomplete** for the new v0.10.30 surface.

No fixture or test prints key material to stdout during normal pytest runs
that I could find.

## 8. Could Not Complete in Time Budget

- I did **not** run the M1–M10 mutations live. Per role rules, this is QA
  Phase 3 work. All findings above are based on code reading + existing
  test inspection.
- I did **not** run `pip-audit` because it is not installed in the sandbox.
  CVE assessment is based on the cryptography release notes I could read.
- I did **not** read every CLI sub-command file end-to-end (Stash, Branch,
  Diff, Dump). Spot-checked for plaintext leaks via grep; none surfaced.
- I did **not** validate the `Simple_Token` derivation against external
  test vectors — Architect to confirm that's already covered by
  `test_Vault__Crypto__Cross_Language_Vectors`.

## 9. Bottom Line

v0.10.30 is **release-blockable on M00 test gaps and the F12 environment
divergence**. The crypto envelope itself is sound. With a small hardening PR
(chmod 0600, secure unlink, clear_kdf_cache, write_file guard) and a QA
Phase 3 mutation-coverage sprint (~6 hours), the new surface meets the
zero-knowledge bar.

**No P0 (immediate-stop) findings. Two P1s (test-coverage gap, environment
pin divergence). Roughly eight P2/P3 hardening items.**
