# Brief — `sgit vault move` (key rotation + server move with stable object IDs)

**Date:** 2026-05-06
**Audience:** Sonnet executor + Sonnet reviewer (two-session pattern)
**Prerequisite:** ships after the `--token`/`--as` rename brief (`00g`)
**Scheduling:** Before the visualisation track. Estimated effort: ~1–1.5 days.
**Author:** Villager orchestrator (Opus)

---

## 1. Why this exists

Two sgit features that don't exist today, both of which we need:

1. **Vault-key rotation** — when a vault key leaks (or when key hygiene says it should rotate), the user needs to swap encryption keys without losing commit history. Current `sgit rekey` works but loses all history; not acceptable for vaults with meaningful audit trails.
2. **Vault server move** — moving a vault to a different SG/Send instance (e.g. from `dev.send.sgraph.ai` to a self-hosted instance) without rebuilding the history.

Both share the same machinery and a single command can serve both. The design preserves object IDs through rotation, keeping all internal references and external citations stable.

---

## 2. The core insight: stable object IDs across rotation

Sgit object IDs today are `obj-cas-imm-{hash(ciphertext)}` — content-addressed on the encrypted bytes. The naive rotation is "re-encrypt under new key, every ID changes, rewrite all refs." We do something cleaner:

**Re-encrypt the contents in place; keep the old object IDs as filenames; break the `id == hash(ciphertext)` invariant deliberately.**

What that means concretely:

- File `obj-cas-imm-abc123` → contents change from `E(old_key, plaintext)` to `E(new_key, plaintext)`. The filename stays `abc123`.
- All cross-references (tree → blob, commit → tree, commit → parent commit) are by ID and remain valid because IDs didn't move.
- Readers using the new key call `obj_store.load('abc123')`, decrypt with `new_key`, get the original plaintext. Works.
- Readers using the old key call `obj_store.load('abc123')`, attempt decrypt with `old_key`, fail at GCM auth — exactly what we want.
- AES-GCM's AEAD auth tag still protects against tampering on each object; we lose only the belt-and-braces "filename hash matches contents" check.
- The minor cost: storage-layer CAS dedup is broken across the rotation boundary — a post-rotation commit identical to a pre-rotation commit produces ciphertext that hashes to a *different* filename, so it gets stored as a dup. Negligible in practice.

The genuinely-tricky issue this exposes is **client cache staleness** — a sparse clone with cached `abc123` (old ciphertext) won't re-fetch after rotation because IDs match. We solve this with explicit markers (§4).

---

## 3. CLI surface

```
sgit vault move [<directory>]
    [--new-key <vault-key>]        # optional; auto-generated if omitted
    [--to <api-url>]               # optional; stays on current server if omitted
    [--reason <text>]              # recorded in the sentinel commit
    [--yes]                        # skip interactive confirmations (CI use only)
    [--dry-run]                    # walk all 8 steps without side effects
    [--cleanup]                    # finish or roll back a partially-completed move
    [--token <access-token>]       # SG/Send access token (standard meaning)
```

Behaviour:

- **In-place rotation:** `sgit vault move` (no flags). Generates new vault-key, prompts for confirmation, re-encrypts every object into a temp folder, pushes to the same server under a NEW vault-id, then atomically renames the temp folder over the original and deletes the old vault from the server.
- **Server move:** `sgit vault move --to https://other-server.example.com`. Same as above but pushes to the target server and deletes from the source.
- **Server move + key rotation:** both flags together. Default workflow for "the leaked vault gets a clean new home with a clean new key."
- **`--cleanup`:** if a previous `vault move` was interrupted (`.sg_vault_new/` exists locally, OR the local clone is on the new vault but the old vault is still on the source server), `--cleanup` finishes the operation — completes the rename and/or retries the source-server delete. Idempotent: if the old vault is already tombstoned (server returns 403), treat as "already cleaned up." No persisted state file is needed; `.sg_vault_new/`'s presence and the move-history.json record are the only state indicators.

Exit codes: 0 success; 1 user aborted at a prompt; 2 mid-operation failure (with clear recovery instructions in stderr).

---

## 4. Markers — auditing the rotation

