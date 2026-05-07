# Brief 18 Implementation Review

**Date:** 2026-05-07
**Reviewer:** Villager orchestrator (Opus deep audit)
**Scope:** Commits `5e7857e` (Brief 18 implementation) + `dd52d2d` (Reviewer Fix 13) on `claude/cli-explorer-session-J3WqA`.
**Verdict: 🟢 GO.** All four fixes from the brief landed cleanly with the right architectural shape.

---

## Headline

| Fix | Status | Notes |
|---|---|---|
| Fix A — clone full-history blobs | ✅ DONE | Blob collection added as side-effect of existing tree walk; new `_download_blobs_by_id` consumes the list |
| Fix B — move auto-repair from source server | ✅ DONE | `_try_repair_missing` fetches missing objects from source before aborting |
| Fix C — fsck dedup missing/corrupt lists | ✅ DONE | One-line `sorted(set(...))` change |
| Fix D — error message wording | ✅ DONE | Now points at `sgit check fsck --repair` |
| Walk_Trees__Head_Only symmetric update | ✅ DONE | Same blob-collection pattern; clone-branch stays thin |
| Reviewer Fix 13 (CLAUDE.md + thread-pool cap) | ✅ DONE | Docstrings removed; thread-pool capped at 8 (small) / 4 (large) |

Test counts: 8 unit + 4 integration = **12 new tests** (brief specified ~10; over-delivered). Zero mocks in any new test file. 198 clone + move unit tests pass.

---

## What's right

### Fix A — design choices that improve on the brief

The executor made **two architectural choices that are better than what the brief specified**:

1. **Splitting blobs into small vs large at collection time** (rather than my single-list approach). `Step__Clone__Walk_Trees` reads `entry.large` while loading each tree (cheap — already decrypted) and stashes IDs in two separate sets. This means `_download_blobs_by_id` doesn't need to re-decrypt or re-flatten to determine size class. Cleaner.

2. **Count-based chunking (50 blobs/chunk)** instead of the brief's implied size-based approach. The old `_clone_download_blobs` did size-based chunking using plaintext sizes from the flattened tree. Post-fix, we no longer have plaintext sizes at the chunking layer (we have raw blob IDs). Count-based is the right call. `BLOBS_PER_CHUNK = 50` is a reasonable starting point — large blob counts × small blob bytes still fit within Lambda's 3MB response cap for typical content.

### Fix A — `Step__Clone__Walk_Trees__Head_Only` updated symmetrically

