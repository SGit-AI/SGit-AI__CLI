# 10 — Known Issues, Bugs & Gaps

**Author:** QA
**Audience:** Everyone

## Bug Tracker

### CRITICAL

#### BUG-001: Push silent failure on remote write error

**Severity:** CRITICAL — data loss risk
**Status:** Open (xfail test exists)
**Location:** `Vault__Sync.push()` / `Vault__Batch.execute_batch()`

When a batch upload partially fails (e.g., ref update succeeds but some blobs fail),
the push reports success. The user believes their data is on the server, but it isn't
fully there. A subsequent clone or pull from another machine may fail with missing objects.

**Impact:** Users may lose data if they delete their local copy after a "successful" push.

**Fix approach:** Verify all uploaded objects after push by reading back the ref and
walking the commit tree, or check batch response status per-operation.

---

### HIGH

#### BUG-002: File deletion doesn't propagate

**Severity:** HIGH
**Status:** Open (xfail test exists)

When User A deletes a file and pushes, User B's pull brings the file back.
The three-way merge correctly identifies the deletion, but the checkout step
doesn't always remove the file from the working directory.

**Root cause:** `_remove_deleted_flat()` only removes files present in `ours_map`
but not in `merged_map`. If the deletion happened on the remote side (theirs),
the file may not be in `ours_map` at all.

---

#### BUG-003: False merge conflicts after pull

**Severity:** HIGH
**Status:** Open (xfail test exists)

After pulling changes that modify a file, editing that same file locally and committing
triggers a false merge conflict on the next pull, even though the file was cleanly merged.

**Root cause:** The content_hash comparison may be stale — the merge commit's tree
re-encrypts metadata with a fresh IV, potentially generating a different blob_id even
for identical content.

---

### MEDIUM

#### BUG-004: Pull status after cross-clone merge

**Severity:** MEDIUM
**Status:** Open (xfail test exists)

After merging changes from another clone, `pull` reports `status: "merged"` instead
of `status: "up_to_date"` when there's actually nothing new to merge.

---

## Architectural Gaps

### GAP-001: No API retry logic

**Severity:** MEDIUM
**Impact:** Intermittent network errors cause hard failures

The `Vault__API` class has no retry logic. A single 5xx error or timeout fails the
entire operation. Should implement exponential backoff for transient errors.

### GAP-002: Multi-remote not wired

**Severity:** LOW (schema exists)
**Impact:** Only supports single remote

`Schema__Remote_Config` and `Vault__Remote_Manager` exist, but `Vault__Sync` always
uses a single `Vault__API` instance. Multi-remote push/pull is not implemented.

### GAP-003: Change pack integration incomplete

**Severity:** LOW
**Impact:** Feature not usable

`Vault__Change_Pack` and `Vault__GC` exist but the end-to-end flow (create pack →
drain into branch → push) is not battle-tested. Change packs are meant for scenarios
where external tools write changes without going through the full commit flow.

### GAP-004: Browser-CLI interop partial

**Severity:** MEDIUM
**Impact:** Some vaults created in browser can't be opened by CLI and vice versa

The browser (Web Crypto API) and CLI must produce identical ciphertext given the same
inputs. Some edge cases remain:
- Browser stores files with different path encoding
- Tree structure may differ (flat vs. hierarchical)
- Some CLI-created vaults cause 404s in browser

### GAP-005: No pagination on list_files

**Severity:** LOW (for now)
**Impact:** Large vaults may timeout on clone

`Vault__API.list_files()` returns all files at once. For vaults with thousands of
objects, this may timeout or consume excessive memory.

## Type_Safe Violations

### VIOLATION-001: Raw primitives in Vault__Components

**Severity:** BLOCKING (per CLAUDE.md rules)
**File:** `sg_send_cli/sync/Vault__Components.py`

`Vault__Components` uses raw `str` and `bytes` for `vault_key`, `vault_id`, `read_key`,
`write_key`, etc. These should be domain-specific Safe_* types.

### VIOLATION-002: Raw primitives in schemas

**Severity:** HIGH
**Files:**
- `Schema__Change_Pack` — `attestations` field
- `Schema__Vault_Policy` — `require_author_signature` (raw bool)
- Some schemas use raw `str` for optional fields

### VIOLATION-003: No Safe_Bool type

**Severity:** MEDIUM
**Impact:** `bool` fields in schemas violate the zero-raw-primitives rule

No `Safe_Bool` type exists. `Schema__Vault_Policy.require_author_signature` uses raw
`bool`. Need to create `Safe_Bool` or handle booleans differently.

## Security Notes

### SEC-001: Content hash collision window

The 48-bit content hash (`SHA256[:12]`) has a collision space of ~2^24 (~16M).
For change detection within a single vault this is fine, but it should not be used
for security-critical deduplication.

### SEC-002: Merge conflict marker parsing fragile

`Vault__Merge` uses simple filename suffix (`.conflict`) rather than a formal grammar.
A malicious file named `evil.txt.conflict` could be confused with a conflict marker.