Two layers — both serve as audit trail. There is **no proactive cache-invalidation logic in `sgit pull`**: because `vault_id` always changes on every move, an existing clone pointing at the old vault_id naturally hits 404/403 from the server when it tries to pull. The user's recovery path is to clone the new vault, not to have `pull` do magic.

### 4a. Vault-key generation counter

`Schema__Vault_Meta` (or wherever vault-level metadata lives) gains a `key_generation: int` field. Starts at 1 on `sgit init`. Increments on every successful `vault move`. Stored alongside the move-history record below; used purely for chain-integrity auditing (each move-history entry's `key_generation` must equal `previous.key_generation + 1`).

### 4b. `move-history.json` (local + server)

New file at `.sg_vault/local/move-history.json` (and mirrored to the server's vault metadata):

```json
{
  "moves": [
    {
      "from_vault_id": "old-vault-id-abcd",
      "to_vault_id":   "new-vault-id-efgh",
      "from_api":      "https://dev.send.sgraph.ai",
      "to_api":        "https://dev.send.sgraph.ai",
      "key_generation": 2,
      "rotated_at":    "2026-05-06T18:00:00Z",
      "reason":        "Leaked in agent session 2026-05-06"
    }
  ]
}
```

Schema: `Schema__Vault_Move_Record` + `Schema__Vault_Moves` (round-trip enforced — same pattern B02 used for migration records).

Clients can walk this to verify lineage: "I last saw vault-id X; I now see vault-id Y; the move-history shows X→Y, with reason; trust restored."

### 4c. Sentinel commit on the named branch

When a `vault move` rotates, append a sentinel commit to every active named branch:

```
vault-move: rotated to vault-id <new> at 2026-05-06T18:00:00Z
  reason: leaked in agent session
  from-vault-id: <old>
  to-vault-id:   <new>
  key-generation: 2
```

The commit's tree is unchanged (same tree reference as its parent). The message and parent linkage carry the audit. This makes the rotation visible in `sgit history log` — agents and humans see the marker naturally, no need to look at side files.

**Required:** the sentinel commit is signed with the new branch signing key. Use the existing signing path; verify in tests that the sentinel verifies under the new key, fails under the old.

---

## 4d. SG/Send tombstone behaviour (server-side, MUST READ)

When the source server receives `DELETE /api/vault/destroy/{vault_id}`, it:

1. Validates the write key.
2. Deletes ALL objects under the vault prefix in S3 (manifest, all `bare/data/*`, all `bare/refs/*`).
3. Writes a permanent **tombstone** file (`deleted.json`) at the vault prefix.

Once the tombstone exists, **no write operation to that `vault_id` will ever succeed with any key** — every write attempt returns `HTTP 403 {"detail": "Write key mismatch"}`. The tombstone is permanent; there is no server-side endpoint to remove it. Reads return `200 {status: not_found}` (objects gone, but reads aren't blocked); list returns `{files: []}` (tombstone itself is invisible to clients).

**Implementation implications:**

- **Step 8 ordering is correctness-critical** (see §5c step 8). Local rename must complete before server delete; otherwise a local-rename failure strands the client on a permanently-tombstoned `vault_id`.
- **Tombstone 403 must be detected and translated.** When SGit pushes to a vault and gets `HTTP 403 {"detail": "Write key mismatch"}`, it should check whether the move-history shows this `vault_id` as a `from_vault_id` (i.e. the user moved away from this vault). If yes, surface `"Vault {vault_id} has been permanently moved/deleted. Clone the new vault at {to_vault_id}."` instead of the raw `"write key mismatch"` (which implies a credentials problem).
- **`Vault__API__In_Memory` must simulate tombstone behaviour** so transaction tests in brief 03 can exercise this path without a real server. See §5c commit 1 (tombstone simulation lands in brief 02 as the first commit).

---

## 5. Implementation outline

The operation is **transactional**: nothing destructive happens until the new vault is fully built, uploaded, and verified on the target server. Any failure before step 8 is recoverable by deleting the temp folder and the partially-uploaded target vault — no data loss, no half-state in the user's working clone.

### 5a. New: `Vault__Object_Store.store_at(object_id, content)`

Adds a lower-level API to write specific bytes to a specific object ID without re-hashing. Today's `store(content)` derives the filename from `hash(content)`; the rotation operation needs to preserve filenames.

`store_at` should:
- Accept `object_id` and `content` (bytes).
- Refuse to overwrite an existing object unless `force=True` is passed (the rotation passes `force=True`; everything else doesn't).
- Not validate `hash(content) == object_id`. Trust the caller.
- Be in a separate test file with explicit tests including the no-overwrite default and the force-overwrite path.

### 5b. New: `sgit_ai/core/actions/move/Vault__Sync__Move.py`

The action class. Method `move(directory, new_vault_key, target_api_url, reason)` orchestrates the workflow below.

### 5c. Workflow — `Workflow__Vault_Move`

The move runs through the workflow framework so it gets the standard tracing, cleanup semantics (via `--cleanup`, see §8c), and step-by-step audit trail. **Critical design rule: nothing destructive happens until step 7.** Every step before 7 leaves the user with their original vault intact; abort at any point via Ctrl+C, the temp folder, and any partially-uploaded vault on the target server are the only cleanup needed.

The eight steps:

1. **`Step__Move__Validate_Local`**
   Confirm working copy is clean; pull fresh from current server; walk the head tree and verify integrity (decrypt every object reachable from HEAD using current key — fails fast if local clone is already corrupt). Reject moves on dirty working copies.

2. **`Step__Move__Derive_New_Keys`**
   Generate the new vault-key (or accept the user-provided one), derive new vault-id, new read/write keys, new branch signing keys (per §8a). Hold all in memory; nothing written to disk yet except the new key into the temp folder created in step 3.

3. **`Step__Move__Build_Temp_Vault`**
   Create `.sg_vault_new/` *next to* the existing `.sg_vault/`. Walk every object in `.sg_vault/bare/data/`, decrypt with the old key, re-encrypt with the new key, write to `.sg_vault_new/bare/data/<same-object-id>` via `store_at(object_id, new_ciphertext)`. Same for `bare/refs/` and `bare/indexes/`. Write the new VAULT-KEY into `.sg_vault_new/VAULT-KEY`. Write `.sg_vault_new/local/move-history.json` with the new entry chained on top of the old vault's existing move-history. Bump `key_generation`. **The user's working `.sg_vault/` is untouched.**

4. **`Step__Move__Write_Sentinel_Commits`**
   Inside `.sg_vault_new/`, append the sentinel commit to each active named branch — same tree as parent, message `vault-move: rotated to vault-id <new> at <ts>`, signed with the new branch signing key. Updates ref files inside `.sg_vault_new/bare/refs/`. Still no server contact.

5. **`Step__Move__Push_To_Target`**
   Push `.sg_vault_new/` to the target API URL (which may equal the source URL but registers a NEW vault-id on the server — there is no collision because vault-id changed). This is essentially a fresh push to a vault that doesn't yet exist on the target. Use the existing push workflow; force-push semantics not required because target vault-id is brand new.

6. **`Step__Move__Verify_Target`**
   Probe the target API: confirm vault-id resolves; pull the move-history.json from the server and assert it matches the local one; pull the head ref and assert the sentinel commit is present and decrypts cleanly under the new key; sample a handful of objects and assert decryption works. Up to this point, **the operation is fully reversible**: just delete `.sg_vault_new/` locally and call the target API to delete the new vault-id.

7. **`Step__Move__Backup_Old_Vault`** ← *destructive boundary starts here*
   Zip the existing `.sg_vault/` to `<directory>/.sg_vault/backups/<old-vault-id>__<timestamp>.zip`. The backup zip contains the full bare/ tree + refs + indexes + local config — i.e. everything needed to read the old vault offline IF the user keeps the old vault-key. Optionally include `VAULT-KEY` inside the zip when the user opts in (see §7 prompt). Compute and store SHA-256 of the zip in a sidecar `.sha256` file for integrity-on-restore.

8. **`Step__Move__Delete_Source`**
   **Two ordered sub-steps. The order matters because the SG/Send tombstone is permanent.**

   **8a. Atomic local rename (FIRST):**
   ```
   mv .sg_vault          → .sg_vault_old_<ts>
   mv .sg_vault_new      → .sg_vault
   rm -rf .sg_vault_old_<ts>
   ```
   The client is now on the new vault. If this fails, `.sg_vault_new/` and the original `.sg_vault/` both still exist locally and the old vault on the source server is also still intact — fully recoverable via `sgit vault move --cleanup`.

   **8b. Server delete (SECOND):**
   `DELETE /api/vault/destroy/{old_vault_id}` on the source server. The server writes a permanent tombstone — no future write to that `vault_id` will ever succeed (with any key). If 8b fails, the user has TWO valid vaults — old still on source server, new on target — both readable by their respective keys. Surface a clear "old vault still live on server, run `sgit vault move --cleanup` or `sgit vault delete-on-remote` on the old vault to remove it" message. **No data loss.**

   Print the success summary and prompt about backup retention (§7 final prompt).

   **Critical correctness note: never reverse 8a and 8b.** If the server delete happens before the local rename, a local-rename failure would strand the user's working clone pointing at a permanently-tombstoned vault_id — no recovery without admin intervention on the SG/Send server.

**Failure semantics per step:**

| Failure at step | Recovery action | Is data loss possible? |
|---|---|---|
| 1–4 (local only) | `rm -rf .sg_vault_new/`. User's vault is untouched. | No |
| 5 (target push fails) | `rm -rf .sg_vault_new/`. Call target API to delete partially-pushed vault-id (idempotent if it doesn't exist). | No |
| 6 (target verification fails) | Same as 5. Plus log the verification mismatch as a P1 issue for investigation. | No |
| 7 (backup zip fails) | `rm -rf .sg_vault_new/`. Vault is unchanged. Surface clear "couldn't write backup, aborting before any destructive change" message. | No |
| 8a (local rename fails) | `.sg_vault_new/` and `.sg_vault/` both exist locally; target vault on server is fine. Recovery: `sgit vault move --cleanup` retries the rename atomically. | No |
| 8b (server delete fails) | Local clone is on the new vault; old vault still live on source server. Two vaults exist. Recovery: `sgit vault move --cleanup` retries the delete (or user runs `sgit vault delete-on-remote` on the old directory if they kept it). | No (both vaults intact) |

The brief should treat "no data loss possible before step 7" as the design contract and ensure the test suite exercises every failure mode at every step.

### 5d. Backup as a reusable primitive

Step 7's backup is the obvious building block for a separate `sgit vault backup` command. Out of scope for this brief but worth noting in the implementation: structure `Step__Move__Backup_Old_Vault` so the zip-creation logic lives in `sgit_ai/core/actions/backup/Vault__Backup.py` as a reusable class, called by the move workflow but also callable standalone in a future brief.

The standalone command would be:
```
sgit vault backup [<directory>] [--include-key]
    [--output-dir <dir>]   # default: <directory>/.sg_vault/backups/
```
With the same `--include-key` prompt explained in §7. Ship the helper class now; ship the standalone CLI later.

### 5e. CLI handler `cmd_vault_move` in `CLI__Vault.py`

The handler does the user-prompt UX (§7) then calls `Vault__Sync.move(...)` which delegates to the workflow runner.

### 5f. Add delegate to umbrella facade `Vault__Sync`

`sgit_ai/core/Vault__Sync.py` is the umbrella facade that all CLI handlers reach through. Add:

```python
def move(self, directory: str, new_vault_key: str = None,
         target_api_url: str = None, reason: str = '',
         on_progress: callable = None) -> dict:
    return Vault__Sync__Move(crypto=self.crypto, api=self.api).move(
        directory, new_vault_key, target_api_url, reason, on_progress)

def move_cleanup(self, directory: str, on_progress: callable = None) -> dict:
    return Vault__Sync__Move(crypto=self.crypto, api=self.api).cleanup(
        directory, on_progress)
```

Mirror the existing pattern used for `clone()`, `pull()`, etc.

### 5g. `Vault__API__In_Memory` tombstone simulation

The transaction tests in brief 03 (`Test_Vault__Sync__Move__Transaction`) need to verify that a tombstoned vault rejects writes with HTTP 403 — but they shouldn't depend on a real SG/Send server being reachable. Extend `Vault__API__In_Memory` to track tombstoned vault_ids:

- On `delete_vault(vault_id)`: record the vault_id in an internal `_tombstoned: set[str]` and remove all stored objects under that vault_id.
- On any write operation (`write`, `batch_write`, `write_if_match`, etc.): check `if vault_id in self._tombstoned: raise HTTPError(403, "Write key mismatch")`.
- On read operations: continue to return `not_found` for missing objects (tombstoned vault behaves as empty).
- On second `delete_vault(vault_id)` for a tombstoned id: also raise `HTTPError(403, "Write key mismatch")` (matches real server behaviour).

This lands as the FIRST commit of brief 02 (before any move workflow code) so subsequent move tests can use it.

---

## 6. Tests

In `tests/unit/core/actions/move/test_Vault__Sync__Move.py` (new directory). All real — zero mocks; use `Vault__Test_Env`.

Mandatory cases:

1. `test_move_inplace_rotates_key_and_preserves_history` — start with a vault containing 3 commits; move with new key; pull from a fresh clone with new key; assert all 3 historical commits + sentinel = 4 commits in `history log`; assert content unchanged.
2. `test_move_to_different_server` — second SG/Send instance fixture; move; pull from new server, fresh clone; same content + sentinel.
3. `test_move_object_ids_stable` — capture object ID set pre-move; capture post-move; assert set equality (only sentinel commit's blob/tree IDs are new).
4. `test_move_old_key_cannot_decrypt_after_move` — try to clone with old key; assert AES-GCM auth failure or "vault not found" (server-side delete).
5. `test_move_history_file_present_and_typed` — round-trip `move-history.json` through `Schema__Vault_Moves`; assert chain integrity.
6. `test_move_sentinel_commit_signed` — verify sentinel commit signature under new branch key; verify it fails verification under old key.
7. `test_move_old_vault_id_is_tombstoned_after_delete` — after move, attempt to push to the OLD vault_id; assert HTTP 403 (the tombstone permanently blocks writes); verify the SGit client surfaces a friendly "vault has been moved/deleted" message rather than the raw "write key mismatch".
8. `test_move_aborts_with_uncommitted_changes` — ensure the validate step blocks if working copy is dirty.
9. `test_move_failure_mid_operation_leaves_recoverable_state` — inject failure between step 6 (verify) and step 7 (backup). Assert the local clone is still readable with the OLD key; `.sg_vault_new/` is removable; user gets a clear "rerun sgit vault move --cleanup" message.

---

## 7. User prompts — confirmation UX

`vault move` is destructive. Build a multi-step confirmation flow with sensible defaults, designed so an agent or user has to actively confirm each implication before the operation begins.

The flow runs **before** any state change:

```
$ sgit vault move

  This will MOVE this vault to a new identity:

    Current vault-id:  ww7f3a-pasture-2841
    Current API:       https://dev.send.sgraph.ai
    Local directory:   /path/to/vault

  After the move:

    [1] The encryption key will be rotated.
        Current key:  ww7f3a-pasture-2841 (last 8: pasture-2841)
        New key:      crisp-mountain-7392        (auto-generated)

    [2] All ~500 objects will be re-encrypted under the new key.
        Object IDs stay the same; content is replaced in place.

    [3] A sentinel commit will be added to all 3 active branches:
          vault-move: rotated to vault-id crisp-mountain-7392

    [4] The new vault will be pushed to the target server:
          Target API:  https://dev.send.sgraph.ai          (unchanged)

    [5] The OLD vault will be backed up locally to a zip file:
          /path/to/vault/.sg_vault/backups/
            ww7f3a-pasture-2841__2026-05-06T18-00-00Z.zip

    [6] After backup, the OLD vault at vault-id ww7f3a-pasture-2841
        on https://dev.send.sgraph.ai WILL BE DELETED.
        This cannot be undone (without the local backup).

    [7] Anyone holding the old vault-key can no longer access the
        live vault. Active sparse clones with cached objects will
        re-fetch automatically on next pull.

  Confirm each:
    [1] Use generated new key 'crisp-mountain-7392'?
        [y/N/edit] →
    [2] Re-encrypt 500 objects?
        [y/N] →
    [3] Add sentinel commits to 3 branches?
        [y/N] →
    [4] Push to https://dev.send.sgraph.ai?
        [y/N/different] →
    [5] Save old vault to local backup zip?
        Include the OLD VAULT KEY inside the zip?
        WARNING: anyone who reads the zip can decrypt the contents.
                 Off by default; opt in only if you understand the risk.
        [y/N] include key  (default N)
    [6] DELETE old vault from server (after backup succeeds)?
        [y/N] →
```

**After the move completes**, one final prompt (only if the backup zip was written):

```
  Move complete. New vault is live at:
    Vault-id:  crisp-mountain-7392
    API:       https://dev.send.sgraph.ai

  Old vault backed up to:
    /path/to/vault/.sg_vault/backups/ww7f3a-pasture-2841__...zip
    (vault-key NOT included — readable only with the old key)

  Keep the backup zip?
    [Y/n]                                     # default Y

  If you delete it AND don't have a copy of the old vault-key,
  the contents of that vault are unrecoverable. Are you sure?
    [y/N]                                     # default N (only asked if user said n above)
```

Implementation rules:

- **Each prompt is interactive `input()` with a clear default.** Default to "no" (abort) for destructive prompts; default to "yes" for the safe data-shape prompts. Capital letter in `[y/N]` is the default.
- **`edit` lets the user override the auto-generated value** (for prompt [1] and the API for prompt [4]). The generated default is shown so the user can just press enter.
- **`--yes` skips all prompts** for CI / scripted use. Document it as "for automation only — assumes you have validated the operation in a dry run."
- **Add `--dry-run`** that walks all 8 workflow steps without any side-effects, prints what would happen, and exits. Useful for "I want to see exactly what this will do" without committing.
- **Print a summary block at the end of all prompts** before kicking off step 1: `"Starting vault move. Press Ctrl+C in the next 5 seconds to abort."` Followed by a 5-second sleep with countdown. Last chance to abort.
- **Never silently proceed past a destructive choice.** If the user types anything except `y`/`yes` to a destructive prompt, abort with a clear "vault move cancelled — no state changed" message.

This UX must be tested. Add `tests/unit/cli/test_CLI__Vault__Move__Prompts.py` with at least:
- All-yes path completes.
- "no" at any prompt aborts.
- `edit` accepts a custom value and uses it.
- `--yes` skips all prompts.
- `--dry-run` performs no state change.

---

## 8. Resolved decisions

These were open questions in earlier drafts; resolved by Dinis on 2026-05-06. Listed here for the executor's reference.

### 8a. Branch signing keys: ALWAYS rotate

Every `vault move` rotates the per-branch signing keys unconditionally. Step 2 (`Step__Move__Derive_New_Keys`) generates new branch signing keypairs alongside the new vault key. The sentinel commit is signed under the new branch key. **No CLI flag** — the rotation is always-on, never optional.

Rationale: the typical move trigger is a leak; treating "server move only, no key rotation" as a separate code path adds complexity for marginal benefit. If a user truly wants to move servers without rotating keys, that's a future feature with a different command — not a flag on `vault move`.

### 8b. Stale-clone adoption on `pull`: NOT NEEDED

There is no special "stale clone adoption" code path in `sgit pull`. Because `vault_id` always changes on every `vault move`, an existing clone pointing at the old `vault_id` naturally hits 404 (vault deleted from source) or 403 (tombstoned) when it tries to pull. The user's recovery path is to clone the new vault — not to have `pull` perform automatic key adoption.

This decision **drops** the originally-proposed `key_generation`-driven cache invalidation on pull (and the corresponding `test_Vault__Sync__Move__Stale_Cache.py` test file in brief 03). `key_generation` is retained only as an audit-chain integrity field in `move-history.json`.

### 8c. Atomicity: `--cleanup` not `--resume`

The originally-proposed `--resume` semantic with a persisted `move-in-progress.json` state file is replaced by a simpler `--cleanup` flag.

`--cleanup` semantics:
- If `.sg_vault_new/` exists and the local clone is still on the old vault → resume from step 8a (atomic local rename).
- If the local clone is on the new vault (move-history shows the recent rotation) but the old vault is still live on the source server → resume from step 8b (server delete).
- If the old vault is already tombstoned (server returns 403 on delete) → treat as "already cleaned up", exit 0.
- If `.sg_vault_new/` does not exist and the move-history shows no recent in-progress move → exit 1 with `"no pending move to clean up"`.

`.sg_vault_new/`'s presence on disk + the most recent `move-history.json` record together capture all the state needed. No separate state file required.

---

## 9. Vault web team debrief — separate document

After the CLI lands, write a short debrief for the Vault web team (the JS client that opens vaults in the browser). Filename: `team/humans/dinis_cruz/claude-code-web/05/06/vault-web-debrief__vault-move-support.md` (or appropriate date).

The debrief should cover:

1. **The rotation primitive.** What `sgit vault move` does at the wire level: existing object IDs get new ciphertext under a new key; vault-id changes; key-generation counter increments; sentinel commit appears on named branches.

2. **JS client: detecting a moved vault.**
   - On page load, if the cached vault-id doesn't resolve on the API (404), the client should check if the user has a `move-history.json` URL (or a redirect mechanism) pointing at the new vault-id.
   - Optionally: SG/Send can expose a "where did this vault go?" endpoint that returns the move-history record. **Up to the SG/Send API team to spec.**

3. **JS client: handling stale cache (rare edge case).**
   - In most cases, the JS client doesn't need to handle stale cache: vault_id changes on every move, so any cache keyed by `(vault_id, object_id)` automatically invalidates.
   - The edge case: if the JS client uses a global cache keyed by `object_id` only (not scoped to `vault_id`), the same `object_id` could resolve to old ciphertext from before a move. AES-GCM decryption fails on old ciphertext + new key. **Required behaviour:** treat AES-GCM auth failure on a cached object as a cache-miss and re-fetch from the server. If the second decryption also fails, surface a real error.
   - Recommendation: scope all caches by `vault_id` to avoid this entirely.

4. **JS client: surfacing the sentinel commit.**
   - The vault history view should call out `vault-move:` commits visually (different colour / icon) so users see when their vault was rotated and why.
   - Hover/click reveals the move-history record (from-id, to-id, reason, timestamp).

5. **Vault key change UX.**
   - When a user opens a moved vault with the OLD key (e.g. they bookmarked the URL with the old token), the JS should detect "I have a 401/404/403" and check whether SG/Send exposes a move-history lookup. If the SG/Send API ever exposes a "where did this vault go?" endpoint, the JS prompts: "This vault has been moved. Open the new vault at <new-vault-id>?" Until then, surface a clean "vault not found — has it been moved?" error rather than a cryptic auth failure.

The debrief is a follow-up — not blocking the CLI implementation.

---

## 10. Documentation

- Update CLI help-text to reference `vault move` in any "if your key leaked" guidance.
- Add a new section to the email-fs-lite Appendix A draft (when it lands) under "Recovery": one-line mention that `vault move` is the right tool for a leak.
- Reference `vault move` in `team/villager/v0.13.x__brief-pack/00e__v0.14.0-pre-release-brief.md` retrospectively as a follow-up that didn't make v0.14.0 (link forward — don't rewrite the brief).
- New skill / SKILL.md: `team/explorer/skills/vault-move-procedure.md` covering the human-driven workflow ("I think my key leaked — what do I do?").

---

## 11. Out of scope

- **Object-ID rewriting / graph rewrite migration approach** — explicitly rejected in favour of in-place rotation with stable IDs. Don't implement both. The earlier `Migration__Tree_IV_Determinism` is a separate one-shot for a different problem.
- **Backwards-compat for clients that don't understand `key_generation`** — internal-tooling release, clean break is fine. Pre-this-release clients fail loudly when they hit a rotated vault, which is the correct outcome.
- **Web team JS implementation** — out of scope for THIS brief. Captured in the debrief at §9.
- **Branch-level rotation (rotate one branch's signing key without touching the vault key)** — not needed for the leak case. Defer.
- **Multi-step move (move to server A, then server B without a final key)** — sequential `sgit vault move` calls handle this. No special support needed.

---

## 12. Verification checklist

When done:

1. `sgit vault move --help` documents all the prompts and flags.
2. `sgit vault move --dry-run` on a real vault prints all the prompts without making any state change.
3. End-to-end move on a test vault works with all 9 unit-test scenarios passing.
4. Move-history file round-trips through `Schema__Vault_Moves`.
5. Sentinel commit appears in `sgit history log` and is correctly signed.
6. Stale-cache invalidation works: clone, modify cache content (simulate stale ciphertext), trigger move, pull, verify cache is replaced.
7. The vault-web debrief at §9 is written and shared.

Estimated dev effort: ~1.5 days for the CLI work, plus ~½ day for the web debrief.
