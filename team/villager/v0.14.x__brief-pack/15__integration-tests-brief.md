# Brief 15 — Move bug fixes + integration test discipline (urgent)

**Date:** 2026-05-07
**Audience:** SGit Dev Agent
**Scheduling:** **URGENT — lands before any further v0.14.x work.** Estimated effort: ~1 day.
**Author:** Villager orchestrator (Opus)

---

## 1. Why this exists

In the last 48 hours, three real bugs in `sgit vault move` shipped past 102 unit/QA tests:

1. **`Vault__API()` constructed with no `base_url`** → every HTTP call crashed with `unknown url type: None/api/...`. Caught by Dinis on first live use. Already fixed in `a2466dc`.
2. **Backup zip filename starts with `__`** because `old_vault_id` was empty. Silent. Backup went to `__2026-05-07T17-46-21Z__pre-move.zip` instead of `<vault-id>__...zip`. **Not yet fixed.**
3. **Move shipped an incomplete vault to the server** — local clone was missing one object, the move silently propagated the gap, the new vault on the server was unclonable. **Data-integrity issue. Not yet fixed.**

All three slipped past 102 tests because every move test in `tests/unit/core/actions/move/` and `tests/qa/sync/test_Vault__Move__Multi_Round.py` uses `Vault__API__In_Memory` — a Python dict fake. The fake accepts any `base_url`, validates nothing, has no concept of upload failure. **The first time `Vault__Sync__Move` ever talks to a real server is when a user runs `sgit vault move`.**

This brief fixes the two outstanding move bugs AND establishes the integration-test discipline that will prevent the next round of "found in production by Dinis" bugs.

---

## 2. The three move bugs to fix immediately

### 2a. 🔴 Move silently ships an incomplete vault when local objects are missing

**Symptom:** after a successful-looking `sgit vault move`, cloning the new vault fails with `missing file: obj-cas-imm-296a51ae41bf` because the new server vault doesn't have that object.

**Root cause:** `Step__Move__Validate_Local` (`sgit_ai/workflow/move/steps/Step__Move__Validate_Local.py`) only counts objects in `bare/data/` (line 58–61). It does NOT walk the commit graph to verify every reachable object is locally present. Brief 02 §5c step 1 explicitly required:

> walk the head tree and verify integrity (decrypt every object reachable from HEAD using current key — fails fast if local clone is already corrupt)

Currently not implemented. If the local clone is missing any historical object, `Build_Temp_Vault._reencrypt_objects` only re-encrypts what's locally present (`os.listdir(data_dir)`), and the new vault is silently incomplete.

**Required fix in `Step__Move__Validate_Local.execute`:**

```python
# After existing checks, BEFORE returning state:
from sgit_ai.storage.Vault__Commit            import Vault__Commit
from sgit_ai.storage.Vault__Object_Store      import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager       import Vault__Ref_Manager
from sgit_ai.storage.Vault__Branch_Manager    import Vault__Branch_Manager
from sgit_ai.crypto.PKI__Crypto               import PKI__Crypto

# Walk every active named branch's full commit graph
crypto      = Vault__Crypto()
obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=crypto)
ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
vc          = Vault__Commit(crypto=crypto, pki=PKI__Crypto(),
                            object_store=obj_store, ref_manager=ref_manager)

# Resolve read_key from local vault_key
keys     = crypto.derive_keys_from_vault_key(vault_key_str)
read_key = keys['read_key_bytes']

missing = []
visited_commits = set()
visited_trees   = set()
visited_blobs   = set()

# For each branch HEAD: BFS commit chain → tree → blobs
for head_commit_id in self._all_branch_heads(...):
    queue = [head_commit_id]
    while queue:
        cid = queue.pop()
        if cid in visited_commits:
            continue
        visited_commits.add(cid)
        if not obj_store.exists(cid):
            missing.append(cid)
            continue
        commit = vc.load_commit(cid, read_key)
        # Walk tree
        if commit.tree_id and str(commit.tree_id) not in visited_trees:
            self._walk_tree(str(commit.tree_id), vc, obj_store, read_key,
                           visited_trees, visited_blobs, missing)
        # Walk parents
        for parent_id in (commit.parents or []):
            queue.append(str(parent_id))

if missing:
    examples = ', '.join(missing[:3])
    raise RuntimeError(
        f'Local vault is missing {len(missing)} object(s) referenced by the '
        f'commit graph (e.g. {examples}). The move would ship an incomplete '
        f'vault to the server. Run `sgit pull` or `sgit fetch` first to '
        f'complete the local clone before retrying vault move.'
    )
```