`clone-branch` now uses the same blob-collection mechanism but only walks `root_tree_ids[:1]` (HEAD's tree). Result: the schema is consistent across all clone modes, but `clone-branch` STAYS THIN as designed. The integration test `test_clone_branch_remains_thin` is a deliberate negative regression — exactly the kind of "make sure the fix doesn't accidentally break the thin modes" check.

### Fix B — `_try_repair_missing` is a clean defence-in-depth

When `_verify_commit_graph` finds missing objects, the executor's implementation now:
1. Tries to fetch each missing object from the source server.
2. Re-checks what's still missing.
3. Aborts only if the repair didn't fully cover the gap.

After Fix A is rolled out, fresh clones won't hit this path. But it's exactly the right safety net for legacy clones running their first move post-upgrade — the auto-repair makes the recovery transparent.

### Fix D — error message correctly points at fsck

The previous "run sgit pull or sgit fetch first" was wrong (those commands have the same bug). Now:

```
... Run `sgit check fsck --repair` to download missing objects before
retrying vault move.
```

`fsck --repair` is the canonical "make my local clone whole" operation. Right answer.

### Reviewer Fix 13 — thread-pool cap matters

Without `min(len(chunks), 8)` and `min(len(large_blobs), 4)` caps, a vault with hundreds of historical blobs would spawn one thread per chunk → potential thread exhaustion, OS-level resource issues. The cap is a small but important correctness fix that wasn't in the brief but the reviewer caught.

### Mock discipline

`grep` confirms zero mocks in either new test file. `Vault__Test_Env` (unit) + real `vault_api` fixture (integration) used throughout. The integration test directly exercises `sync.fsck(clone_dir)` against a real local server fixture — exactly the standard from brief 15.

---

## Three minor observations (non-blocking)

### 🟢 1. Old `_clone_download_blobs` is now dead code

The HEAD-only flatten + download path at `Vault__Sync__Clone.py:_clone_download_blobs` is no longer called by `Step__Clone__Download_Blobs` (which uses `_download_blobs_by_id`). Worth a quick `grep -rn _clone_download_blobs sgit_ai/` to confirm nothing else calls it, then delete in a future reviewer-fix pass. Dead code is a smell that compounds over time.

### 🟢 2. `_try_repair_missing` swallows individual fetch errors silently

```python
for oid in missing:
    try:
        data = api.read(vault_id, f'bare/data/{oid}')
        if data:
            ...
    except Exception:
        continue       # ← silent
```

If 35 objects are missing and 5 fail to fetch (e.g. server hiccup), the user only sees the still-missing-after-repair count. The 5 fetch errors disappear. For now this is acceptable — the move aborts anyway with a clear message, and the user can rerun. Worth a stderr summary in a future polish pass: `"warning: 3 objects could not be fetched (server error); retry the move"`.

### 🟢 3. `BLOBS_PER_CHUNK = 50` is empirical

For a vault with 50 blobs averaging 60KB each, that's ~3MB per chunk = right at Lambda's response cap. If response payloads grow (more metadata, larger objects), occasional chunks may hit the cap and fail. Worth keeping an eye on in production; trivial to tune later. Not urgent.

---

## What this fix means

The Brief 15 §2a commit-graph integrity check was load-bearing for safety — it was the band-aid stopping `vault move` from corrupting vaults on cloned sources. With Fix A landed:

- **Fresh clones download every reachable blob.** Post-clone `fsck` reports zero missing.
- **`history show <past-commit>` works** on any cloned vault.
- **`history diff` and `history log --patch`** produce complete output.
- **`vault move` on a fresh clone passes Validate_Local cleanly** — no missing-objects abort.
- **§2a downgrades from "essential" to "defence-in-depth"** — exactly where it belongs.

Combined with Fix B (auto-repair on legacy clones), the recovery story for users with pre-fix clones is: try `vault move`; if §2a fires, the auto-repair downloads the missing objects from the source server before aborting; user re-runs and it passes. No manual `fsck --repair` step needed in most cases.

---

## Recommendation

🟢 **Merge to dev.** This is a clean implementation of a critical fix. Three observations are all non-blocking polish for future reviewer-fix passes.

**Three small follow-ups to fold into the next reviewer-fix pass** (probably brief 16's pass when it picks up the §3b/§3c cosmetic items):

1. Delete the dead `_clone_download_blobs` method.
2. Add a stderr summary in `_try_repair_missing` for individual fetch failures.
3. Add a one-line comment to `BLOBS_PER_CHUNK = 50` noting the Lambda 3MB constraint that informs the choice.

Updated v0.14.x landing order after Brief 18 merges:

```
✅ 18 — clone full-history blobs                  (DONE, this commit)
1. 16 — brief-15 cosmetic follow-ups (~1h)
2. 17 — commit-id prefix resolution (~½ day)
3. 12 — vault move cleanup pass (~½ day)
4. 09 — schema-parse error handling (~½ day)
5. 06 — dotfile tracking (~½ day)
6. 07 — .vault-settings + initial commit (~1 day)
7. 08 — --vault-key flag (~½ day)
8. 10 — command graph + suggestions (~1.5 days)
```

After Brief 10, visualisation track is unblocked.

The test-coverage discipline brief 15 introduced is paying off here too — the integration test `test_clone_then_vault_move_passes_validation` is the explicit end-to-end regression that ties Brief 15 §2a's safety check to Brief 18's root-cause fix. That's the kind of test that prevents the next round of "found by Dinis on a real vault" surprises.
