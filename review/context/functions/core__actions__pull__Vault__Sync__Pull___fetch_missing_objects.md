## `_fetch_missing_objects` in sgit_ai/core/actions/pull/Vault__Sync__Pull.py (L259-L477)

**Purpose:** BFS from `commit_id` downloading every commit, tree and blob the clone lacks, stopping at `stop_at` and at shallow boundaries. It is the pull's (and switch's) object-download path; every byte it writes goes through `Vault__Verified_Write`.

**Inputs & Assumptions:**
- `vault_id`, `commit_id` (str): the remote head. `commit_id` is semi-trusted (decrypted server ref). Trust in its *shape*: on the pull path it has passed through `Safe_Str__Commit_Id` (sanitising) in `Schema__Pull__State`; on the switch path (`Vault__Sync._fetch_branch_for_switch` L193-L198) it is the raw `json.loads(...)['commit_id']` string — used in `f'bare/data/{c}'` (L332) and then by `Verified_Write.save`, whose `STORE_FILE_ID` regex (`^bare/(data|…)/[^/]+$`, `Vault__Verified_Write.py:L18-L19`) and `Path_Guard.safe_join` (L76) contain the write. `obj_store.exists(c)` (L330) joins the raw string into a path before that — a read, `isfile`, not a write.
- `obj_store`, `read_key`, `sg_dir`: trusted.
- `stop_at` (str | None): the held head; pre-marked visited (L318-L319).
- `include_blobs` (bool): `False` on sparse clones (`Step__Pull__Fetch_Missing` L80).
- `failures` (dict | None): per-object classification out-param.
- `scope`: partial-clone scope; boundaries stop the commit walk (L353-L354).
- Implicit: `self.api` (batch_read, read, presigned_read_url, fetch_presigned).

**Outputs & Effects:**
- **Writes:** `bare/data/<id>` for commits (L332), trees (L384), blobs (L466) — all via `_save` → `Vault__Verified_Write.save` (L279-L282). A refused object is reported (`_p('warning', …)`, L284-L285), recorded in `failures` (L286-L288) and never written.
- Progress events including decrypted commit messages, truncated to 60 chars (L433-L441) — plaintext commit messages reach the progress callback/stdout.
- Returns timing/count stats.

**Block-by-Block:**

```python
# L276-L290  _save
verdict = Vault__Verified_Write(crypto=self.crypto).save(sg_dir, f'bare/data/{oid}', data, read_key=read_key)
if verdict == Vault__Verified_Write.REFUSED:
    ... failures[fid] = self.api._classify_exception(fid, RuntimeError('integrity check failed…'))
    return False
return True
```
- **What:** verify-then-write per object.
- **Assumes:** `Verified_Write.save` (L72-L88): `is_store_path` (regex + not protected) → `classify` (sha256 of ciphertext at the id's own width, `Vault__Crypto.object_id_matches` L200-L203) → `safe_join` → write. No decrypt is attempted; authenticity against the key is checked later by whoever loads the object (AES-GCM).
- **Establishes:** every object this function writes hashes to its name (threat model §5, content addressing).

```python
# L292-L311  _batch_save
results = self.api.batch_read(vault_id, fids, failures=failures)
for fid, data in results.items():
    if data:
        if _save(fid, data) and failures is not None:
            failures.pop(fid, None)
```
- **What:** The server's `fid` keys name the files written. `_save` passes `f'bare/data/{oid}'` where `oid = fid.replace('bare/data/', '')` — so a server response keyed with a file_id we did not ask for would be written under `bare/data/<that name>` **if** it hashes to it. Content addressing makes that harmless (an object that hashes to its id is that object); `is_store_path` keeps it in the store.
- **Assumes:** nothing checks `fid ∈ fids` here (contrast `Vault__Key_Fetch.fetch_missing` L45, which does). Harmless by the hash argument.

```python
# L324-L373  Phase 1: commit walk
missing_cids = [c for c in unvisited if not obj_store.exists(c)]
if missing_cids: _batch_save([f'bare/data/{c}' for c in missing_cids])
...
if obj_store.exists(pid_str) and self._commit_tree_local(vc, pid_str, read_key, obj_store):
    visited_commits.add(pid_str)
else:
    next_wave.append(pid_str)
```
- **What:** Wave-by-wave fetch of commits; a parent is treated as "complete below" only when its commit **and** its root tree are local (L359-L367, `_commit_tree_local` L252-L257) — because `status` and the rewind check download commit objects alone.
- **Assumes:** a local commit with a local root tree has all its trees and blobs (comment L359-L360: "every download path fetches commits with their trees"). `fetch_tree_lazy` (`Vault__Sync__Base.py:L598-L665`) writes a tree without going through this path — see Open Questions.
- Exceptions per commit are swallowed (L368-L369).

```python
# L375-L411  Phase 2: tree walk
seen_trees = graph_walk.walk_trees(root_tree_ids, _load_tree, _on_batch_missing)   # or Scoped_Tree.walk_fetch
```
- **What:** level-by-level tree fetch via `_batch_save`.

```python
# L413-L427  Phase 3 / L447-L477 blobs
for file_id, is_large in missing_blobs:
    if is_large:
        url_info = self.api.presigned_read_url(vault_id, file_id)
        data     = self.api.fetch_presigned(url_info['url'])
    else:
        data = self.api.read(vault_id, file_id)
    if data: _save(file_id, data)
```
- **What:** Blobs one by one; large ones via a presigned URL.
- **Assumes:** `Vault__API.fetch_presigned` (L37-L56) → `check_presigned_url` (L58-L71): https to any host, http only to loopback or the configured host; redirects re-checked (L46-L49). The downloaded bytes are still id-verified by `_save` (comment L462). `is_large` comes from the decrypted tree entry (`getattr(entry, 'large', False)`, L425) — an author's claim that only chooses the transport.

**Cross-Function Dependencies:**
- Callee `Vault__Verified_Write.save` (internal, L72-L88): read in full; see above.
- Callee `Vault__API.batch_read` / `read` / `presigned_read_url` / `fetch_presigned` (external-source-available): token headers on every request (`_auth_headers` L78-L90); redirects not followed on the pooled path (`_send` L434-L436, L466-L467).
- Callee `_classify_chunk_exception` (L218-L250): maps HTTP 404/403/other to ABSENT/FORBIDDEN/TRANSIENT for messages.
- Callers: `Step__Pull__Fetch_Missing.execute` L85 (after the policy, before `_accept`); `Vault__Sync._fetch_branch_for_switch` L196-L198 (**before** `require_signatures` L204 — objects are fetched, then the policy runs, then the ref is written; consistent since object writes are hash-verified and not "accepts").
- Shared state: `bare/data/`.
- Invariant coupling: "verify-before-write on every download path" (threat model §5). `Vault__Sync__Base.fetch_tree_lazy` (L622-L629, L645-L654) writes `bare/data/` with plain `open(...,'wb')` and no `Verified_Write`; its callers were not found by grep in `sgit_ai/` (only the definition) — recorded as an open question for the dossier, not for this function.

**Open Questions:**
- unclear; whether `fetch_tree_lazy` is reachable (no in-tree caller found with `grep -rn fetch_tree_lazy sgit_ai/`). If it is dead code, the "every download path" claim holds; if a plugin calls it, that path is unverified.
- unclear; no cap on the commit walk here (contrast `limit=10000` in `require_signatures` and `commit_fetch_limit` in the rewind guard).