Helper `_walk_tree` walks the tree's children, marking sub-trees and blobs as visited or missing.

**This single fix would have prevented today's data-integrity bug.**

### 2b. 🟡 Backup zip filename starts with `__` (empty `old_vault_id`)

**Symptom:** `/vault/.sg_vault_new/backups/__2026-05-07T17-46-21Z__pre-move.zip` — the leading `__` indicates the `vault_id` segment was empty.

**Root cause:** `Step__Move__Validate_Local` (line 38–56) tries to resolve `vault_id` from `local/config.json` first, then derives from the vault_key as a fallback. If config.json doesn't have the field AND the derive-from-key fallback fails silently (line 55: `except Exception: pass`), `vault_id` stays `''`. The empty string flows through to the backup filename construction.

**Required fix:** add a hard guard immediately after the resolution attempts:

```python
# (existing resolution code lines 38-56)

if not vault_id:
    raise RuntimeError(
        'Could not determine old vault_id from local config or vault key. '
        'The move would produce an ambiguously-named backup and orphan state. '
        'Aborting before any destructive change.'
    )
```

Also: replace the silent `except Exception: pass` on line 55 with at least a stderr warning so the failure isn't invisible:

```python
try:
    vault_id = Vault__Crypto().derive_keys_from_vault_key(vault_key_str)['vault_id']
except Exception as e:
    print(f'warning: could not derive vault_id from vault_key: {e}', file=sys.stderr)
```

### 2c. 🟡 New vault key not displayed in success output

**Symptom:** after `sgit vault move`, the user has to `cat .sg_vault/local/vault_key` to find the new key. This is bad UX for a credential the user typically wants to copy somewhere safe.

**Required fix in `cmd_vault_move`** (`sgit_ai/cli/CLI__Vault.py`, near the success-message block):

```python
print()
print('Move complete. New vault is live at:')
print(f'  Vault-id:    {result.get("new_vault_id", "?")}')
print(f'  Vault-key:   {new_vault_key}')                         # ← NEW
print(f'  API:         {result.get("target_api", "?")}')
print()
print('  ⚠ Save the new vault-key somewhere safe — the old key is now invalid.')
print()
if result.get('backup_zip_path'):
    # Use the POST-rename path (.sg_vault/backups/), not the .sg_vault_new/ path
    final_path = result['backup_zip_path'].replace('.sg_vault_new/', '.sg_vault/')
    print(f'  Old vault backed up to: {final_path}')
```

The backup-path replacement above is a workaround; better is to have `Step__Move__Delete_Source` (the step that does the rename) update the path in the returned state to reflect the post-rename location.

---

## 3. Mandatory new integration tests

Three new test files in `tests/integration/`. All use the REAL `Vault__API` (not `Vault__API__In_Memory`) via the existing `vault_api` / `crypto` / `temp_dir` fixtures from `conftest.py`.

### 3a. `tests/integration/test_Vault__Sync__Move__Integration.py`

```
test_move_in_place_rotation_then_clone_succeeds
  - sgit init <key>; commit "first"; commit "second"; push
  - sgit vault move (auto-generated new key)
  - From a fresh dir: sgit clone <new-key>
  - Assert: clone walks all commits without missing-object errors,
    working copy matches expected files end-to-end.

test_move_validates_full_commit_graph_before_proceeding
  - Setup vault with 5 commits
  - Manually delete one historical object from .sg_vault/bare/data/
  - Run sgit vault move
  - Assert: aborts with the "missing N objects" message (regression
    test for §2a fix); no .sg_vault_new/ created; no server state changed.

test_move_then_old_vault_id_is_tombstoned
  - Move; attempt to push to OLD vault_id directly
  - Assert: HTTP 403 with the friendly "permanently moved/deleted" message,
    not the raw "write key mismatch".

test_move_with_dirty_local_clone_fails_validation_clearly
  - Setup vault, write a file, DON'T commit
  - Run sgit vault move
  - Assert: aborts with "uncommitted changes" message; no state change.
```

