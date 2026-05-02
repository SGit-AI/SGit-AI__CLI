# Brief 23 — E3 + E4: BFS walk unification and blob-download deduplication

**Owner role:** Villager Dev
**Status:** Ready to execute.
**Prerequisites:** Brief 22 fully landed (v0.10.30 sub-class split complete).
**Estimated effort:** ~4 hours (E3 ~2.5 h, E4 ~1.5 h)
**Risk:** MEDIUM — both touch clone and pull paths; tests gate every commit.

---

## Why this brief exists

Brief 22 planned five extractions (E1–E5). E1, E2, and E5 were completed.
E3 and E4 were skipped. The duplication they address is still present across
the newly-split sub-classes and will grow harder to fix as the codebase evolves.

This brief closes both in one sprint. Do them in order: E3 first, then E4.
Each extraction is exactly one commit; the suite must be green before moving on.

---

## Required reading

1. This brief.
2. `team/villager/architect/v0.10.30__vault-sync-split-plan--extractions.md`
   — E3 and E4 sections (the architect design; this brief updates the file
   locations since the split moved the code).
3. `sgit_ai/sync/Vault__Sync__Clone.py` — `_clone_with_keys` (BFS walk, clone path)
4. `sgit_ai/sync/Vault__Sync__Pull.py` — `_fetch_missing_objects` (BFS walk, pull path)
5. `sgit_ai/sync/Vault__Sync__Pull.py` — `_clone_download_blobs` (blob download)
6. `sgit_ai/sync/Vault__Sync__Sparse.py` — `sparse_fetch` (blob download, duplicated)
7. `sgit_ai/objects/Vault__Object_Store.py` — where E4 method will live

---

## E3 — `Vault__Graph_Walk` (BFS unification)

### The problem

The BFS commit/tree/blob walk appears in two places:

| Location | File | Semantics |
|---|---|---|
| `_clone_with_keys` | `Vault__Sync__Clone.py` | No `stop_at`; walks full history |
| `_fetch_missing_objects` | `Vault__Sync__Pull.py` | `stop_at` boundary; optional `include_blobs` |

Both maintain `visited_commits`, `visited_trees`, and (in the pull path)
`seen_blobs` sets manually. Any bug in the traversal logic must be fixed in
two places. Adding features (e.g. progress streaming, sparse improvements) means
touching two files.

### What to build

Create `sgit_ai/sync/Vault__Graph_Walk.py` (NEW):

```python
class Vault__Graph_Walk(Type_Safe):
    obj_store     : Vault__Object_Store = None
    read_key      : bytes               = None
    stop_at       : set                          # commit IDs; BFS stops when reached
    include_blobs : bool                = True
    on_commit     : object              = None   # callable(commit_id, commit_obj) -> None
    on_tree       : object              = None   # callable(tree_id) -> None
    on_blob       : object              = None   # callable(blob_id, is_large) -> None
    on_progress   : object              = None   # callable(phase, msg, detail) -> None

    def walk(self, start_commit_ids: list) -> dict:
        """BFS from start_commit_ids. Returns {n_commits, n_trees, n_blobs}."""
```

**Note on `callable` field type:** Type_Safe validates field types at construction.
Use `object = None` (not `callable = None`) for the callback fields to avoid any
Type_Safe validation issue with the `callable` built-in. Assign after construction:
```python
walker = Vault__Graph_Walk(obj_store=..., read_key=..., stop_at=set())
walker.on_commit = my_callback
```

**`stop_at` default:** `set` is a mutable default — declare as `stop_at : set`
with no value (Type_Safe empty-collection pattern). Callers pass it explicitly.

**Visited sets:** `Vault__Graph_Walk` owns `_visited_commits`, `_visited_trees`,
`_seen_blobs` internally (private, created in `walk()`). Not Type_Safe fields —
just local variables inside `walk`.

### Callers after E3

`_clone_with_keys` becomes:
```python
walker = Vault__Graph_Walk(obj_store=obj_store, read_key=read_key, stop_at=set())
walker.on_progress = _p
stats = walker.walk([commit_id])
```

`_fetch_missing_objects` becomes:
```python
walker = Vault__Graph_Walk(obj_store=obj_store, read_key=read_key, stop_at=stop_set,
                           include_blobs=include_blobs)
walker.on_commit   = lambda cid, obj: _p('scan', 'commit', cid)  # or decrypt log line
walker.on_progress = _p
stats = walker.walk(start_commit_ids)
```

The `on_commit` callback in the pull path is where commit-message decryption for
the per-commit log line lives. Keep that logic in `_fetch_missing_objects` and
pass it in as the callback — do not put it inside `Vault__Graph_Walk`.

### Tests

