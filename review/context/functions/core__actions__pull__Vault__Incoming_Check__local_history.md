## `local_history` in sgit_ai/core/actions/pull/Vault__Incoming_Check.py (L55-L74)

**Purpose:** The set of every commit reachable from `head` whose object is in the local store — "what this clone already holds". It is the `stop_at` frontier for `verify_chain`, so it decides which commits the policy is *not* applied to.

**Inputs & Assumptions:**
- `c`, `read_key`: trusted.
- `head` (str): the held head (clone-branch ref or accepted baseline). Trust: trusted (local).
- Implicit: object store; `c.obj_store.crypto` (L62) rather than `self.crypto` — same object in practice (`_init_components` L376 builds the store with `self.crypto`).

**Outputs & Effects:**
- Returns a `set` of ids. No writes. Never raises past L72-L73 except for `obj_store.exists` itself.

**Block-by-Block:**

```python
# L63-L73
seen  = set()
queue = [head] if head else []
while queue:
    cid = queue.pop()
    if not cid or cid in seen or not c.obj_store.exists(cid):
        continue
    seen.add(cid)
    try:
        queue.extend(str(p) for p in (vc.load_commit(cid, read_key).parents or []) if str(p))
    except Exception:
        continue
```
- **What:** DFS over local commits; absent objects are skipped (not added), unreadable commits are added but not expanded.
- **Why here:** All parents are followed (docstring L56-L59) so that an ancestor-remote-head or a divergent merge base counts as held.
- **Assumes:** that every commit object in the local store that is reachable from the held head was accepted under the policy at the time (or predates it). Objects enter the store from: verified downloads during pull/clone/status/switch, and this clone's own commits. `_fetch_commit_chain` (called by `sgit status`) writes commit objects for *unaccepted* heads too (`Vault__Sync__Status.py:L304`) — but those are not reachable from the held head until a head is accepted, so they do not enter this set. The N3 tests (`test_N3__status_writes_no_ref`, `test_N3__status_between_read_only_pulls_does_not_get_past_the_policy`) establish exactly that status does not move the held head.
- **Establishes:** `seen` ⊆ local objects; `head ∈ seen` when it is local.
- **Depended on by:** `require_signatures` L33-L36.

**Cross-Function Dependencies:**
- Callee `Vault__Object_Store.exists` (internal, L93-L94): `isfile(join(vault_path, 'bare/data', id))`.
- Callee `Vault__Commit.load_commit` (internal): decrypt + parse; exceptions swallowed here.
- Callers: `require_signatures` L33 only.
- Shared state: none written.
- Invariant coupling: unbounded walk (no limit) — on a long history this is O(history) decrypts per pull under the policy. `Vault__Ref_Guard.is_ancestor` caps at 100,000 (L21 of Ref_Guard); this does not.

**Open Questions:**
- unclear; whether an unbounded DFS over every parent is acceptable for the vault sizes in production; noted for the cost model, not for correctness.