### 3b. `tests/integration/test_Vault__Backup__Integration.py`

```
test_backup_round_trip_against_real_server
  - sgit init; commit; push to real server
  - sgit vault backup
  - Assert: zip exists with correct filename pattern (vault_id__ts__label.zip)
  - Assert: sha256 sidecar matches; manifest.json parses through schema.

test_backup_filename_includes_real_vault_id
  - Specifically asserts the vault_id segment of the filename is non-empty
  - Regression test for §2b.
```

### 3c. `tests/integration/test_Vault__Restore__Integration.py`

```
test_restore_bare_mode_against_real_server
  - Setup, push, backup, restore --mode bare to a fresh dir
  - Assert: restored .sg_vault/ structure matches; vault_id non-empty
    (regression for the c925321 fix); sgit history log shows same commits.

test_restore_expanded_mode_with_key_against_real_server
  - Same setup, restore --mode expanded
  - Assert: working copy extracted; file contents match originals.
```

### 3d. `tests/integration/test_Vault__Sync__Move__Backup_Roundtrip.py`

```
test_move_backup_can_be_restored_under_old_key
  - Setup vault on real server
  - sgit vault move (creates backup zip during step 7)
  - Restore the backup zip into a fresh dir under the OLD vault key
  - Assert: restored vault is byte-identical to pre-move state.
```

This proves the brief 02 §4d "backup is the safety net" promise actually holds end-to-end — exactly the recovery path Dinis is using right now.

---

## 4. The standard going forward

**From this brief onward: every action class in `sgit_ai/core/actions/<area>/` that performs network I/O must have at least one integration test in `tests/integration/test_<Area>__Integration.py`.**

The integration test must:
1. Use the REAL `Vault__API` against the real local server fixture (not `Vault__API__In_Memory`).
2. Exercise at least one happy-path round trip end-to-end.
3. Assert real HTTP response shapes, not just in-memory dict equality.
4. Run as part of the `tests/integration/` suite (Python 3.12 venv per `CLAUDE.md`).

**Existing gaps to fill incrementally** (not in this brief — flag for follow-up):

| Action | Has integration test? |
|---|---|
| `clone` (full) | Partial — covered indirectly by `test_Vault__Local_Server.py` |
| `clone-branch` | ❌ |
| `clone-headless` | ❌ |
| `clone-range` | ❌ |
| `clone-readonly` | ❌ |
| `pull` | ❌ |
| `fetch` | ❌ |
| `vault delete-on-remote` | ❌ |
| `migrate` | ❌ |
| `share send` / `share publish` | Partial via `test_API__Transfer__Local_Server.py` |
| **`vault move`** | ❌ (this brief fixes) |
| **`vault backup`** | ❌ (this brief fixes) |
| **`vault restore`** | ❌ (this brief fixes) |

A separate follow-up brief should fill the remaining ❌ entries one at a time.

### 4a. CI requirement going forward

Add to the executor/reviewer checklist:
- **Any new action class touching the API requires an integration test.** PR / commit reviewer rejects work without one.
- **Any bug fix in a network-touching action requires a regression test in the integration tier.** Today's three bugs would each have a one-line integration test that would have caught them.

Confirm `tests/integration/` runs in CI on every PR. If not currently running automatically (the Python 3.12 venv setup may have been local-only): add a CI workflow step that sets up Python 3.12, installs `sgraph-ai-app-send`, and runs `pytest tests/integration/ -v`.

---

## 5. Order of work

1. **Fix §2a** — `Step__Move__Validate_Local` walks the full commit graph. This is the data-integrity fix; do it first.
2. **Fix §2b** — guard against empty `old_vault_id`; add stderr warning on derive failure.
3. **Fix §2c** — display new vault-key + correct backup path in success output.
4. **Land `test_Vault__Sync__Move__Integration.py`** with all 4 tests. Confirm `test_move_validates_full_commit_graph_before_proceeding` fails against pre-§2a code, passes after.
5. **Land `test_Vault__Backup__Integration.py`** (2 tests).
6. **Land `test_Vault__Restore__Integration.py`** (2 tests).
7. **Land `test_Vault__Sync__Move__Backup_Roundtrip.py`** (1 test).
8. **Run full unit + integration suites green.**
9. **Reviewer fix pass.**

