# Architecture & Implementation Plan — Per-Path Indexes for sgit

**Author:** Fable (architect capacity) · **Date:** 2026-08-06 · **Responds to:** `v0.33.56__devbrief__sgit-per-path-indexes` (13th of 6 Aug)
**Method:** grounded against the current codebase; every mechanism is cited to `file:line`. This is a design + phased plan, not an implementation.

---

## 0. One-paragraph summary

The brief is correct that this is **a new domain string plus a write-path obligation, not a new subsystem** — I verified every mechanism it relies on against the code. A per-path index is a **mutable object at a client-computable location**: `id = idx-pid-{mut}-{HMAC(read_key, "sg-vault-v1:file-id:path-index:{vault_id}:{path}")[:12]}`, stored at `bare/indexes/{id}`, encrypted with a **random IV** (it is mutable, not CAS-deduped), holding either the record value (small hot records) or a blob pointer (large files), **plus the commit position it reflects**. It is built at **push** time from the tree that is becoming the new named head, uploaded **after** content and the ref-CAS (content first, index last), and maintained as an **invariant of the writing interface**, never a convention. There is one cross-cutting reality the brief understates: **the write-side maintenance is sgit's (this repo), but the read-side one-request fast path is mostly the SG/Send API/browser's** — the same client/server split as the 6-Aug security advisory. Both halves must derive the identifier identically (byte-for-byte interop).

---

## 1. How it maps onto the existing code (the gap is narrow)

| Brief claim | Reality in code | Verdict |
|---|---|---|
| Four-segment IDs; `idx` = denormalised cache; `pid` = keyed hash | `Vault__Crypto.derive_file_id()` = `HMAC(read_key, domain)[:12]`; `derive_branch_index_file_id` domain `sg-vault-v1:file-id:branch-index:{vault_id}` → `idx-pid-muw-{hex}` (`Vault__Crypto.py:65-79,73-75`) | ✅ exact |
| Batch endpoint: write, match-on-write, delete | `Vault__Batch` builds `write` / `write-if-match` (+`match` hash) / `delete` ops; `execute_batch` → `api.batch()` (`Vault__Batch.py:59-101,189-241`); delete via `api.delete` (`Vault__Batch.py:261-263`) | ✅ no change needed |
| Batching collapses breadth not depth | Read path is `Vault__Sub_Tree.flatten()` recursing tree→subtree→blob (`Vault__Sub_Tree.py:83-109`); BFS walk downloads one level per round trip (`Vault__Graph_Walk.py:7-33`) | ✅ exactly the cost model |
| Deterministic IDs already used for refs/branch-index/head/commit-log | `derive_ref_file_id`, `derive_branch_index_file_id`, `derive_branch_ref_file_id` (`Vault__Crypto.py:69-79`) | ✅ same family |
| Mutable objects stored at fixed derived locations | Refs at `bare/refs/{ref-pid-muw-…}`, branch index at `bare/indexes/{idx-pid-muw-…}` (`Vault__Sync__Push.py:477,484`) | ✅ per-path index joins this shelf |
| Content-first ordering exists | Push writes blobs (Phase A) then commits/trees, then the ref via **WRITE_IF_MATCH last** (`Vault__Sync__Push.py:169-273`; `Vault__Batch.py:89-101`) | ✅ index appends after |

**The gap:** (a) a new domain string + derivation helper, (b) an index object schema, (c) a build+upload step at push after the ref-CAS, (d) delete/rename/repair handling, (e) a declared-paths manifest, (f) an optional reader fast-path. Everything else is reuse.

---

## 2. The eight decisions (recommendations)

