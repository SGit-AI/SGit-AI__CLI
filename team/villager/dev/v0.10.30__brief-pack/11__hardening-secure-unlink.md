# Brief 11 — Hardening: secure-unlink helper for rekey wipe

**Owner role:** **Villager Dev**
**Status:** Ready to execute. Recommended after brief 10 lands (shares
the local-file helper module, but can run in parallel if owner is
careful).
**Prerequisites:** None hard. Brief 10 soft-recommended for code locality.
**Estimated effort:** ~1–2 hours
**Touches:** `sgit_ai/sync/Vault__Sync.py` (rekey wipe path), possibly a
new helper module, tests under `tests/unit/sync/`.

---

## Why this brief exists

AppSec finding F02 (severity MEDIUM): `rekey_wipe` in `Vault__Sync.py`
removes old vault state with `shutil.rmtree`, but the file blocks are
left intact on disk for an attacker with raw-device or undelete access.
For a key-rotation workflow, this is a real residual risk: the old
ciphertext + old read_key may both still be recoverable from the device.

The fix is a `_secure_unlink(path)` helper that overwrites a file with
zeros (or random bytes) before `os.unlink`-ing it, then applies it in
`rekey_wipe` and any other "wiping key material" path.

---

## Required reading

1. This brief.
2. `team/villager/dev/dev__ROLE.md`.
3. `team/villager/appsec/v0.10.30/F02__rekey-key-material.md` — the
   finding.
4. `sgit_ai/sync/Vault__Sync.py` `rekey_wipe` method (~line 1770 per the
   AppSec mutation matrix). Read the surrounding rekey flow to
   understand abort windows.
5. `team/humans/dinis_cruz/claude-code-web/05/01/v0.10.30/05__probe-delete-rekey-vault-lifecycle.md`
   — the rekey design context.

---

## Scope

**In scope:**
- Add `_secure_unlink(path: Safe_Str__File_Path) -> None` (or method on
  the helper class from brief 10 if it exists). Behaviour:
  1. Open file for write.
  2. Determine length.
  3. Overwrite with zero bytes (or `os.urandom` if you prefer; document
     the choice).
  4. `fsync` to flush to disk.
  5. `os.unlink`.
- Apply in `rekey_wipe` and any other path that removes a file holding
  key material under `.sg_vault/local/`.
- Tests asserting that after `_secure_unlink`, the file is gone AND
  recovery from the same path returns no plaintext.

**Out of scope:**
- Filesystem-specific guarantees beyond best-effort overwrite. Modern
  SSDs with TRIM may reallocate blocks; document this as residual risk
  in the AppSec finding doc but do not attempt to defeat it (impossible
  from userspace).
- Memory wiping (a different concern; brief 12 handles cache eviction).
- Windows-specific behaviour.

**Hard rules:**
- Use Type_Safe parameter types.
- No mocks; real temp files in tests.
- Behaviour preservation: rekey workflow must still produce identical
  end-state (new ciphertext + new key on disk).
- Tests must pass under Phase B parallel CI shape.

---

## Acceptance criteria

- [ ] Helper exists and is reachable from `Vault__Sync.rekey_wipe`.
- [ ] `rekey_wipe` calls `_secure_unlink` for every file removed
      (audit-grep `os.unlink\|rmtree` in the rekey path).
- [ ] If a directory must be removed, files inside are
      `_secure_unlink`-ed first, then the directory is `rmdir`-ed.
- [ ] At least 3 tests:
  1. After rekey, the old vault_key file is gone AND the underlying
     bytes are not recoverable via direct disk read of the same path.
  2. Mid-rekey abort still leaves a deterministic state — either old
     fully present, or new fully present, no half-written keys.
  3. Empty / small / multi-MB file all wipe correctly.
- [ ] Suite still 2,105+ passing, coverage ≥ 86%.
- [ ] No new mocks.
- [ ] Closeout entry added to the hardening log.

---

## Deliverables

1. Helper (source).
2. `rekey_wipe` refactored to use it.
3. Test file (e.g., `tests/unit/sync/test_Vault__Sync__Secure_Unlink.py`).
4. Closeout entry in the hardening log.

Commit message:
```
fix(security): secure-unlink for rekey wipe

Closes AppSec finding F02. Old vault key + ciphertext were left
recoverable on disk after rekey_wipe (only inode-level removal).
A new _secure_unlink helper overwrites file contents before unlinking
and is applied in the rekey wipe path.

Tests cover empty, small, multi-MB cases plus a mid-rekey abort
deterministic-state assertion.

https://claude.ai/code/session_<id>
```

---

## When done

Return a ≤ 200-word summary:
1. Helper location.
2. Number of call sites refactored.
3. Test count + the disk-read assertion approach (just unlink-and-stat?
   open the underlying device? a test fixture that mounts a tmpfs and
   reads back the same path?).
4. Any abort-window finding (mid-rekey state machine) that surfaces
   during the work — escalate to Architect if the rekey state machine
   needs redesign.
5. Coverage delta.
