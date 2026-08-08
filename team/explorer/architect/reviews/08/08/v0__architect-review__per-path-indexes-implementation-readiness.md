# Architect Review — Per-Path Indexes: Implementation Readiness

**Version:** v0 (repo `sgit_ai/_version.py == v0.1.0`)
**Date:** 2026-08-08
**Role:** Architect (Explorer)
**Scope:** Readiness assessment of branch `claude/setup-architect-agent-RskQe` (commits `0cf8c80..9ba5af7`) — the per-path-index design and the crypto/simple-token security stream — against the live codebase on `dev`. Determines whether the work is ready to leave the architecture phase and enter implementation.

**Inputs (reviewed docs, on branch `claude/setup-architect-agent-RskQe`):**
- `team/explorer/architect/contracts/08/06/v0__architecture__per-path-indexes.md`
- `team/explorer/architect/contracts/08/06/v0.1__architecture__index-and-cache-modes.md`
- `team/explorer/architect/contracts/08/06/v0.2__architecture__mixed-version-compatibility.md`
- `team/explorer/architect/reviews/08/06/v0__security-review__crypto-entropy-simple-tokens.md`
- `team/explorer/architect/contracts/08/06/v0__advisory__sg-send-api__simple-token-security.md`
- `pyproject.toml`, `requirements-test.txt` (osbot-utils `3.70.0 → 3.75.0`)

**Inputs (live code verified, on `dev`):**
- `sgit_ai/crypto/Vault__Crypto.py:26-83,141-176,199-213`; `sgit_ai/crypto/simple_token/Simple_Token.py:9-51`; `Simple_Token__Wordlist.py` (356 words)
- `sgit_ai/storage/Vault__Sub_Tree.py:25-55,83-109,135-147,162-217`; `Vault__Ref_Manager.py:16-70`; `Vault__Branch_Manager.py:76-104`
- `sgit_ai/core/actions/push/Vault__Sync__Push.py:23-282,455-500`; `Vault__Batch.py:59-101,189-265`
- `sgit_ai/objects/Vault__Inspector.py:518-560`
- `sgit_ai/core/Vault__Ignore.py:5-31`; `sgit_ai/storage/Vault__Storage.py:6-15`
- `sgit_ai/schemas/Schema__Object_Tree_Entry.py`; `Schema__Branch_Index.py`; `Schema__Local_Config.py`
- `sgit_ai/network/api/Vault__API.py:45-115`
- Empirical: `Schema__Object_Tree_Entry.from_json({... "index_mode":"cache"}).json()` drops the unknown key and serialises every `None` field (reproduced with `osbot-utils` 3.75).

**Related reviews:**
- `team/explorer/architect/contracts/06/08/v0__contract__branch-index-wire-format.md` (the contract-with-fixtures precedent this review measures against)
- `team/explorer/architect/reviews/06/13/v0__architect-review__cli-simple-token-disablement.md` (the disablement the security stream builds on)
- `team/explorer/architect/reviews/06/04/v0.1.0__architect-review__read-only-clone-contract.md` (`bare/indexes/` storage-layout reference)

---

## 0. Executive Summary

The design is well-grounded. Every mechanism the per-path-index docs rely on was verified against live code, including the central non-breaking claim (an in-tree-entry declaration field would re-ID every tree — reproduced empirically). The Index-vs-Cache split and the manifest-as-tracked-file decision are correct and materially improve on the v0 framing. The security-stream review is accurate to the byte (30.2-bit tokens, the `transfer_id` fast-hash oracle, the fixed global salt).

It is **not yet ready to green-light as a single implementation push.** Three gating gaps remain, all in the Architect's own domain (storage layout, interop contract): a namespace collision between per-path indexes and the branch index, a declared-paths manifest location that is not reconciled against the real ignore rules, and the absence of a signed wire-format contract with interop test vectors — the team's own definition of "ready" (see the branch-index contract precedent).

**Verdict: CONDITIONAL GO. Approve Phase 1 (derivation helper + index/cache schemas + shared test vectors) now; gate Phases 2–4 on F1 + F2 + F6 below.** The security stream is accurate and is an SG/Send-owned workstream; the CLI half is already shipped. Recommend it be split from the feature branch.

---

## 1. Findings

