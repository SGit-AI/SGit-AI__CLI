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
    [--token <access-token>]       # SG/Send access token (standard meaning)
```

Behaviour:

- **In-place rotation:** `sgit vault move` (no flags). Generates new vault-key, prompts for confirmation, re-encrypts every object on the local clone, force-pushes the rotated bare objects to the same server, deletes the old vault from the server.
- **Server move:** `sgit vault move --to https://other-server.example.com`. Same as above but pushes to the target server and deletes from the source.
- **Server move + key rotation:** both flags together. Default workflow for "the leaked vault gets a clean new home with a clean new key."

Exit codes: 0 success; 1 user aborted at a prompt; 2 mid-operation failure (with clear recovery instructions in stderr).

---

## 4. Markers — how clients detect the rotation

Three layers, each cheap, each useful:

### 4a. Vault-key generation counter

`Schema__Vault_Meta` (or wherever vault-level metadata lives) gains a `key_generation: int` field. Starts at 1 on `sgit init`. Increments on every successful `vault move`.

Clients that pull and see `key_generation` ahead of their local last-seen value know to wipe their object cache and re-fetch.

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

**Required:** the sentinel commit is signed with the new branch signing key (or a special vault-move key — TBD). Use the existing signing path; verify in tests that the sentinel verifies under the new key, fails under the old.

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

The move runs through the workflow framework so it gets the standard tracing, resume semantics, and step-by-step audit trail. **Critical design rule: nothing destructive happens until step 7.** Every step before 7 leaves the user with their original vault intact; abort at any point via Ctrl+C, the temp folder, and any partially-uploaded vault on the target server are the only cleanup needed.

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
   Call the source-server API to delete the old vault-id. Replace the local working `.sg_vault/` with `.sg_vault_new/` (atomic rename: `mv .sg_vault .sg_vault_old_<ts>` then `mv .sg_vault_new .sg_vault`, then `rm -rf .sg_vault_old_<ts>`). Update CLI state. Print the success summary and prompt about backup retention (§7 final prompt).

**Failure semantics per step:**

