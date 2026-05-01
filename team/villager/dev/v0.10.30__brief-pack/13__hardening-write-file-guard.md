# Brief 13 — Hardening: write_file read-only guard

**Owner role:** **Villager Dev**
**Status:** Ready to execute.
**Prerequisites:** None.
**Estimated effort:** ~1 hour
**Touches:** `sgit_ai/sync/Vault__Sync.py` (`write_file` method), tests
under `tests/unit/sync/`.

---

## Why this brief exists

AppSec finding F08 + Dev finding 8.6 + Architect finding 02: the
`write_file` method on `Vault__Sync` does not check that the vault is
writable before attempting to write. If `clone_mode.json` is missing or
malformed, `load_clone_mode` returns `{'mode': 'full'}` and a read-only
clone silently becomes read-write. AppSec mutation M7 also showed that
`write_file` would silently skip encryption if `crypto.encrypt` were
replaced by identity — partly because there is no defensive check at
the top of the method.

A defensive guard at the top of `write_file` closes both gaps:

```python
def write_file(self, ...):
    c = self.config()  # or however the current vault config is fetched
    if not c.write_key:
        raise Vault__Read_Only_Error(...)
    if not c.read_key:
        raise Vault__Missing_Key_Error(...)
    # existing body
```

The exact exception class names are your choice; use Type_Safe Safe_Str
fields where appropriate.

---

## Required reading

1. This brief.
2. `team/villager/appsec/v0.10.30/F08__surgical-write-path.md`.
3. `team/villager/dev/v0.10.30/08__error-handling-consistency.md` finding 8.6.
4. `team/villager/architect/v0.10.30/02__new-commands-cli-boundary.md`.
5. `sgit_ai/sync/Vault__Sync.py` — `write_file` method (~line 282 per
   AppSec mutation matrix). Read the `load_clone_mode` failure path too.

---

## Scope

**In scope:**
- Add a defensive guard at the top of `write_file` checking `write_key`
  is present and non-empty.
- Make `load_clone_mode`'s "fail-open" behaviour (return `{'mode':
  'full'}` on missing/malformed file) explicit: either fail-closed
  (raise) OR keep fail-open but document the choice and assert that the
  guard catches it. Pick fail-closed if it's safe; document the choice.
- Tests:
  - Read-only clone + `write_file` raises the new error.
  - Corrupt `clone_mode.json` + `write_file` raises (does not silently
    succeed).
  - Full-mode write_file still works.
- Update mutation matrix M7: this brief alone does NOT close M7
  (encryption-skip mutation), but the guard DOES close the related
  `clone_mode.json`-corruption mutation. Document the partial closure.

**Out of scope:**
- Closing M7 itself — that's brief 20 (crypto-determinism / encryption
  integrity tests) which adds the `bare/data/{blob_id}` ciphertext
  assertion.
- Schema for `clone_mode.json` — that's brief 16. (This brief assumes
  current dict shape; brief 16 will replace it.)

**Hard rules:**
- Type_Safe exception classes if you create them.
- No mocks; real read-only clones in tests.
- Tests under Phase B parallel CI shape.

---

## Acceptance criteria

- [ ] `write_file` raises a typed error before any write when the vault
      is not writable.
- [ ] `load_clone_mode` failure mode is explicit (fail-closed preferred,
      fail-open documented if kept).
- [ ] At least 4 tests covering the guard.
- [ ] Suite ≥ 2,105 passing, coverage ≥ 86%.
- [ ] No new mocks.
- [ ] Closeout entry in hardening log.
- [ ] Mutation matrix updated noting the partial closure.

---

## Deliverables

1. Source change to `write_file`.
2. New error class(es) in `sgit_ai/sync/` (or wherever vault errors live).
3. Test additions.
4. Hardening log entry.

Commit message:
```
fix(security): defensive read-only guard on write_file

Closes AppSec F08 / Dev 8.6 / Architect finding 02. write_file did
not check write_key was present before writing. A corrupt or missing
clone_mode.json silently demoted a read-only clone to read-write.
A guard at the top of write_file now raises Vault__Read_Only_Error
before any write attempt.

Tests cover read-only clone, corrupt clone_mode.json, and full-mode
happy path.

https://claude.ai/code/session_<id>
```

---

## When done

Return a ≤ 150-word summary:
1. Guard location.
2. Exception class name.
3. fail-open vs fail-closed decision for `load_clone_mode`.
4. Test count.
5. Mutation matrix partial-closure note.
