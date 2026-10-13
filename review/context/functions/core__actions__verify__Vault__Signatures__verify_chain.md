## `verify_chain` in sgit_ai/core/actions/verify/Vault__Signatures.py (L54-L87)

**Purpose:** Walks a commit graph from `head` and classifies every commit reached, stopping at what the caller says is already held (`stop_at`) and not expanding past shallow boundaries. Its `first_failure` is the single value that `require_signatures` and `Step__Clone__Verify_Signatures` turn into a refusal; `check verify` prints its counts.

**Inputs & Assumptions:**
- `c`, `read_key`: trusted, local.
- `head` (str): the commit to start from. Trust: **semi-trusted** (a decrypted ref from the server, or a local ref).
- `stop_at` (set): commits not classified and not expanded (L56-L57, L73). Trust: trusted — computed by the caller from local history and the policy anchor. **This is where "what is incoming" is decided; the function trusts it entirely.**
- `limit` (int): `0` = unbounded (L59); clone passes `1` for "head only" (`Step__Clone__Verify_Signatures` L61).
- `index`: when `None`, loaded from disk (L62-L66) with every exception → `None` (so a present-but-unreadable index silently disables the branch→key fallback *here*; callers that care fail closed before calling, `Vault__Incoming_Check.require_signatures` L30, `Step__Clone__Verify_Signatures` L37).
- `boundaries` (set): classified but not expanded (L58, L82-L83).
- Precondition: the commits to classify are in `c.obj_store`; otherwise they count as `missing`, which is a failure (L80).

**Outputs & Effects:**
- Returns `dict(total, counts, by_status, first_failure)`; `first_failure` is `(cid, status)` for the first non-`VERIFIED` commit in BFS order, or `None` (L70, L80-L81).
- No writes of its own (via `status_of`→`_key_for`, key files may be fetched and written).
- Raises whatever `status_of`/`load_commit` raise (see `status_of`).

**Block-by-Block:**

```python
# L61-L66
vc = Vault__Commit(...)
if index is None:
    try:
        index = c.branch_manager.load_branch_index(self._directory_of(c), c.branch_index_file_id, read_key)
    except Exception:
        index = None
```
- **What:** One `Vault__Commit` for the walk; the index, best-effort.
- **Assumes:** `_directory_of(c)` (L89-L91, `dirname(c.sg_dir)`) is the vault root — true because `sg_dir = directory/.sg_vault` (`Vault__Sync__Base._init_components` L365).
- **Establishes:** `index` may be `None`; only the pre-0.19 branch→key fallback in `_key_for` L30-L32 is affected.

```python
# L67-L77
stop  = set(stop_at or []); bounds = set(boundaries or [])
seen  = set(); queue = [head] if head else []
...
while queue:
    cid = queue.pop(0)
    if not cid or cid in seen or cid in stop:
        continue
    seen.add(cid)
    if limit and len(seen) > limit:
        break
```
- **What:** BFS with dedup; `stop` commits are skipped before being counted; `limit` breaks after `limit+1` have been added to `seen` (the `limit+1`-th is added then the loop breaks before it is classified — so `total` can read `limit+1` while only `limit` were classified).
- **Why here:** `stop` filtering before `seen.add` means a stopped commit is never classified and never expanded.
- **Assumes:** `stop_at` is exactly the set of commits the clone already accepted plus the policy start; computed by `Vault__Incoming_Check.local_history` + `policy_start`, or by `Step__Clone__Verify_Signatures._anchor_commits`.
- **Establishes:** each classified commit is classified once.
- **Depended on by:** L78-L85.

```python
# L78-L85
status = self.status_of(c, read_key, cid, index=index, vc=vc)
by[status].append(cid)
if status != VERIFIED and first_failure is None:
    first_failure = (cid, status)
if status == MISSING or cid in bounds:
    continue
commit = vc.load_commit(cid, read_key)
queue.extend(str(p) for p in (commit.parents or []) if str(p))
```
- **What:** Classify, record the first failure, then expand parents unless missing or a boundary.
- **Why here:** `MISSING` must not be expanded (no object to read); a boundary is classified (the head of a shallow clone must still verify) but its parents are by design absent.
- **Assumes:** the walk does not stop at the first failure — it keeps going (so the whole chain is classified for `check verify`), but `first_failure` is BFS-first, not "closest to head". The parents list is `list[Safe_Str__Object_Id]` (`Schema__Object_Commit.py:L14`), regex `^obj-cas-imm-([0-9a-f]{12}|[0-9a-f]{32})$`, so a parent id is path-safe when later used in `os.path.join`.
- **Establishes:** every commit reachable from `head` through local objects, not in `stop`, has a status.
- **Depended on by:** `require_signatures` L47-L53 (raises on `first_failure`), `Step__Clone__Verify_Signatures` L65-L70, `cmd_check_verify` (prints counts).

**Cross-Function Dependencies:**
- Callee `status_of` (internal): see record. Note `load_commit` is called twice per commit (L46 inside `status_of`, L84 here).
- Callee `Vault__Branch_Manager.load_branch_index` (internal, L88-L96): decrypt + `Vault__Index_Reader.parse` + `Vault__Format.check_client` (L96). A `Vault__Client_Too_Old_Error` here is swallowed by L65-L66 — the format gate does not refuse from inside `verify_chain`; it refuses earlier in `_init_components`→`_apply_vault_format` (`Vault__Sync__Base.py:L356-L359`).
- Callers (read): `Vault__Incoming_Check.require_signatures` (L45-L46; `stop_at = local_history | policy_start`, `boundaries` from local config); `Step__Clone__Verify_Signatures.execute` (L62-L64; `stop_at = anchor | range_stop`, `limit` 0 or 1); `Vault__Sync.verify_signatures` (`sgit_ai/core/Vault__Sync.py:L271-L272`; `stop_at` none, `boundaries` from config, head = this clone's own head).
- Shared state: object store, key store.
- Invariant coupling: "nothing writes a local named ref or a baseline except verify-then-accept" (`Vault__Incoming_Check` docstring L3-L5) is enforced by the *callers'* ordering, not here.

**Open Questions:**
- unclear; `limit` semantics when the head itself is in `stop` (then nothing is classified and `first_failure` is `None` — a pass). `require_signatures` guards this with `if incoming_head in stop: return` (L34-L35); `Step__Clone__Verify_Signatures` has no such guard but its `stop_at` only contains the anchor and `range_from`, so a head equal to the anchor passes silently. Whether a vault whose head *is* the recorded `signed-since` commit should be checked at all is a policy question, not a code one.