---

## 6. Out of scope

- **Filling integration tests for clone-branch, clone-headless, clone-range, clone-readonly, pull, fetch, migrate, delete-on-remote, share publish** — flagged in §4 but defer to a separate follow-up brief. Each is small (~30 min); together they're ~½ day.
- **Changing the existing in-memory tests** — keep them. They're fast and useful for invariant testing. Just no longer sufficient on their own.
- **Browser / web-client integration** — out of scope; vault-web team's concern.
- **Brief 12** — this brief absorbs the move-related items from brief 12 §1 (silent re-encryption fallbacks remain in brief 12; the pre-flight validation moves here). Brief 12's other items (store_at refactor, cleanup state edge case) stay in brief 12.

---

## 7. Verification checklist

When done:

- All ~9 new integration tests pass against the real local server.
- `Step__Move__Validate_Local` walks the full reachable commit graph and aborts cleanly when any object is missing.
- The "missing object" failure mode produces an actionable error pointing at `sgit pull` / `sgit fetch`.
- Backup zip filenames always include a non-empty `vault_id` segment.
- `cmd_vault_move` success output displays the new vault-key prominently.
- The full disaster-recovery cycle (move → backup → restore-from-backup → verify) round-trips correctly.
- All 3,442+ existing unit tests still pass.
- `tests/integration/` runs in CI on every PR going forward.

---

## 8. The standard, restated for emphasis

**No network-touching action class ships without an integration test against the real server.**

Today's lesson: 102 tests in two tiers, all using a Python dict fake, missed three bugs that a single integration test would have caught. The cost of an integration test per action is ~30 minutes. The cost of shipping a data-integrity bug to a user is the user's trust. Going forward, executor + reviewer treat this as table stakes, not a nice-to-have.


**From this brief onward: every action class in `sgit_ai/core/actions/<area>/` that performs network I/O must have at least one integration test in `tests/integration/test_<Area>__Integration.py`.**

The integration test must:
1. Use the REAL `Vault__API` against the real local server fixture (not `Vault__API__In_Memory`).
2. Exercise at least one happy-path round trip end-to-end.
3. Assert a real HTTP response shape, not just an in-memory dict equality.
4. Run as part of the `tests/integration/` suite (Python 3.12 venv per `CLAUDE.md`).

**Existing gaps to fill incrementally** (not in this brief — flag for follow-up):

| Action | Has integration test? |
|---|---|
| `clone` (full) | Partial — covered indirectly by `test_Vault__Local_Server.py` |
| `clone-branch` | ❌ |
| `clone-headless` | ❌ |
| `clone-range` | ❌ |
| `clone-readonly` | ❌ |
| `pull` | ❌ |
| `fetch` | ❌ |
| `vault delete-on-remote` | ❌ |
| `migrate` | ❌ |
| `share send` / `share publish` | Partial via `test_API__Transfer__Local_Server.py` |
| **`vault move`** | ❌ (this brief fixes) |
| **`vault backup`** | ❌ (this brief fixes) |
| **`vault restore`** | ❌ (this brief fixes) |

A separate follow-up should fill the remaining ❌ entries one at a time. Don't bundle into this brief — keep it focused on the immediate disaster-prevention work.

### 4a. CI requirement going forward

Add to the executor/reviewer checklist:
- **Any new action class touching the API requires an integration test.** PR / commit reviewer rejects work without one.
- **Any bug fix in a network-touching action requires a regression test in the integration tier**, not just unit. Today's three bugs would each have a one-line integration test that would have caught them.

---

## 5. Implementation outline

### 5a. Reuse the existing fixture pattern

`tests/integration/conftest.py` already provides `vault_api`, `crypto`, `temp_dir` fixtures. The new test files use the same pattern. No new infrastructure needed.

### 5b. The skeleton for each new test file

