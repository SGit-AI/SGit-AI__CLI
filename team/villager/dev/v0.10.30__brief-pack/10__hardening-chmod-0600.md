# Brief 10 — Hardening: chmod 0600 on `.sg_vault/local/` files

**Owner role:** **Villager Dev** (`team/villager/dev/dev__ROLE.md`)
**Status:** Ready to execute. Deferred queue is unblocked (brief 06 PASS).
**Prerequisites:** None within the deferred queue. Phase B test infra
must be in place (it is).
**Estimated effort:** ~1–2 hours
**Touches:** `sgit_ai/sync/Vault__Sync.py`, `sgit_ai/cli/CLI__Token_Store.py`,
possibly `sgit_ai/secrets/` callers; new tests under `tests/unit/`.

---

## Why this brief exists

AppSec finding F02 / F07 / F11 (severity MEDIUM aggregated): files in
`.sg_vault/local/` that hold key material are written with the default
umask (typically `0644`). On a multi-user host, any local user can read
the read_key, vault_key, and stored tokens — equivalent to credential
theft.

Concrete code references from AppSec:
- `sgit_ai/sync/Vault__Sync.py:1551` and `:1655` (clone_mode.json)
- `sgit_ai/cli/CLI__Token_Store.py:42-43` (token store)
- `sgit_ai/secrets/` callers writing `vault_key`

This is a small, well-scoped hardening change. It does NOT change
behaviour for legitimate users (umask 0600 only restricts other users on
the same host).

---

## Required reading

1. This brief.
2. `team/villager/dev/dev__ROLE.md`.
3. `team/villager/appsec/v0.10.30/F02__rekey-key-material.md`,
   `F07__clone-mode-plaintext-keys.md`, `F11__token-handling.md`.
4. `CLAUDE.md` — Type_Safe rules, no-mocks rule.

---

## Scope

**In scope:**
- Add a single helper that performs `os.chmod(path, 0o600)` after writing
  any file under `.sg_vault/local/`. Place the helper where existing
  callers will pick it up — likely a small method on `Vault__Sync` or a
  new tiny class `Vault__Local_File_Writer` (Architect's choice; pick the
  one that minimizes call-site churn).
- Apply the helper at every `.sg_vault/local/*` write site identified by
  AppSec. Audit grep first to make sure no site is missed:
  ```
  grep -rn '\.sg_vault/local' sgit_ai/
  grep -rn 'open(.*"w"' sgit_ai/sync/Vault__Sync.py | head
  ```
- Add tests under `tests/unit/sync/` (or a new module) that:
  - After a clone, assert `os.stat(path).st_mode & 0o777 == 0o600` for
    each `.sg_vault/local/*` file.
  - Run on a temp directory; do not touch real `~/.sg_vault`.

**Out of scope:**
- The `vault_key` printed-on-stdout (intentional UX per Dinis).
- Token masking in logs (separate concern; AppSec accepted-risk).
- Windows ACL handling — Linux/macOS only for this brief; flag Windows
  as a follow-up if you encounter platform branches.

**Hard rules:**
- Type_Safe class for the helper if you create a new class. Use
  `Safe_Str__File_Path` (already exists) for path arguments.
- No mocks. Tests use real temp dirs.
- Do not alter the contents of any file — only its mode.
- Tests must pass under the existing `pytest tests/unit/` invocation
  (Phase B parallel CI shape).

---

## Acceptance criteria

- [ ] Every `.sg_vault/local/*` file write goes through the chmod helper.
- [ ] Audit-grep `grep -rn '\.sg_vault/local' sgit_ai/` shows no
      direct write that bypasses the helper.
- [ ] New tests under `tests/unit/sync/test_Vault__Sync__File_Modes.py`
      (or similar) — at least 5 assertions covering clone_mode.json,
      vault_key, simple-token clone files, post-rekey files, post-probe
      files (where probe writes nothing — assert that too).
- [ ] Suite still passes 2,105+ tests; coverage ≥ 86%.
- [ ] No mock / patch / monkeypatch added.
- [ ] Behaviour preserved for legitimate users (clone, push, rekey,
      probe, write, delete-on-remote workflows still pass).
- [ ] Each commit is a discrete logical change; pushable independently.

---

## Deliverables

1. Helper class or method (in source).
2. Refactored call sites.
3. New test file(s) under `tests/unit/`.
4. Closeout note appended to `team/villager/dev/v0.10.30/`
   (e.g., `team/villager/dev/v0.10.30__hardening-log.md`) — append-only,
   one short paragraph per hardening brief.

Commit message template:
```
fix(security): chmod 0600 on .sg_vault/local/ files

Closes AppSec finding F02/F07/F11. Files holding key material
(read_key, vault_key, tokens) were written with default umask
(0644), allowing any local user on a multi-user host to read them.
A single helper now applies 0600 after every write under
.sg_vault/local/.

No behaviour change for legitimate users. New tests assert mode bits
for clone_mode.json, vault_key, simple-token clones, and post-rekey
state.

https://claude.ai/code/session_<id>
```

---

## When done

Return a ≤ 200-word summary stating:
1. Helper location (file:line).
2. Call sites refactored (file:line list).
3. Test file added + assertion count.
4. Coverage delta if any (likely flat, fine).
5. Anything not protected by chmod that should be (escalate).