| # | Severity | Finding | Location |
|---|---|---|---|
| F1 | HIGH | Per-path index ids collide with the branch-index namespace; `_resolve_head` can load a path index as the branch index | `Vault__Inspector.py:544-547`; per-path-indexes §D1/§2 |
| F2 | MEDIUM | Declared-paths manifest at `.sgit/indexed` is not reconciled with the real `.sg_vault/` ignore rules | index-and-cache-modes §6; `Vault__Ignore.py:5-31`, `Vault__Storage.py:6` |
| F3 | LOW | Push seam citation points at a local ref write, not the remote ref-CAS | per-path-indexes §D4/§7; `Vault__Sync__Push.py:265` vs `:273` |
| F4 | IMPORTANT | Normal push does not upload any index today; per-path indexes are a new per-push server-write obligation, not "joining an existing shelf" | `Vault__Sync__Push.py:232-273,455-500` |
| F5 | MEDIUM | Reconcile/repair leans on `flatten()`, which is uncached and re-run every commit/status/push/pull; rebuild cost is the unmeasured SLA | `Vault__Sub_Tree.py:83-109`; per-path-indexes §10 Phase 3 |
| F6 | IMPORTANT | No interop test vectors and no signed wire-format contract for the new objects/domain — the stated Phase 1 definition-of-done is unmet | per-path-indexes §8; cf. branch-index contract §4.3/§10 |
| F7 | LOW | Originating dev-brief `v0.33.56__devbrief__sgit-per-path-indexes` is not committed; the decision trail has a gap | doc headers |
| F8 | MEDIUM | New schemas must use `Safe_*` types + round-trip tests; the existing `bool` fields are a pre-existing violation, not a precedent | CLAUDE.md §1/§6; `Schema__Object_Tree_Entry.py:13` |
| F9 | ADVISORY | Two independent workstreams (feature + security advisory) are bundled on one branch | branch contents |

---

## 2. Finding detail

### F1 — HIGH: per-path index ids collide with the branch-index namespace

**Evidence.** The design places per-path indexes at `bare/indexes/{idx-pid-{mut}-<hmac>}` (per-path-indexes §D1), the same directory and the same `idx-pid-muw-` prefix family as the branch index (`Vault__Crypto.py:73-75,89`). HEAD resolution scans that directory and takes the *first* matching file:

```python
# Vault__Inspector.py:542-547
indexes_dir = storage.bare_indexes_dir(directory)
if os.path.isdir(indexes_dir):
    for name in sorted(os.listdir(indexes_dir)):
        if name.startswith('idx-pid-muw-'):
            index_id = name
            break
```

`save_branch_index` also defaults to a random `idx-pid-muw-<token_hex(6)>` when no id is passed (`Vault__Branch_Manager.py:78-79`), so a stray `idx-pid-muw-*` file already mis-resolves HEAD today.