New file: `tests/unit/sync/test_Vault__Graph_Walk.py`

Required tests:
- `test_walk_single_commit_single_blob` — minimal vault; walker visits all objects
- `test_walk_stop_at_respects_boundary` — two commits; stop_at first → only first visited
- `test_walk_sparse_skips_blobs` — `include_blobs=False`; `on_blob` never called
- `test_walk_callbacks_invoked` — verify `on_commit`, `on_tree`, `on_blob` each fire
- `test_walk_returns_counts` — return dict has `n_commits`, `n_trees`, `n_blobs`

Use the real `Vault__API__In_Memory` + real crypto — no mocks.

### Acceptance criteria

- [ ] `Vault__Graph_Walk` in `sgit_ai/sync/Vault__Graph_Walk.py`
- [ ] `_clone_with_keys` delegates BFS to `Vault__Graph_Walk`
- [ ] `_fetch_missing_objects` delegates BFS to `Vault__Graph_Walk`
- [ ] 5+ tests in `test_Vault__Graph_Walk.py`, all passing
- [ ] Suite ≥ 2,367 passing (current baseline)
- [ ] Clone and pull tests (existing) still pass — no behaviour change

---

## E4 — `batch_download` on `Vault__Object_Store`

### The problem

Small/large blob bucketing + download appears in two places:

| Location | File | Used by |
|---|---|---|
| `_clone_download_blobs` | `Vault__Sync__Pull.py` | `pull` and `clone` (via `_fetch_missing_objects`) |
| `sparse_fetch` | `Vault__Sync__Sparse.py` | `sparse_fetch` only |

Both bucket blobs into small (batch_read) and large (presigned URL + urlopen).
Both use a progress callback. Any change to presigned-URL handling or batch size
must be made in two files.

### What to build

Add `batch_download` to `sgit_ai/objects/Vault__Object_Store.py`:

```python
def batch_download(
    self,
    vault_id    : str,
    blob_ids    : list,       # list of bare/data/{blob_id} file-id strings
    is_large    : list,       # parallel bool list: True if large blob
    api         : object,     # Vault__API — passed per call, not stored as field
    save_fn     : object,     # callable(file_id: str, data: bytes) -> None
    on_progress : object,     # callable(done: int, total: int) -> None
) -> int:
    """Download small blobs via batch_read; large blobs via presigned URL.
    Returns total blob count downloaded."""
```

**`api` is NOT a field on `Vault__Object_Store`** — the storage layer must stay
decoupled from the API layer. Pass it per call only.

`_clone_download_blobs` and `sparse_fetch` both become thin callers of
`obj_store.batch_download(...)`, each supplying their own `save_fn` and
`on_progress` closures.

### Tests

New file: `tests/unit/objects/test_Vault__Object_Store__Download.py`

Required tests:
- `test_batch_download_small_blobs` — all small; verifies batch_read path
- `test_batch_download_returns_count` — return value equals len(blob_ids)
- `test_batch_download_calls_save_fn` — save_fn called once per blob
- `test_batch_download_progress_increments` — on_progress called for each blob
- `test_batch_download_empty_list` — zero blobs; returns 0, no errors

For the large-blob path (presigned URL + urlopen): if the in-memory API does not
support presigned URLs, skip the large-blob test with `pytest.mark.skip` and a
clear note. Do not add a mock for urlopen.

### Acceptance criteria

- [ ] `Vault__Object_Store.batch_download` implemented
- [ ] `_clone_download_blobs` in `Vault__Sync__Pull.py` uses it
- [ ] `sparse_fetch` in `Vault__Sync__Sparse.py` uses it
- [ ] 5+ tests in `test_Vault__Object_Store__Download.py`, all passing
- [ ] Suite ≥ 2,367 passing
- [ ] Pull, clone, and sparse tests (existing) still pass — no behaviour change

---

## Commit sequence

```
refactor: E3 — extract Vault__Graph_Walk; unify BFS in Clone + Pull
refactor: E4 — extract batch_download to Vault__Object_Store; dedup Pull + Sparse
```

One commit per extraction. Do not mix them.

---

## Hard rules (all briefs)

- No mocks — use real objects, `Vault__API__In_Memory`, temp directories.
- No multi-paragraph **class or method** docstrings — one line max.
  Module-level docstrings (top of file) are fine and encouraged.
- Do not modify `team/humans/dinis_cruz/claude-code-web/` — that directory
  is maintained by the Explorer agent.
- Suite must be green after every commit before moving to the next.

---

## When done

Return a summary covering:
1. `Vault__Graph_Walk` — LOC, test count, which BFS callers were updated
2. `batch_download` — LOC, test count, which download callers were updated
3. Final passing test count
4. Any large-blob test that was skipped and why
