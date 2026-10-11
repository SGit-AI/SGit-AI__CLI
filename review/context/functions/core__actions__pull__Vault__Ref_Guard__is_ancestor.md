## `is_ancestor` in sgit_ai/core/actions/pull/Vault__Ref_Guard.py (L23-L48)

**Purpose:** True when `ancestor` is reachable from `descendant` through **local** commit objects (bounded at 100,000 visits). `classify` uses it to tell a rollback (new head in our past) from an unknown lineage; `Vault__Branch_Switch.switch` uses it to decide whether a reused clone branch is strictly behind the named head (L88-L91 of Branch_Switch).

**Inputs & Assumptions:**
- `c`, `read_key`: trusted.
- `ancestor`, `descendant` (str): commit ids. In `classify` the roles are `remote_head` (semi-trusted, from the server's decrypted ref) and `last_known` (trusted baseline).
- `boundaries` (set | None): shallow boundaries, not expanded (L36-L37).
- Implicit: local object store only — nothing is fetched here.

**Outputs & Effects:** bool; no writes; exceptions from `load_commit` swallowed (L38-L41).

**Block-by-Block:**

```python
# L25-L28
if not ancestor or not descendant:
    return False
if ancestor == descendant:
    return True
```
- **What:** Edge cases. Equal ids are "ancestor" (reflexive).
- **Depended on by:** `classify` L58 (which already returned FORWARD for equality at L54-L55, so the reflexive branch is for the switch caller).

```python
# L29-L48
vc = Vault__Commit(...)
seen = set(); queue = [descendant]
while queue and len(seen) < LOCAL_WALK_LIMIT:
    cid = queue.pop()
    if cid in seen or not c.obj_store.exists(cid):
        continue
    seen.add(cid)
    if boundaries and cid in boundaries:
        continue
    try:
        commit = vc.load_commit(cid, read_key)
    except Exception:
        continue
    for p in (commit.parents or []):
        p = str(p)
        if p == ancestor:
            return True
        if p and p not in seen:
            queue.append(p)
return False
```
- **What:** DFS from `descendant`; returns True the moment `ancestor` appears as a parent.
- **Why here:** Checking parents at push time (L44-L45) rather than at pop time means `ancestor` need not be a *local* object to be found — only the child that names it must be.
- **Assumes:** that every commit on the path from `descendant` to `ancestor` is local and decryptable. A missing or undecryptable intermediate commit ends that path (`continue`), and the function returns False — "not an ancestor", which `classify` then treats as *not* a rollback. The limit (100,000) likewise yields False.
- **Establishes:** True ⇒ a local chain of parent links from `descendant` names `ancestor`. False ⇒ nothing proven.
- **Depended on by:** `classify` L58-L59; `Vault__Branch_Switch.switch` L90.

**Cross-Function Dependencies:**
- Callee `Vault__Commit.load_commit` (internal): decrypt/parse; see `status_of` record for the branch_id repair.
- Callers: `classify` (L58); `Vault__Branch_Switch.switch` (L86-L91) — a reused clone branch's head is moved to the named head only when `is_ancestor(clone_head, named_head)`; a False (including "could not tell") leaves the clone head where it was.
- Shared state: none.
- Invariant coupling: the rewind guard depends on `classify` getting a True here when the remote head is in our past; a False here on an actual rollback falls through to `connected` (L60-L61).

**Open Questions:**
- unclear; whether `boundaries` passed from `_guard_rewind` (L31-L33 of Fetch_Remote_Ref) can make a genuine rollback *below* the boundary read as REWOUND via `connected` rather than via this function — depends on `_fetch_commit_chain` reporting `connected=True` when it stops at a boundary (it does: boundaries are not expanded and do not set `connected=False`, `Vault__Sync__Status.py:L317-L318`).