| Failure at step | Recovery action | Is data loss possible? |
|---|---|---|
| 1–4 (local only) | `rm -rf .sg_vault_new/`. User's vault is untouched. | No |
| 5 (target push fails) | `rm -rf .sg_vault_new/`. Call target API to delete partially-pushed vault-id (idempotent if it doesn't exist). | No |
| 6 (target verification fails) | Same as 5. Plus log the verification mismatch as a P1 issue for investigation. | No |
| 7 (backup zip fails) | `rm -rf .sg_vault_new/`. Vault is unchanged. Surface clear "couldn't write backup, aborting before any destructive change" message. | No |
| 8 mid-step (source delete fails) | The user now has TWO valid vaults — old one on source server, new one on target server. Both readable by their respective keys. Surface clear "two vaults exist, run `sgit vault move --resume` to retry source delete, OR manually delete via `sgit vault delete-on-remote`" message. | No (both vaults intact, just messy state) |
| 8 mid-step (local rename fails) | Vault is on target server with new key; backup zip exists; local working clone is in transition state. Recovery: `sgit vault move --resume` finishes the rename. | No (target vault is fine; local is recoverable from `.sg_vault_new/` or from re-cloning). |

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
7. `test_move_client_with_stale_cache_invalidates_on_pull` — clone before move; cache `bare/data/<id>`; perform move; pull on stale client; assert key-generation counter triggers a re-fetch (cache invalidated, new ciphertext written under same id).
8. `test_move_aborts_with_uncommitted_changes` — ensure the validate step blocks if working copy is dirty.
9. `test_move_failure_mid_operation_leaves_recoverable_state` — inject failure between step 6 (sentinel written) and step 7 (push). Assert the local clone is still readable with the new key; user gets a clear "rerun sgit vault move --resume" message.

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

## 8. Open questions to resolve before coding

### 8a. Do branch signing keys rotate too?

If a vault key leaks, the **branch signing keys** stored locally per-clone may or may not be compromised — depends on how the leak happened. Two options:

- **Branch keys rotate:** every active branch gets a new signing keypair. The vault-move workflow generates them and re-signs every commit it touches (the sentinel) under the new key. Old branch verifications fail under new keys, which is the expected security property. **Recommended for a leak scenario.**

- **Branch keys preserved:** the vault encryption key rotates but signing keys carry over. Faster operation. **Acceptable for "I just want to move servers, no leak."**

Make this a CLI flag: `sgit vault move [--rotate-branch-keys]` (default on for `vault move`; off if `--reason` is "server-move"). Or split into `sgit vault rotate-key` (keys only, no server move) vs `sgit vault relocate` (server only, no key change). My recommendation: one command with the flag — simpler vocabulary.

### 8b. What about clone-branch / sparse / clone-readonly?

After a move, all existing clones must:
- Update their local `VAULT-KEY` to the new key.
- Update their local `clone_mode.json` (read-only clones) with the new read-key.
- Trigger cache invalidation on first pull post-move.

The natural mechanism: when a client pulls and sees `key_generation` ahead, the pull tells them "vault has moved — run `sgit vault adopt-move` to update local keys." Or: bake the auto-update into pull itself if the client has the old key locally available.

**Decide before coding:** is move adoption automatic (pull figures it out) or explicit (user runs `sgit vault adopt-move`)? My recommendation: automatic pull with a prominent "vault key has been rotated" message — saves one user step in the common case.

### 8c. Atomicity

Step 7 (push to target) is the irreversible point. Everything before it is local and recoverable. After step 7, the source delete (step 8) must either succeed or leave the user with a clear "two valid vaults exist" state plus instructions to manually delete the source.

The brief should flag this as the failure mode requiring most care. Have the executor design a clear `--resume` semantic so an interrupted move can be picked up by re-running `sgit vault move --resume`.

---

## 9. Vault web team debrief — separate document

After the CLI lands, write a short debrief for the Vault web team (the JS client that opens vaults in the browser). Filename: `team/humans/dinis_cruz/claude-code-web/05/06/vault-web-debrief__vault-move-support.md` (or appropriate date).

The debrief should cover:

1. **The rotation primitive.** What `sgit vault move` does at the wire level: existing object IDs get new ciphertext under a new key; vault-id changes; key-generation counter increments; sentinel commit appears on named branches.

2. **JS client: detecting a moved vault.**
   - On page load, if the cached vault-id doesn't resolve on the API (404), the client should check if the user has a `move-history.json` URL (or a redirect mechanism) pointing at the new vault-id.
   - Optionally: SG/Send can expose a "where did this vault go?" endpoint that returns the move-history record. **Up to the SG/Send API team to spec.**

3. **JS client: detecting cache staleness via decryption failure.**
   - Currently the JS client probably caches `obj-cas-imm-<id>` blobs by ID in IndexedDB or memory.
   - Post-move, the same ID points at NEW ciphertext on the server. If the JS still has OLD ciphertext cached, it'll try to decrypt with the new key and AES-GCM will fail.
   - **Required behaviour:** when AES-GCM decryption fails on a cached object (and the user has the right key), re-fetch from the server and try again. If second decryption also fails, surface a real error to the user. This auto-recovery makes moves transparent.

4. **JS client: surfacing the sentinel commit.**
   - The vault history view should call out `vault-move:` commits visually (different colour / icon) so users see when their vault was rotated and why.
   - Hover/click reveals the move-history record (from-id, to-id, reason, timestamp).

5. **Vault key change UX.**
   - When a user opens a moved vault with the OLD key (e.g. they bookmarked the URL with the old token), the JS should detect "I have a 401/404 + this vault has a known move-history" and prompt: "This vault has been rotated. Enter the new key: ___". This is the JS equivalent of `sgit vault adopt-move`.

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