**Risk.** A per-path index declared with `muw` mutability (the design's opt-in multi-writer mode) whose 12-hex tail sorts before the branch-index tail will be loaded by `_resolve_head` and parsed as a `Schema__Branch_Index` — yielding the wrong HEAD or a hard parse failure in `sgit inspect`. The default `snw` mode avoids this by producing `idx-pid-snw-*`, but the design permits `muw`, so the hazard is real and silent.

**Recommendation.**
- (a) *(preferred)* Give per-path indexes a distinct prefix (e.g. `pidx-pid-…`) and/or a distinct subdirectory (`bare/path-indexes/`), keeping `bare/indexes/` reserved for the single branch index.
- (b) Make `_resolve_head` derive the branch-index id deterministically (`derive_branch_index_file_id`) instead of scanning — fixes the pre-existing stray-file bug too.
- Do both; (b) is worth doing regardless of this feature.

### F2 — MEDIUM: manifest location not reconciled with the real ignore rules

**Evidence.** The manifest is proposed at vault-root `.sgit/indexed` (index-and-cache-modes §6). The internal directory is `.sg_vault/`, and only `.sg_vault*` is always-ignored (`Vault__Ignore.py:5`, `Vault__Storage.py:6`). The self-healing argument (v0.2 §3) *requires* the manifest to be tracked content that old clients snapshot — i.e. it must live outside `.sg_vault/`.

**Risk.** `.sgit/` is not in `ALWAYS_IGNORED_DIRS`, so it happens to be tracked — but the name is one character from the always-ignored `.sg_vault_*` family and is undocumented against the ignore rules. A future ignore-list edit, or a reader assuming `.sgit/` mirrors `.sg_vault/`, silently breaks the "declaration survives foreign writes" property the whole compatibility analysis rests on.

**Recommendation.** Pin the manifest to an explicitly tracked, clearly-named path and state in the contract why it is tracked (i.e. that it is ordinary working-tree content, not `.sg_vault/` internal state). Add a test asserting the manifest is *not* matched by `Vault__Ignore`.

### F3 — LOW: push seam citation is off by the local/remote boundary

**Evidence.** The docs say to insert the index phase "right after line 273's ref write" (per-path-indexes §7). `Vault__Sync__Push.py:273` is `ref_manager.write_ref(...)`, a *local* disk write (`Vault__Ref_Manager.py:16-26`). The remote ref-CAS completes inside the batch at `:265` (`execute_batch` → `WRITE_IF_MATCH` last, `Vault__Batch.py:96-101`).

**Risk.** None to the design intent (indexes after remote content + ref are durable, which is correct). The line pointer would place a developer's insertion after a purely local write, not after the remote CAS.

**Recommendation.** Restate the seam as "after the Phase B batch (`:265`) succeeds," and note the ref durability is established by the batch, not by `write_ref`.

### F4 — IMPORTANT: per-path indexes are a new per-push write obligation

**Evidence.** A steady-state push writes only `bare/refs/{named_ref_id}` plus `bare/data/*` objects (`Vault__Sync__Push.py:232-273`). The branch index reaches the server **only** via the one-shot `_register_pending_branch` after clone and on first push (`:455-500`) — it is not maintained per-push.

**Risk.** The framing "the per-path index joins this shelf" (per-path-indexes §1) implies the write path already maintains indexes on every push; it does not. The feature introduces a genuinely new per-push upload + delete obligation, which changes the write-amplification and effort estimates.

**Recommendation.** State the obligation explicitly in the contract, and fold the index/cache batch into `Schema__Push_State` resumability (a `commits_zipped`/`indexes_written` list) so a crash mid-index-phase resumes rather than silently re-runs.

### F5 — MEDIUM: reconcile/repair cost is the unmeasured SLA

**Evidence.** `flatten()` is recursive, uncached, and re-run from scratch on every commit, status, push and pull (`Vault__Sub_Tree.py:83-109`), decrypting every tree object and every `_enc` field per call. The design's "reconcile every declared path against the new head" (v0.2 §4) and the repair pass (v0 §5, §10 Phase 3) both depend on this being cheap.

**Risk.** On large vaults the reconcile/repair walk is the recovery SLA and is currently unquantified. The design correctly lists it as "measure the walk," but it is the one open number that gates whether repair is on-demand-only or must be incremental.

**Recommendation.** Keep the Phase 3 measurement as a hard gate. Consider a `commit_id`-keyed local flat-map cache in `.sg_vault/local/` (invalidation is trivial — tree ids are content-addressed) as the shared fix for both reconcile cost and the repeated `flatten()` calls across commit/status/push.

### F6 — IMPORTANT: interop contract and test vectors are missing

**Evidence.** CLAUDE.md makes byte-for-byte CLI/browser/server interop with shared test vectors the definition of done. The precedent, `contracts/06/08/v0__contract__branch-index-wire-format.md`, ships reference fixtures (Fixture A/B) and a concrete `vault_id "7y6uk6gj" → index_file_id "idx-pid-muw-b69ec449a18c"` vector, with RFC-2119 field tables and a change-control section. The per-path docs describe this deliverable (per-path-indexes §8, Phase 1) but the branch ships no fixtures, no vectors, and no signed contract.

**Risk.** Phase 1's own stated definition-of-done is unmet. Building the write side before the derivation domain and object schemas are pinned as a contract risks the CLI and SG/Send diverging on `idx_id` derivation — the exact interop failure the security advisory warns about for tokens.

**Recommendation.** Before Phase 2, promote the design into a wire-format contract that pins: the `path-index` domain string, the `Schema__Index` / `Schema__Cache` plaintext shape, the random-IV envelope, the storage path, and a worked `path → idx_id` vector. Answer the open questions (§4 below) with "CLI default if no reply," as the branch-index contract does.

### F7 — LOW: originating brief absent

The docs respond to `v0.33.56__devbrief__sgit-per-path-indexes` (13 Aug), which is not committed. The framing the design honours cannot be verified from the repo. Recommend committing the brief (or noting it lives elsewhere) so the decision trail is complete.

### F8 — MEDIUM: Type_Safe rules for the new schemas

`Schema__Object_Tree_Entry.large : bool` (`:13`) and `Schema__Local_Config.sparse : bool` use raw `bool`, which CLAUDE.md §1 forbids. These are pre-existing and out of scope to fix here, but they must not be treated as precedent: `Schema__Index`, `Schema__Cache`, and any manifest schema must use `Safe_*` domain types and carry a round-trip test (`from_json(x.json()).json() == x.json()`, CLAUDE.md §6).

### F9 — ADVISORY: split the branch

The per-path-index feature and the simple-token security review/advisory are independent workstreams with different owners (CLI vs SG/Send) and timelines. Bundling them on one branch/PR muddies review and couples a feature green-light to a security decision. Recommend two branches.

---

## 3. Zero-Knowledge & Crypto Interop

| Concern | Assessment | Verdict |
|---|---|---|
| Mutable index/cache objects must use random IV | Design mandates `crypto.encrypt` (random IV), never `encrypt_deterministic` (per-path-indexes §8) — correct; `encrypt_deterministic` is only for CAS trees (`Vault__Crypto.py:162-170`) | OK, must be tested |
| New derived locations multiply the existing leak | A derived id discloses that an object exists at a path-derived location and how often it changes — accepted 4 Aug. Per-path indexes multiply these (one per indexed path). Keep the indexed set small and declared | Accepted, restate in contract |
| 48-bit id collision applies to path ids | `derive_file_id` truncates to 48 bits (`Vault__Crypto.py:65-67`); two paths can collide. Design mitigates by storing+verifying `path` in the object (per-path-indexes §3/§8). Same as security-review F5 | OK with stored-path guard |
| No new server capability | Reads/writes/deletes of computable ids; `Vault__Batch` already supports `DELETE` and `WRITE_IF_MATCH`-last (`Vault__Batch.py:96-101,261-263`) | No API change — confirmed |
| Interop test vectors | Absent — see F6 | BLOCKING for Phase 1 done |

No zero-knowledge regression in the design as written, provided the random-IV rule and the stored-path collision guard are enforced by tests.

---

## 4. Open Questions (must be answered or defaulted before Phase 2)

| Question | Recommended default if no reply |
|---|---|
| Option A (side manifest) confirmed as the v1 declaration home? | Yes — A; B (in-entry hint) only as a future `tree_v2` migration |
| Value/pointer (cache/index) threshold | 4 KB, per-pattern override in the manifest |
| Default mutability | `snw`; `muw` opt-in with CAS — and see F1 (distinct namespace) |
| Does the SG/Send API *write* vaults? | If yes, the write-side reconcile invariant must live there too, or its writes go silently stale |
| Per-path index prefix/namespace (F1) | `pidx-` prefix and/or `bare/path-indexes/` subdir |
| Repair cadence + rebuild time (F5) | On-demand always; measure the walk in Phase 3 before committing to incremental |

---

## 5. Hand-Off

**To Dev (binding once F1/F2/F6 are decided):**
- Phase 1 is approved to start: `derive_path_index_file_id`, `Schema__Index` / `Schema__Cache` (Safe_* fields + round-trip tests, F8), and shared interop test vectors (F6). Ships nothing user-visible.
- Do not begin Phase 2 write-side maintenance until the namespace decision (F1) and the wire-format contract (F6) are signed.

**To Dev (recommended):**
- Fix `_resolve_head` to derive the branch-index id deterministically (F1(b)) independent of this feature.
- Add a `commit_id`-keyed flat-map cache (F5) as a shared performance fix.

**To QA (binding):**
- Interop vectors for the new domain/objects asserted in the Python suite, mirrored to browser/server per CLAUDE.md.
- A test asserting the declared-paths manifest is not matched by `Vault__Ignore` (F2), and a test asserting a `muw` path index does not shadow the branch index in `_resolve_head` (F1).

**To the SG/Send API team:** the security advisory (`v0__advisory__sg-send-api__simple-token-security.md`) is theirs to action; the CLI half (simple-token creation disablement) is shipped and verified. No further CLI implementation is required there beyond the optional C6/C7 hardening items.

**To Historian:** picks up automatically.

---

*Verified against `dev` (`sgit_ai/_version.py == v0.1.0`) and branch `claude/setup-architect-agent-RskQe` (`0cf8c80..9ba5af7`) on 2026-08-08. Every code reference above was read directly; the Type_Safe field-drop behaviour was reproduced empirically with osbot-utils 3.75.*
