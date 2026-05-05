# Brief B06 — Layer Cleanup (combined)

**Owner:** **Architect** (decisions) + **Villager Dev** (mechanical moves)
**Status:** Ready. Combines v0.12.x B16 + B17 + B20 (Graph_Walk extraction).
**Estimated effort:** ~2 days
**Touches:** `sgit_ai/crypto/`, `sgit_ai/network/transfer/`, `sgit_ai/storage/`, new `sgit_ai/storage/graph/Vault__Graph_Walk.py`, layer-import test.

---

## Why this brief exists

Three cleanup items from the v0.12.x sprint, all small enough to combine:

1. **Vault__Crypto → network dep** (was B16): `Vault__Crypto.py:100,111` imports `Simple_Token` from `sgit_ai.network.transfer`. Layer rule says crypto depends on nothing. Tracked as known violation but it's a real architectural smell.
2. **Vault__Transfer mis-located** (was B17): 320 LOC in `network/transfer/` but imports 6 storage classes. Whole file should move to `core/actions/transfer/`. Eliminates 6 known-violation entries.
3. **Vault__Graph_Walk extraction** (was B20 / B23 carry-forward): BFS commit/tree/blob walk duplicated across `Workflow__Clone.Step__Clone__Walk_Trees`, `Workflow__Pull.Step__Pull__Fetch_Missing`, and `Vault__Sync__Pull._fetch_missing_objects`. Extract to a single class.

---

## Required reading

1. This brief.
2. `team/villager/v0.12.x__perf-brief-pack/00c__opus-mid-sprint-review.md` §2.1 (known violations) + §2.7 (B23 not folded in).
3. `tests/unit/architecture/test_Layer_Imports.py` — see `KNOWN_VIOLATIONS` set.
4. The three locations BFS lives:
   - `sgit_ai/workflow/clone/Step__Clone__Walk_Trees.py`
   - `sgit_ai/workflow/pull/Step__Pull__Fetch_Missing.py`
   - `sgit_ai/core/actions/pull/Vault__Sync__Pull.py` `_fetch_missing_objects`

---

## Scope

### Cleanup 1 — Vault__Crypto → network dep

**Diagnosis:** `Vault__Crypto.is_simple_token()` and `Vault__Crypto.simple_token_to_keys()` use `Simple_Token` from `network.transfer.Simple_Token`. The token format is mostly a crypto primitive (it's a deterministic-derivation scheme), so it logically belongs in `crypto/`.

**Fix:** Move `Simple_Token` and `Simple_Token__Wordlist` from `sgit_ai/network/transfer/` to `sgit_ai/crypto/simple_token/`. Update imports.

`Vault__Transfer` currently also imports `Simple_Token` from network.transfer. After the move, it imports from `crypto.simple_token` — which is fine because Vault__Transfer is moving anyway (Cleanup 2 below).

**Update:** Remove the corresponding entry from `KNOWN_VIOLATIONS` in the layer-import test.

### Cleanup 2 — Relocate Vault__Transfer

**Move:** `sgit_ai/network/transfer/Vault__Transfer.py` → `sgit_ai/core/actions/transfer/Vault__Transfer.py`.
Use `git mv` to preserve history.

**Update imports:**
- `Vault__Transfer` now imports from storage cleanly (it's in core, which is allowed).
- CLI handlers that invoke `Vault__Transfer` get their import paths updated.
- Any `Simple_Token` imports inside `Vault__Transfer.py` come from `crypto.simple_token` post-Cleanup 1.

**Update layer-import test:** Remove the 6 `Vault__Transfer` entries from `KNOWN_VIOLATIONS`.

### Cleanup 3 — `Vault__Graph_Walk` extraction

**Why now:** B23 carry-forward; flagged in Opus review as preventing duplication tripling once B08 eventually lands. Now is also right because we just shipped 3 BFS implementations.

**New class:** `sgit_ai/storage/graph/Vault__Graph_Walk.py` (Type_Safe class).

```python
class Vault__Graph_Walk(Type_Safe):
    obj_store     : Vault__Object_Store = None
    read_key      : bytes = None
    stop_at       : list = None              # commit IDs where BFS stops
    include_blobs : bool = True
    on_commit     : Optional_Callable = None # (commit_id, commit_obj) -> None
    on_tree       : Optional_Callable = None # (tree_id) -> None
    on_blob       : Optional_Callable = None # (blob_id, is_large) -> None
    on_progress   : Optional_Callable = None # (phase, msg, detail) -> None

    def walk(self, start_commit_ids: list) -> dict:
        """BFS from start_commit_ids. Returns {n_commits, n_trees, n_blobs, bytes_downloaded}."""
```

**Refactor the three call sites** to use it:
1. `Step__Clone__Walk_Trees` — wraps `Vault__Graph_Walk` for the clone path.
2. `Step__Pull__Fetch_Missing` — same with pull-specific `stop_at` config.
3. `Vault__Sync__Pull._fetch_missing_objects` — refactor to delegate to the same class (until B04 wires the workflow, which removes the duplication entirely).

**Tests:**
- Unit tests for `Vault__Graph_Walk` (single commit / single blob, stop_at boundary, sparse-skip-blobs, callbacks fire).
- Existing tests for the 3 call sites pass without modification.

---

## Hard rules

- **Type_Safe** for the new class.
- **`git mv` for relocations** to preserve history.
- **Layer-import test stays green.** Two `KNOWN_VIOLATIONS` entries removed (Vault__Crypto + Vault__Transfer block).
- **No mocks.**
- **Coverage must not regress.**
- **Suite passes** at every commit boundary.

---

## Acceptance criteria

- [ ] `Simple_Token` lives at `sgit_ai/crypto/simple_token/`.
- [ ] `Vault__Transfer.py` lives at `sgit_ai/core/actions/transfer/`.
- [ ] `Vault__Graph_Walk` exists at `sgit_ai/storage/graph/`.
- [ ] All 3 BFS call sites delegate to `Vault__Graph_Walk`.
- [ ] `KNOWN_VIOLATIONS` is reduced by 7 entries (1 crypto + 6 Vault__Transfer).
- [ ] At least 6 new tests for `Vault__Graph_Walk`.
- [ ] Suite ≥ 3,068 + ~6 passing.
- [ ] Coverage delta non-negative.

---

## When done

Return a ≤ 250-word summary:
1. Cleanup 1 / 2 / 3 outcomes.
2. KNOWN_VIOLATIONS count before / after.
3. LOC removed via Graph_Walk extraction (sum across the 3 call sites).
4. Coverage + test count delta.
