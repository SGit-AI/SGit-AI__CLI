# Debrief 17 — Clone does not download historical blobs (data-loss risk)

**Date:** 2026-05-07  
**Found by:** Dinis Cruz (live `sgit vault move` session)  
**Severity:** 🔴 Critical — silent data loss on vault move; degraded history commands  
**Status:** Root cause confirmed, fix not yet implemented

---

## 1. How it was found

A vault was freshly cloned from the server. `sgit vault move` was then run on
the clone. The Brief 15 §2a integrity check (commit graph walk added to
`Step__Move__Validate_Local`) fired:

```
error: Local vault is missing 35 object(s) referenced by the commit graph
(e.g. obj-cas-imm-...). The move would ship an incomplete vault to the server.
Run `sgit pull` or `sgit fetch` first to complete the local clone before
retrying vault move.
```

Initial hypothesis: the missing objects belonged to **other cloners' branches**
(a known limitation). That theory was disproved when `sgit check fsck` was run
on both the original local vault and a freshly cloned copy:

```
$ sgit check fsck .           # run on a fresh clone
  ▸ Checked 59 commits, 1 trees
  Missing objects: 234
    ! obj-cas-imm-<...>       # same IDs repeated
    ! obj-cas-imm-<...>
    ... and 224 more
```

A clone that just finished downloading reported **234 missing objects
immediately** — before any other operation.

---

## 2. What the evidence shows

| Operation | Reported number |
|-----------|----------------|
| Clone: commits walked | 59 |
| Clone: trees walked | 415 |
| Clone: blobs downloaded | 165 |
| fsck: objects missing after clone | 234 |

The clone walked 415 trees across the full commit history but downloaded only
165 blobs. `fsck` then walked the same 59-commit chain and found 234 objects
missing locally.

---

## 3. Root cause

The clone's blob-download step fetches **only the blobs needed to reconstruct
the current HEAD working copy** — i.e., one blob per file that currently exists
in the vault's latest state.

It does **not** download blobs for historical versions of files that have since
been modified or deleted.

In a content-addressable store, every unique version of every file is a
separate blob object. A vault with 59 commits and active file churn will have
far more blob objects in its history than it has files in its HEAD tree.

**Concretely:**
- If `README.md` was committed 10 times, there are 10 distinct blob objects.
- Clone downloads the HEAD version (1 blob).
- The 9 historical versions remain on the server but are not downloaded.
- `fsck` flags the 9 historical blobs as missing → correct, they are.

---

## 4. Impact

### 4a. Vault move creates an incomplete new vault (🔴 data loss)

`Step__Move__Build_Temp_Vault._reencrypt_objects` iterates `os.listdir(bare/data/)`.
Only locally-present objects get re-encrypted and pushed to the new vault.
Historical blobs that were never downloaded are silently absent from the new
vault.

After the move:
- Old vault is tombstoned (permanently deleted).
- New vault is missing all historical file versions.
- Anyone cloning the new vault and running `sgit history show <old-commit>`
  gets decryption errors for any file that changed between that commit and HEAD.

**The Brief 15 §2a integrity check prevented this.** Without it, the move would
have completed silently and the data loss would only be discovered later (or
never, if no one inspects history).

### 4b. History commands are degraded on any clone

`sgit history show`, `sgit history diff`, and `sgit history log --patch` all
need to decrypt historical blobs. Those commands will fail or silently produce
incomplete output on any cloned vault because the historical blobs were never
downloaded.

### 4c. `sgit check fsck` duplicate output (minor bug)

The `fsck` output lists the same object ID multiple times (e.g., the same blob
is referenced by 4 different historical tree objects and therefore appears 4
times in `result['missing']`). The list is not deduplicated before printing.
This inflates the reported "Missing objects" count and makes triage harder.

---

## 5. What the Brief 15 fix saved

Without the `Step__Move__Validate_Local` commit graph walk:

1. Move would have appeared to succeed.
2. New vault on server would have been silently incomplete.
3. Old vault would have been tombstoned.
4. Data recovery would require: knowing which objects were missing, having the
   old vault key, and the old vault not having been garbage-collected.

The fix correctly blocked the move and gave a clear error. The error message
("run `sgit pull` first") is wrong — pull has the same selective-download
behaviour — but the abort is the right outcome.

---

## 6. Fixes required

### Fix A — Clone must download ALL historical blobs (critical)

The blob-download step in the clone workflow must be changed from
"blobs needed for HEAD checkout" to "all blobs reachable from the full commit
chain."

This is the canonical definition of a full clone in any content-addressable
VCS. The current behaviour is closer to a shallow/sparse checkout.

File to change: wherever the clone's blob download loop runs (the step that
produced "Downloading blobs [165/165]").

### Fix B — Move must fetch missing objects before re-encrypting (defence-in-depth)

Even after Fix A, a future clone could miss objects due to a network
interruption or another edge case. The move workflow should:

1. Run the commit graph walk (already done by Brief 15).
2. If objects are missing, attempt to fetch them from the old vault server
   (the old vault is still live at this point and the credentials are available).
3. Only abort if fetch fails — not on first discovery of a gap.

`sgit check fsck --repair` already implements the per-object fetch logic
(`_repair_object`). The move workflow can reuse it.

### Fix C — Dedup missing-object list in `fsck` output (minor)

Change `result['missing'].append(oid)` to check membership first, or
deduplicate before printing. The count and the list should reflect unique
object IDs.

### Fix D — Update error message in move (low priority)

"Run `sgit pull` or `sgit fetch` first" is misleading because pull/fetch have
the same selective-download behaviour. Change to:

```
Run `sgit check fsck --repair` to download all missing objects from the
server before retrying vault move.
```

---

## 7. Order of work

1. **Fix A** — clone full history blobs. This is the root cause fix.
2. **Fix C** — dedup fsck output (quick, unblocks triage).
3. **Fix B** — move auto-repair (defence-in-depth, can land after Fix A).
4. **Fix D** — error message (trivial, anytime).

Fix A must land before any user runs `sgit vault move` on a cloned vault.