```python
import os, pytest

# Real Vault__API instance (NOT in-memory) is provided by conftest.py
# via the `vault_api` fixture, backed by a sgraph-ai-app-send local server.

class Test__Vault_Sync_Move__Integration:

    def test_move_in_place_rotation_then_clone_succeeds(self, vault_api, crypto, temp_dir):
        sync = Vault__Sync(crypto=crypto, api=vault_api)

        # Setup: real init + commit + push
        vault_dir = os.path.join(temp_dir, 'src')
        result    = sync.init(vault_dir)
        ...

        # Action: real move
        mover = Vault__Sync__Move(crypto=crypto, api=vault_api)
        new_state = mover.move(vault_dir, reason='integration test')

        # Verify: real clone with the new key from a fresh dir
        new_key = open(os.path.join(vault_dir, '.sg_vault', 'local', 'vault_key')).read().strip()
        clone_dir = os.path.join(temp_dir, 'cloned')
        sync.clone(new_key, clone_dir)

        # Assert end-to-end correctness
        assert os.path.isfile(os.path.join(clone_dir, '.sg_vault', 'local', 'vault_key'))
        assert sync.history_log(clone_dir)['commits']  # full history walks
```

### 5c. Test count and effort

- `test_Vault__Sync__Move__Integration.py` — 4 tests (~1.5 hours)
- `test_Vault__Backup__Integration.py` — 2 tests (~45 min)
- `test_Vault__Restore__Integration.py` — 2 tests (~45 min)
- `test_Vault__Sync__Move__Backup_Roundtrip.py` — 1 test (~30 min)
- Brief 12 updates (validate-local graph walk + cmd_vault_move output + non-empty vault_id check) — ~3 hours
- Reviewer fix pass — ~30 min

**Total: ~7 hours.** Plus running the integration suite (which adds ~1-2 minutes to the test run).

### 5d. CI integration

Confirm the integration suite runs in CI on every PR. If not currently running (the Python 3.12 venv setup may have been local-only): add a CI workflow step that:
- Sets up Python 3.12.
- Installs `sgraph-ai-app-send`.
- Runs `pytest tests/integration/`.

If this is already in CI: no change needed, just confirm the new tests get picked up.

---

## 6. Order of work

1. **Update brief 12** with the three new requirements (3a, 3b, 3c) — already-pending brief, just expand its scope.
2. **Land the validate-full-graph change in `Step__Move__Validate_Local`** — this is the single most important code change. Add the failing-fast unit test alongside.
3. **Land the move integration test file** with all 4 tests. Confirm at least one (the validate-graph regression test) fails against the current code, passes after the fix.
4. **Land the backup + restore integration tests.**
5. **Land the move/backup roundtrip test.**
6. **Update `cmd_vault_move`** to display the new vault key + correct backup path.
7. **Run the full suite + integration suite — confirm everything green.**
8. **Reviewer fix pass.**

---

## 7. Out of scope

- **Filling integration tests for clone-branch, clone-headless, clone-range, clone-readonly, pull, fetch, migrate, delete-on-remote, share publish** — flagged in §4 but defer to a separate brief. Each is small (~30 min); together they're ~½ day. Worth doing but not URGENT in the way the move-related coverage is.
- **Changing the existing in-memory tests** — keep them. They're fast and useful for invariant testing. They're just not sufficient on their own.
- **Browser / web-client integration** — out of scope; that's a vault-web team concern.

---

## 8. Verification checklist

When done:

- All ~9 new integration tests pass against the real local server.
- `Step__Move__Validate_Local` walks the full reachable commit graph and aborts if any object is missing.
- The "missing object" failure mode produces a clear actionable error pointing at `sgit pull` / `sgit fetch`.
- `cmd_vault_move` success output shows the new vault-key prominently.
- Backup zip filename always includes a non-empty vault_id segment.
- A simulated "missing object in local" scenario in the new integration test reproduces the bug Dinis hit today, and the fix makes it pass.
- All 3,442+ existing unit tests still pass.
- The integration suite runs in CI on every PR going forward.

---

## 9. The standard, restated for emphasis

**No network-touching action class ships without an integration test against the real server.**

This is the lesson from today: 102 tests in two tiers, all using a Python dict fake, missed three bugs that a single integration test would have caught. The cost of an integration test per action is ~30 minutes. The cost of shipping a data-integrity bug to a user is the user's trust. Going forward, the executor + reviewer treat this as table stakes, not a nice-to-have.