**D1 — Domain string.** Follow the convention, path included:
`sg-vault-v1:file-id:path-index:{vault_id}:{path}` → `idx-pid-{mut}-{HMAC(read_key,…)[:12]}` at `bare/indexes/{id}`. One index per file; no registry; client-computable. *(Note the mutability label is **not** hashed — it's an output label, mirroring `idx-pid-muw-`; see D3/§4 for the reader consequence.)*

**D2 — Value vs pointer, threshold.**

| Case | Index holds | Reads |
|---|---|---|
| Small hot record (≤ **4 KB**, tunable) | the record value | 1 |
| Large file (> threshold) | `blob_id` pointer | 2 |
| Both | also the reflected `commit_id` | — |

Threshold rationale: a pointer costs a whole extra round trip to fetch something ~30 bytes; below a few KB the value-in-index always wins. 4 KB is a safe default well under the 4 MB batch budget (`Vault__Sub_Tree.py:7`); make it a manifest field so it's per-pattern tunable.

**D3 — Default mutability.** `snw` (single-writer) for the records driving this — "the writing interface is the only thing that updates them" — buying short-lived server caching for hot reads. `muw` only when genuinely multi-writer; then writes use WRITE_IF_MATCH with the prior object hash (the CAS path already exists, `Vault__Batch.py:96-100`). Declare mutability **per path/pattern in the manifest** so both writer and reader agree.

**D4 — Write sequence (write it down).** `blobs → sub-trees → root tree → commit(s) → named ref (WRITE_IF_MATCH) → **per-path indexes**`. Indexes go in a **separate batch after the ref-CAS succeeds**, so a lost CAS never leaves stale indexes and the atomic branch advance is untouched (`Vault__Sync__Push.py:263-273` is the seam — index phase is inserted right after line 273's ref write).

**D5 — Delete / rename.** §5.

**D6 — Repair.** §5, and it ships in v1.

**D7 — Declared paths.** §6 — a tracked manifest of glob patterns; indexed is opt-in per path/pattern.

**D8 — Where it lives.** In the **write path** (push), as an invariant of the same code that advances the ref — never a convention (§7).

---

## 3. The index object schema

New `Schema__Path_Index` (Type_Safe, round-trip-tested per project rules), encrypted with **random IV** via `crypto.encrypt` (mutable object — must NOT use `encrypt_deterministic`, which is only for immutable CAS-deduped trees, `Vault__Sub_Tree.py:213-217`):

```
schema        : "path_index_v1"
path          : the indexed path            # stored (encrypted) for collision-safety — see §8
commit_id     : the named-branch commit this reflects   # staleness + cheap repair
kind          : "value" | "pointer"
content_type  : str
size          : int
# kind == value:
value_b64     : the record bytes
# kind == pointer:
blob_id       : obj-cas-imm-…
content_hash  : the plaintext hash (already computed at build, Vault__Sub_Tree.py:142)
```

`path` is stored so a reader can verify it matches after a computed read: the derived id is a 48-bit HMAC truncation (`Vault__Crypto.py:66-67`), so two paths *could* collide; on mismatch the reader falls back to the tree walk. (This is the same 48-bit truncation flagged as F5 in the 6-Aug security review; storing+verifying the path is the pragmatic guard, and widening the derivation later fixes it globally.)

---

## 4. Read protocol (the one-request payoff — mostly SG/Send/browser)

To read a known path P (reader holds read_key, knows vault_id and P's declared mutability):

1. Compute `idx_id` locally (no request).
2. **One batch read** of `{ref-pid-muw-… , idx_id}` together — breadth, not depth, so still one round trip (`api.batch_read`, as used in clone, `Vault__Sync__Clone.py`).
3. Decrypt the index:
   - **hit + `path` matches + `commit_id == ref's commit`** → fresh: use `value` (done, 1 RT) or fetch `blob_id` (2 RTs).
   - **hit but `commit_id` older than ref** → index lags: use it opportunistically *or* fall back to a tree walk from the ref for strong freshness (caller's choice, per the platform's stated tolerance for lag).
   - **miss (404) or `path` mismatch** → not indexed / collision → fall back to `Vault__Sub_Tree.flatten`-style walk.

Fetching the ref in the same batch is what makes staleness *measurable at read time* for free. Readers that don't care about freshness skip the ref and read only `idx_id`.

---

## 5. Delete, rename, repair

**Delete.** Removing a tracked indexed path must emit a `delete` op for its `idx_id` in the post-ref index batch (`Enum__Batch_Op.DELETE`, already supported `Vault__Batch.py:261-263`). A stale index outliving its file returns content the vault no longer has — worse than no index.

**Rename.** Under snapshot semantics a rename is indistinguishable from delete-old + create-new (there is no rename op; `Vault__Sub_Tree` rebuilds trees from the working set). So it is naturally **`delete old_idx_id` + `write new_idx_id`** — two index ops, derived from the old and new paths. No special rename handling is needed *provided* the index-maintenance step diffs the previous indexed set against the current one (see §7) rather than only processing additions.

**Repair.** A pass that walks the named-branch tree once (`flatten`), and for each declared indexed path compares the current record against its index:
- The recorded `commit_id` makes most checks free: if the index's `commit_id == named head`, it is current — no content read.
- Divergences are re-written; orphan indexes (no matching tracked path) are deleted.
Runs **on demand** (`sgit index repair`) and **scheduled** (server-side sweep, SG/Send). Ships in v1 — divergence is silent by nature, so the recovery path must exist before the first divergence, not after.

---

## 6. Declared-paths manifest (opt-in, visible)

Indexing is a permanent per-write cost, so it must be **declared, not universal**. Add a tracked manifest — mirror `Vault__Ignore`'s `.gitignore` handling (`Vault__Ignore`, glob patterns) — e.g. a vault-root `.sgit/indexed` listing patterns with per-pattern `{mutability, value|pointer, threshold}`. It is snapshotted like any file, so it versions with the vault and its history is auditable.

- **Writers** read the manifest at push to know which paths to maintain (and to diff old-vs-new indexed sets for delete/rename).
- **Readers** that know a path is indexed by app convention (the hot-record cases: a page, a key record) need *not* read the manifest — they compute the id and try the read, falling back on miss. Readers that don't know can read a manifest-index (the manifest exposed at its own fixed per-path index) once and cache it.

---

## 7. Write-side maintenance = an invariant, not a convention

Insert an **index-maintenance phase** in `Vault__Sync__Push.push` immediately after the ref advances (`Vault__Sync__Push.py:272-273`). The same code that advanced the named ref computes and uploads the indexes, so "the write succeeded ⇒ the indexes moved" holds by construction. Concretely:

1. Load the declared manifest for the commit being pushed.
2. `flatten(clone_commit.tree_id)` (already computed at `Vault__Sync__Push.py:141`) → current record set for matched patterns.
3. Diff against the **previous** indexed set (recoverable from the prior named commit's tree, or from a small locally-cached index-manifest state) → `{to_write, to_delete}`.
4. Build a second batch: `write` (snw) / `write-if-match` (muw) for `to_write`, `delete` for `to_delete`.
5. Execute after the ref-CAS batch. Failure here is **safe and self-healing**: content and ref are already durable, indexes simply lag until the next push or a repair pass — never point at nothing.

Do **not** model this as a workflow step: anything expressible as an omissible step can be omitted, and a skipped index is silent, permanent, and undetectable. Keep it below that layer, in the push code itself.

*(For value-holding indexes the same "cache never leads" rule applies trivially — the source-of-truth blob/tree is written in Phase A/B before the index batch.)*

---

## 8. Crypto / security notes

- **Random IV, not deterministic.** Index objects are mutable; use `crypto.encrypt` (random IV, `Vault__Crypto.py:199-204`), never `encrypt_deterministic`. Deterministic IV would leak value-equality across paths/updates and is meant only for immutable CAS trees.
- **48-bit id collision (review F5).** Two paths can share an `idx_id`. Mitigated by storing+verifying `path` inside the object (§3); a future widening of `derive_file_id` beyond 48 bits removes it structurally. Worth doing alongside the review's F5.
- **Accepted leak (on record 4 Aug).** A derived id discloses *that an object exists at a path-derived location and how often it changes* — never the data. Confirmed acceptable; restated here because per-path indexes multiply these locations (one per indexed path vs one per vault). Keep the indexed set small and deliberate.
- **Interop is binding.** Writer (sgit), reader (SG/Send browser/API), and any server helper must derive the identical `idx_id` and parse the identical object. Per CLAUDE.md's byte-for-byte rule, ship **shared HMAC + schema test vectors** across all three runtimes as the definition of done.

---

## 9. Ownership split (this is not only sgit's)

| Half | Owner | Work |
|---|---|---|
| Write-side index maintenance on push | **sgit (this repo)** | §3–§7: derivation helper, schema, push phase, delete/rename, repair, manifest |
| Read-side one-request fast path | **SG/Send API + browser** (the vault read/write API) | §4: compute id, batched `{ref, idx}` read, decrypt, verify, fall back |
| If the API also *writes* vaults | **SG/Send API** | must implement the same §7 invariant, or indexes it writes go stale silently |
| Shared derivation + schema test vectors | **joint** | §8 interop |

This mirrors the 6-Aug simple-token advisory: the CLI owns its half; the identifier scheme and the read/write API are shared and must not diverge. Flag to the SG/Send team that **a writer that skips index maintenance produces silent, permanent staleness** — the exact failure §7 is designed to prevent — so if their API writes vaults, the invariant must live there too.

---

## 10. Phased implementation plan

**Phase 1 — Derivation + schema (small, no behaviour change).**
`Vault__Crypto.derive_path_index_file_id(read_key, vault_id, path)`; `Schema__Path_Index` (+ round-trip test); shared test vectors. *Ships nothing user-visible; unblocks both halves.*

**Phase 2 — Write-side maintenance (sgit).**
Manifest reader (`.sgit/indexed`); index-build from `flatten`; the post-ref push phase with diff→{write,delete}; `sgit index status`. Tests: push writes/updates/deletes indexes; failure after ref leaves content intact and indexes merely stale.

**Phase 3 — Repair (sgit).**
`sgit index repair` (on-demand) using recorded `commit_id` for cheap comparison; orphan cleanup. Tests: corrupt/delete an index → repair reconstructs; measure rebuild time at realistic vault sizes (it is the recovery path — measure, don't assume).

**Phase 4 — Read fast-path.**
Optional in sgit (`sgit cat`/`fetch <path>` fast path); **primary deliverable for SG/Send** (browser/API). Batched `{ref, idx}` read, verify, fall back. Interop vectors asserted in all runtimes.

**Phase 5 — Hardening.**
Widen `derive_file_id` past 48 bits (review F5) so path-verification becomes belt-and-suspenders; scheduled server-side repair sweep (SG/Send).

Dependency: 1 → {2 → 3, 4}; 5 independent. Phases 2/3 are shippable in sgit without waiting on SG/Send; Phase 4's value lands when SG/Send consumes it.

---

## 11. Open questions — resolved / remaining

| Question | Recommendation |
|---|---|
| Value/pointer threshold | 4 KB default, per-pattern override in manifest |
| Default mutability | `snw` (single-writer hot records); `muw` opt-in with CAS |
| Rename under snapshot semantics | Not distinguishable — falls out as delete-old + write-new via the §7 diff; no special case |
| Repair frequency/cost | On-demand always; server sweep periodic; recorded `commit_id` makes most checks read-free — measure the walk in Phase 3 |
| How/who declares indexed paths | Tracked `.sgit/indexed` manifest, glob patterns, opt-in, versioned |
| Batch endpoint changes | **None** — ordinary reads/writes/deletes of computable ids (`Vault__Batch` already covers it) |
| Rebuild time at realistic sizes | Open — **measure in Phase 3**; it is the recovery SLA |
| **New:** does the SG/Send API write vaults? | If yes, the §7 invariant must live there too (else silent staleness) — confirm with that team |

---

## 12. Honest tensions (carried from the brief, with the design's answer)

| Tension | Design answer |
|---|---|
| Write amplification | Declared-only (§6) keeps cost proportional; diff-based maintenance touches only changed paths |
| Value-in-index duplicates content | Bounded by the 4 KB threshold; rebuildable from the tree (§5 repair); never authoritative (§3 stores only recomputable fields + `commit_id`) |
| snw caching wrong once a 2nd writer appears | Mutability is a declared manifest field; changing it re-labels the id — treat as a migration, not a silent flip |
| Stale reads | Read protocol surfaces staleness for free via the batched ref (§4); platform already tolerates lag |
| Repair designed late | It is in v1 (Phase 3), not after the first incident |
| Deterministic ids disclose existence/frequency | Accepted (4 Aug); minimised by keeping the indexed set small (§6) and random-IV values (§8) |

---

*Not a new subsystem, not a staging area, not authoritative, not always a pointer, not universal — exactly as the brief frames it. The write-side is implementable in this repo behind Phases 1–3; the read-side one-request win is realised when SG/Send consumes the shared derivation. Interop test vectors are the contract between the two.*
