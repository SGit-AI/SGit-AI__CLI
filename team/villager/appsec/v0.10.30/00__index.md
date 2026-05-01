# Villager AppSec — v0.10.30 Deep Analysis Index

**Author:** Villager AppSec
**Date:** 2026-05-01
**Branch:** `claude/villager-multi-agent-setup-sUBO6`
**Plan:** `team/villager/appsec/v0.10.30__plan__deep-analysis.md`

## Files

| File | Topic | Severity | Disposition |
|------|-------|----------|-------------|
| [F01](F01__hmac-iv-determinism.md) | Deterministic HMAC IV — concrete leakage map and verified-no-key-exposure proof | MEDIUM (residual) | DOCUMENT |
| [F02](F02__rekey-key-material.md) | Rekey lifecycle: unlink-not-wipe of old `vault_key`; abort window between wipe and init | MEDIUM | REAL-FIX (secure-unlink) + DOCUMENT |
| [F03](F03__pbkdf2-lru-residency.md) | `_pbkdf2_cached` retains old passphrases in process memory indefinitely | MEDIUM (CLI) / HIGH (agent) | REAL-FIX for agent contexts |
| [F04](F04__probe-leakage.md) | `probe_token`: error-message hash echo, no disk artefacts, token-existence oracle by design | LOW | DOCUMENT + small UX |
| [F05](F05__delete-on-remote.md) | `delete-on-remote`: write-key auth header not asserted by unit tests; server-side destruction is best-effort | LOW + TEST GAP | TEST (real-server) |
| [F06](F06__sparse-clone-side-channels.md) | Sparse clone / fetch / cat: server sees per-blob access pattern | LOW | DOCUMENT |
| [F07](F07__clone-mode-plaintext-keys.md) | `clone_mode.json` stores plaintext `read_key_hex`; consistent with vault_key file but world-readable | MEDIUM | ACCEPTED (per Dinis) + chmod 0600 |
| [F08](F08__surgical-write-path.md) | `write_file` uses identical encryption primitives as commit; no read-only guard at top of function | LOW | OK + 3 tests + 1 small guard |
| [F09](F09__push-checkpoint-contents.md) | `push_state.json` schema verified clean (vault_id, clone_commit_id, blobs_uploaded only) | LOW | OK + schema-allowlist test |
| [F10](F10__logging-error-hygiene.md) | Debug log URL audit, progress message audit, error-path scan — no key material leaks | LOW | OK + 3 capsys tests |
| [F11](F11__token-handling.md) | Token persistence in `.sg_vault/local/` files; rekey stdout print; no out-of-vault token leaks | LOW | DOCUMENT + chmod 0600 |
| [F12](F12__dependency-audit.md) | Pin floor `cryptography>=43.0.0` is fine; sandbox env actually has `41.0.7` (env divergence) | MEDIUM (env) | REAL-FIX (CI integration) |
| [M00](M00__mutation-test-matrix.md) | 10-mutation adversarial matrix — 6 of 10 currently UNDETECTED by test suite | — | QA Phase 3 |
| [99](99__consolidated-report.md) | Narrative consolidated report, top-3 findings, escalations, real-fix vs document-only | — | — |

## How to Read This Set

1. Start with `99__consolidated-report.md` for the executive view.
2. F01 has the **HMAC-IV concrete leakage map** Dinis asked for.
3. M00 lists the test-coverage gaps QA must close in Phase 3.
4. Each F-file is self-contained and ≤200 lines per Villager rules.

## Disposition Summary

- **0 P0 findings** (no immediate-stop issues; no plaintext or key leak found).
- **2 P1 findings**: F12 environment-pin divergence; M00 mutation coverage gap.
- **8 P2/P3 hardening items**: chmod 0600, secure-unlink, clear_kdf_cache,
  write_file guard, three Type_Safe schemas, three regression tests, two
  doc additions.

## Escalations

- **Architect**: F04 (rate-limit policy), F03 (multi-tenant agent design),
  F11 (osbot-utils pin policy).
- **Dev**: F08 (defensive guard), F02/F07/F11 (chmod helper, secure-unlink),
  F03 (clear_kdf_cache method), Type_Safe schemas for clone_mode and
  push_state.
- **QA Phase 3**: full M00 execution, plus capsys regression tests from
  F10/F11.
- **DevOps**: F12 `pip-audit` CI integration, F05 real-server integration
  test for write-key enforcement.
