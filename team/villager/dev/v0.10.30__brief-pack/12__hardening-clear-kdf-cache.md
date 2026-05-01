# Brief 12 — Hardening: clear_kdf_cache for PBKDF2 LRU

**Owner role:** **Villager Dev** (primary) + **Villager AppSec** (review)
**Status:** Ready to execute.
**Prerequisites:** None.
**Estimated effort:** ~2 hours
**Touches:** `sgit_ai/crypto/Vault__Crypto.py`, callers in `cli/` and
`sync/`, tests under `tests/unit/crypto/`.

---

## Why this brief exists

AppSec finding F03 (severity MEDIUM CLI / **HIGH agent**): the
module-level `functools.lru_cache(maxsize=256)` on `_pbkdf2_cached` at
`sgit_ai/crypto/Vault__Crypto.py:26-32` retains old passphrases and
derived keys in process memory until process exit OR LRU eviction.

For one-shot CLI runs this is brief and usually fine. For long-running
agent contexts (the agent-friendly write/cat/ls/probe surface added this
sprint), the cache becomes a passphrase residency problem: an old
passphrase used for a previous vault stays in process memory forever.

The fix is a `Vault__Crypto.clear_kdf_cache()` method (or equivalent)
that wipes the cache, plus call-site wiring at the natural eviction
moments: end of rekey, end of probe, end of delete-on-remote, and
optionally after a successful clone if the agent doesn't need to derive
the same key again immediately.

---

## Required reading

1. This brief.
2. `team/villager/dev/dev__ROLE.md` and
   `team/villager/appsec/appsec__ROLE.md`.
3. `team/villager/appsec/v0.10.30/F03__pbkdf2-lru-residency.md`.
4. `sgit_ai/crypto/Vault__Crypto.py` lines 26–32 and surrounding.
5. `team/villager/appsec/v0.10.30/M00__mutation-test-matrix.md` row M5
   — the cache-disable mutation test (currently undetected).

---

## Scope

**In scope:**
- Add a method on `Vault__Crypto` (a Type_Safe class — keep the cache
  module-level OR move it inside the class, your choice; document
  rationale). The method clears the LRU cache.
- Wire calls from:
  - `Vault__Sync.rekey_wipe` (right after the wipe finishes).
  - `Vault__Sync.delete_on_remote` (right before/after the deletion).
  - `Vault__Sync.probe_token` (after the probe returns; probe should not
    leave any key material in process state).
  - Optionally any "session end" hook the CLI exposes.
- Tests:
  - **Functional**: `clear_kdf_cache()` empties the cache; subsequent
    PBKDF2 derivations work correctly.
  - **Cache-bound**: `_pbkdf2_cached.cache_info().currsize` is 0 after
    clear.
  - **Mutation closer**: the M5 test from the mutation matrix —
    `test_pbkdf2_cache_size_bounded` checking `cache_info().currsize`
    against the expected upper bound.

**Out of scope:**
- Replacing PBKDF2 with a different KDF.
- Changing iteration count.
- Memory zeroing of derived key bytes (different problem; Python doesn't
  give you reliable byte-level wiping anyway — note as residual risk).
- Multi-tenant agent host abstraction (escalated to Architect per AppSec
  F03 — separate brief if/when it becomes priority).

**Hard rules:**
- No behaviour change to the KDF itself.
- No new dependency.
- Tests under Phase B parallel CI shape.

---

## Acceptance criteria

- [ ] `clear_kdf_cache()` method (or equivalent) exists.
- [ ] Wired into rekey, delete-on-remote, probe paths.
- [ ] Tests added: at least 3 (functional clear + cache_info bound +
      M5 closer).
- [ ] Mutation matrix M5 row updates from "U (correctness OK)" to
      "D" — the new test catches the `maxsize=0` mutation.
- [ ] Suite ≥ 2,105 passing, coverage ≥ 86%.
- [ ] No new mocks.
- [ ] Closeout entry in hardening log.

---

## Deliverables

1. Source change (helper + wiring).
2. Test file additions.
3. Hardening log entry.
4. Update note inside `team/villager/appsec/v0.10.30/M00__mutation-test-matrix.md`
   marking M5 as resolved (you may edit that file in place — small
   update, not a redesign).

Commit message:
```
fix(security): clear_kdf_cache for PBKDF2 LRU residency

Closes AppSec finding F03. The module-level lru_cache on
_pbkdf2_cached retained passphrases in agent contexts beyond their
useful life. New Vault__Crypto.clear_kdf_cache() is wired into
rekey, delete-on-remote, and probe — natural cache-eviction
boundaries for the agent surface added this sprint.

Closes mutation gap M5 (cache_info().currsize bound test).

https://claude.ai/code/session_<id>
```

---

## When done

Return a ≤ 200-word summary:
1. Helper signature + module location.
2. Wiring sites.
3. Test count + the mutation matrix update.
4. Coverage delta.
5. Anything that surfaced about long-running agent contexts that
   warrants the Architect brief on multi-tenant scope (escalate, don't
   try to fix).
