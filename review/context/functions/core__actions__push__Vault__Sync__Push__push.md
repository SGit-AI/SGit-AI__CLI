## `push` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L25-L396)

**Purpose:** Move the named branch on the host to this clone's head: refuse unsafe states, read the server's copies of the index and ref, decide "first push" / "nothing to push" / "behind" / "rewound", pull first (unless `--force`), upload blobs (with a resumable checkpoint), then commits + trees + the ref in one batch where the ref write is compare-and-swap, then record the new remote baseline locally. Everything that can overwrite a teammate's or the host's state funnels through the `force` / `expected_ref_hash` pair it hands to `Vault__Batch.build_push_operations`.

**Inputs & Assumptions:**
- `directory` (str): the clone. Trust: local user.
- `force` (bool): from CLI `--force` or set True by the CLI for `--force-with-lease` (sgit_ai/cli/CLI__Vault.py:L1204-L1207).
- `lease` (str | None): `None` = no lease; `''` = "where this clone last saw the remote"; a commit id/prefix = explicit (CLI L1205, L1210; `cmd_push` L1179-L1183 disambiguates a directory from a commit).
- `use_batch` (bool, default True): never set False by the CLI (grep `use_batch` in `sgit_ai/cli/` → nothing).
- `branch_only`, `push_conflict`, `on_progress`, `message` (unused here).
- Implicit: `self.api` (`Vault__API`/`Auto`/`Static`), `self.crypto`, `.sg_vault/` state via `_init_components` (keys derived from the local vault key: `vault_id`, `read_key`, `write_key`, `branch_index_file_id`; Vault__Sync__Base.py:L364-L396), `local/config.json` (`my_branch_id`), `local/remote_heads.json` (baselines), `local/push_state.json`, `local/pending_registration.json`.
- Preconditions and who establishes them:
  - no `.conflict` files unless `push_conflict` (L47-L48, `_check_no_conflict_files`);
  - no merge in progress (L49, `Vault__Merge__State.check_not_in_progress`, Vault__Merge__State.py:L42-L49);
  - the branch index loads and the gate admits this client (L72 → `load_branch_index` → `Vault__Format.check_client`, Vault__Branch_Manager.py:L88-L97);
  - the clone branch and its tracked named branch exist in the index (L74-L80, `tracked_named_branch` never falls back to `current` when a creator branch is recorded, Vault__Branch_Manager.py:L111-L124);
  - the server's index has no branch with the same name on another ref (L84-L85, `refuse_name_clash`; test `tests/unit/review/test_Review__eed8084.py::test_push_refuses_before_writing_anything`);
  - the server's named ref, if present, decrypts under this vault's key (L86, `_require_readable_server_ref`, Vault__Sync__Base.py:L80-L96 — offline/absent is not an error there);
  - working copy clean (L91-L95, `Vault__Sync__Status.status`, a network-reading status that writes no ref: `tests/security/test_Security__Fixed__Verify_Then_Accept.py::test_N3__status_writes_no_ref`).

**Outputs & Effects:**
- Returns one of: `up_to_date` (L101, L135, L190, L193), `resynced` (L111), `behind` / `rewound` (L121), `pushed_branch_only` (via `_push_branch_only`), `pushed` (L391-L396) with `cache_*` and `pull_*` fields.
- Host writes (all through `Vault__Batch`): branch registration (index CAS, clone ref, public key — `_register_pending_branch` L88), the whole `bare/` tree on a first push or resync (L110, L140), public key (L142), blobs (Phase A), commits/trees/ref (Phase B), cache objects (`_reconcile_cache`).
- Local writes: `push_state.json` checkpoints (L294, L318, cleared L389); the local named ref moved to `clone_commit_id` (L366, `Vault__Ref_Manager.write_ref`, which also appends to the reflog); the remote baseline for the named ref (L367, `_write_remote_baseline` → `Vault__Secret_File` write of `remote_heads.json`, Vault__Sync__Base.py:L239-L254); a merged index when registration merged (L850-L851).
- Raises: `RuntimeError`s for the guards; `Vault__Push_Conflict_Error` (name clash, index race, CAS miss); `Vault__Push_Lease_Error`; `Vault__Unreadable_Ref_Error`; `Vault__Signature_Error` from `require_signatures`; `Vault__Client_Too_Old_Error`.

**Block-by-Block:**

```python
# L52-L55
c = self._init_components(directory)
if lease is not None and not lease:
    lease = self._read_remote_baseline(directory, c.storage, self._tracked_named_ref_id(directory)) or ''
```
- **What:** `--force-with-lease` with no commit: the lease is the last head this clone **accepted** (pull/merge/own push), never one `status` observed (comment L53-L55; review B2; `tests/security/test_Security__Fixed__Baselines.py::test_B2__status_does_not_satisfy_the_lease`).
- **Assumes:** `remote_heads.json` is readable; `_remote_baselines` raises `Vault__Ref_Rewind_Error` when the record is damaged or missing-after-existing (Vault__Sync__Base.py:L170-L186) — propagates.

```python
# L82-L86
index_sync = Vault__Index_Sync(crypto=self.crypto, api=self.api)
index_sync.refuse_name_clash(branch_index, index_sync.read_remote(vault_id, index_id, read_key)[1], str(named_meta.branch_id))
self._require_readable_server_ref(vault_id, str(named_meta.head_ref_id), read_key)
```
- **What:** two server reads before anything is written: the index (`read_remote` → `api.read`, decrypt, `check_client`) and the named ref (`api.read`, decrypt).
- **Assumes:** `read_remote` returning `(None, None)` for an unreadable/absent index (Vault__Index_Sync.py:L44-L52) makes `refuse_name_clash` a no-op (`name_clashes` returns `{}` when `remote is None`, L207-L208) — an offline or substituted index does not block the push here. The server's index gate can raise `Vault__Client_Too_Old_Error` (L53) — the host can refuse this client by `min_client` (TM-R26/TM-R29 territory).
- **Assumes:** a ref that decrypts to a `commit_id` is "readable"; nothing binds it to this ref id (TM-R03) or checks freshness (SP-2).

```python
# L88-L89
self._register_pending_branch(directory, vault_id, write_key, read_key, storage, ref_manager, _p)
```
- **What:** first push after a clone: merge+CAS the index, plain-write the clone ref and public key. See its record. Runs **before** the dirty-tree check and before the "nothing to push" decision, so a clone with nothing to push still registers.

```python
# L97-L101
clone_commit_id = ref_manager.read_ref(str(clone_meta.head_ref_id), read_key)
named_commit_id = ref_manager.read_ref(str(named_meta.head_ref_id), read_key)
if not clone_commit_id: return dict(status='up_to_date', ...)
```
- **What:** both heads from **local** ref files (decrypted).

```python
# L103-L135  ("nothing to push" before any pull)
if clone_commit_id == named_commit_id:
    if not self._commit_tree_is_empty(...):
        if self._is_first_push(vault_id) or not self._server_has_named_ref(vault_id, named_ref_id_str):
            self._upload_bare_to_server(directory, vault_id, write_key, storage, read_key)
            return dict(status='resynced', ...)
    server_head = self._server_named_commit_id(vault_id, named_ref_id_str, read_key)
    if server_head and server_head != named_commit_id:
        rewound = self._server_rewound(c, read_key, named_commit_id, server_head)
        return dict(status='rewound' if rewound else 'behind', server_head=server_head, message='Nothing to push', ...)
    cache_stats = self._reconcile_cache(...)
    return dict(status='up_to_date', message='Nothing to push', **cache_stats)
```
- **What:** local heads equal → decide between resync, behind/rewound, or cache-only reconcile.
- **Assumes (resync):** `list_files(vault_id, 'bare/')` empty, or the named ref id absent from `list_files(vault_id, 'bare/refs/')`, means the server lost the vault structure → re-upload **every** local `bare/` file with plain writes (`_upload_bare_to_server`: blobs, trees, commits, refs, indexes, keys, cache). A listing error is an error, not "empty" (`_is_first_push` L721-L725, `_server_has_named_ref` L768-L772; review S10). A listing that is *successfully* empty or lacks the ref is trusted: `nothing found` cross-checking it against `_server_named_commit_id` before the re-upload.
- **Assumes (behind/rewound):** `_server_named_commit_id` returns the server's head or `None` (offline / undecryptable → `None` → treated as "could not verify" and the code goes on to reconcile caches against the local head, L125-L135; the undecryptable case was already refused at L86). Tests: `tests/unit/review/test_Review__d3b8eef__Lower_Priority.py::test_push_on_a_rewound_branch_says_so`, `test_push_when_a_teammate_pushed_says_behind`; CLI exits 1 on `rewound` (CLI__Vault.py:L1223-L1228).
- **Establishes:** nothing is written to the host on this path except the resync re-upload and cache ops.

```python
# L137-L142
first_push = self._is_first_push(vault_id)
if first_push:
    self._upload_bare_to_server(directory, vault_id, write_key, storage, read_key)
else:
    self._ensure_public_key(c, vault_id, write_key, clone_meta, _p)
```
- **What:** first push → plain-write all of `bare/` (including the local named ref file with its *old* head, and any legacy private key under `bare/keys/`, TM-R27); otherwise make sure this clone's public key is on the server.
- **Assumes:** `list_files` returned an honest empty list. See `_is_first_push`.

```python
# L144-L162  branch_only
```
- Delegates to `_push_branch_only`; the named ref is untouched.

```python
# L164-L173
pull_result = None
if not first_push and not force:
    pull_result = Vault__Sync__Pull(crypto=self.crypto, api=self.api).pull(directory)
    if pull_result['status'] == 'conflicts': raise RuntimeError(...)
clone_commit_id = ref_manager.read_ref(...); named_commit_id = ref_manager.read_ref(...)
```
- **What:** fetch-first. `pull` (sgit_ai/core/actions/pull/Vault__Sync__Pull.py:L72) applies the rewind guard, `signatures-required`, verify-before-write, and moves the **local** named ref + baseline to the server's head (L63 there; `_write_remote_baseline`). After it, the local named ref file holds the **server's exact ciphertext bytes**: `Step__Pull__Fetch_Missing._accept` writes `workspace.remote_ref_data` (the bytes `api.read` returned, Step__Pull__Fetch_Remote_Ref.py:L87, L96) straight to `bare/refs/<named>` (sgit_ai/workflow/pull/Step__Pull__Fetch_Missing.py:L36-L41, comment: "the server's exact bytes: push's compare-and-swap matches against them"), and only re-encrypts via `write_ref` when no raw bytes were captured (L42-L43). This is what makes the CAS `match` at L201 the server's current bytes.
- **Assumes:** with `force` (plain `--force` or `--force-with-lease`) the pull is skipped, so the local named ref may be stale; `--force` then overwrites blindly (by design), `--force-with-lease` replaces the match with the server's bytes (L205). `tests/unit/review/test_Tags_Reflog_Lease.py::test_plain_force_push_does_not_crash_on_the_remote_heads_missing_tree` covers the stale-tree fetch at L223-L230.

```python
# L175-L193
if clone_commit_id == named_commit_id:
    cache_stats = self._reconcile_cache(...); return up_to_date
if not clone_commit_id: return up_to_date
```
- **What:** after the pull, nothing new → cache-only.

```python
# L195-L198
Vault__Incoming_Check(crypto=self.crypto, api=self.api).require_signatures(directory, self._init_components(directory), read_key, clone_commit_id, named_commit_id or '')
```
- **What:** under `signatures-required`, refuse here what every other clone would refuse on pull — before anything is sent (d3b8eef L5). Policy source: the **local** index (loaded inside), which the pull just merged with the server's (gate follows the server copy, TM-R29).

```python
# L200-L206
named_ref_id      = str(named_meta.head_ref_id)
expected_ref_hash = ref_manager.get_ref_file_hash(named_ref_id)
if not first_push and lease is None and self._named_ref_absent_on_server(vault_id, named_ref_id):
    expected_ref_hash = None
if lease is not None and not first_push:
    expected_ref_hash = self._check_lease(directory, vault_id, read_key, storage, named_ref_id, lease)
    force             = False
```
- **What:** the CAS match. Default: the **local** ref file's raw bytes (= server's after the pull). Dropped to `None` (plain write) only when the **server says** the ref does not exist (`not_found`, ABSENT classification; TM-R33 for the race, `tests/security/test_Security__Fixed__Index_Overwrite.py::test_S10__a_per_file_read_error_never_turns_the_ref_write_into_a_blind_write` for the error-is-not-absent rule). Lease: the server's current bytes, after checking the server's head equals the leased commit; `force` is then cleared so the write is CAS, not blind.
- **Assumes:** on a **first push** `expected_ref_hash` stays the local bytes (neither branch at L202/L204 applies), and the match holds because `_upload_bare_to_server` (L140) just uploaded that very file — the CAS is against our own upload, i.e. effectively unguarded against a concurrent first push (TM-R33).
- **Assumes:** the host's `not_found` is truthful; a host that answers `not_found` for a ref it holds turns the CAS into a plain write: `nothing found` beyond the server's word.
- **Establishes:** `(force, expected_ref_hash)` → the ref op kind in `build_push_operations` L92-L104.

```python
# L208-L257
clone_commit = vault_commit.load_commit(clone_commit_id, read_key)
clone_flat, _ = scoped_tree.flatten(...)
if named_commit_id:
    named_commit = vault_commit.load_commit(named_commit_id, read_key)
    if not obj_store.exists(str(named_commit.tree_id)):
        Vault__Sync__Pull(...)._fetch_missing_objects(vault_id, named_commit_id, obj_store, read_key, c.sg_dir, _p, include_blobs=False, **fetch_kw)
    named_flat, _ = scoped_tree.flatten(...); named_blob_ids = {...}
commit_chain = fetcher.fetch_commit_chain(obj_store, read_key, clone_commit_id, stop_at=named_commit_id)
new_commits  = [cid for cid in commit_chain if cid != named_commit_id]
clone_tree_entries = batch.collect_chain_blob_entries(commit_chain, named_commit_id, obj_store, read_key, skip_missing_trees=scope.is_scoped())
```
- **What:** the delta. The only host read here is `_fetch_missing_objects` for a force push whose named tree is not local — a verified download (Vault__Sync__Pull.py:L276-L290 `_save` → `Vault__Verified_Write`).
- **Assumes:** `fetch_commit_chain` is a local walk (`load_commit` only, `get_parents` swallows errors → a missing parent truncates the chain silently, Vault__Fetch.py:L36-L42); `limit=100` caps the chain, so a clone more than 100 commits ahead pushes only the newest 100 and their trees — the older commits are **not** uploaded though the chain references them. Observation: `nothing found` detecting a truncated chain here. (Readers refuse a head whose history is missing: `Vault__Sync__Status._fetch_commit_chain` `connected=False`.)

```python
# L259-L320  Phase A
if not first_push:
    push_state = self._load_push_state(state_path, vault_id, clone_commit_id, remote_url=remote_url)
    already_done = set(str(b) for b in push_state.blobs_uploaded)
    ...
    for bid in to_upload:
        ciphertext = obj_store.load(bid)
        if len(ciphertext) > LARGE_BLOB_THRESHOLD:
            uploaded = batch._upload_large(vault_id, f'bare/data/{bid}', ciphertext, write_key, on_progress)
            if uploaded: ... push_state.blobs_uploaded.append(...); self._save_push_state(...)
            else: small_blob_ops.append(write)
        else: small_blob_ops.append(write)
    if small_blob_ops:
        if use_batch:
            try: batch.execute_batch(vault_id, write_key, small_blob_ops)
            except Exception: batch.execute_individually(vault_id, write_key, small_blob_ops)
        else: batch.execute_individually(..., atomic_moves=False)
        ... push_state.blobs_uploaded.append(...)   # all of them
        self._save_push_state(state_path, push_state)
    uploaded_blob_ids.update(already_done)
```
- **What:** blobs first, checkpointed per large blob and per small batch so a retry skips what landed.
- **Assumes:** the checkpoint (`push_state.json`, keyed by vault_id, clone_commit_id, remote_url — `_load_push_state`) is truthful: a blob listed there is skipped on retry **without asking the server**. It is a local 0600 file written by this process (`_save_push_state`); `nothing found` re-verifying against the server. `execute_individually`'s own result list (always `ok`) is what L313-L318 trust.
- **Assumes:** `except Exception` at L309 — including `Vault__Push_Conflict_Error`, impossible for plain writes — falls back to one-by-one PUTs.

```python
# L322-L363  Phase B
operations, _ = batch.build_push_operations(..., named_blob_ids=uploaded_blob_ids, ..., expected_ref_hash=expected_ref_hash, force=force, skip_missing_trees=scope.is_scoped())
if first_push:
    operations = [op for op in operations if str(op.get('file_id', '')).startswith('bare/refs/')]
if use_batch:
    try: batch.execute_batch(vault_id, write_key, operations)
    except Vault__Push_Conflict_Error: raise
    except Exception as e: batch.execute_individually(vault_id, write_key, operations)
else: batch.execute_individually(vault_id, write_key, operations, atomic_moves=False)
```
- **What:** commits, trees and the ref. On a first push only the ref op remains (the bare upload sent the rest — but see `team/humans/dinis_cruz/claude-code-web/04/15/push-named-branch-contamination-fix.md:L106` for the historical ordering hazard: anything created after `_upload_bare_to_server` and before here would not be uploaded; today the clone head is committed before push starts).
- **Assumes:** a conflict is final ("retrying op by op cannot help", L358) — correct for a true race; for a 502-retried batch that had landed, the conflict is against our own bytes and the push fails although the server holds the move (see `execute_batch`). Any other failure → fallback with its pre-check CAS.
- **Establishes:** on return without exception, the host reported every op `ok` (`_checked`) or the fallback's own `ok` list.

```python
# L365-L367
ref_manager.write_ref(named_ref_id, clone_commit_id, read_key)
self._write_remote_baseline(directory, storage, named_ref_id, clone_commit_id)
```
- **What:** local named ref and the accepted-remote-head baseline move to the pushed commit. From now on a server head that does not descend from `clone_commit_id` is a rewind for this clone (`Vault__Ref_Guard`).
- **Assumes:** the server really holds the move (above). A host that answered `ok` without writing leaves this clone believing a baseline the server never had; the next pull's rewind guard would then fire on the honest history. `nothing found` re-reading the ref after the write.

```python
# L369-L396
cache_stats = {} if scope.is_scoped() else self._reconcile_cache(...)
if not first_push: self._clear_push_state(state_path)
return dict(status='pushed', commit_id=clone_commit_id, objects_uploaded=blob_count, commits_pushed=commit_count, **cache_stats, **self._pull_file_changes(pull_result))
```
- **What:** fail-soft cache layer after the ref is durable; clear the checkpoint; report.

**Cross-Function Dependencies:**
- Callees in this slice: `_register_pending_branch`, `_is_first_push`, `_server_has_named_ref`, `_upload_bare_to_server`, `_server_rewound`, `_reconcile_cache`, `_ensure_public_key`, `_push_branch_only`, `_named_ref_absent_on_server`, `_check_lease`, `_load/_save/_clear_push_state`, `_commit_tree_is_empty`, `_pull_file_changes`; `Vault__Batch.collect_chain_blob_entries`, `_upload_large`, `execute_batch`, `execute_individually`, `build_push_operations`.
- Callees outside (read in full where cited): `Vault__Sync__Base._init_components` L364-L396, `_read_remote_baseline` L224-L225 / `_remote_baselines` L161-L191, `_write_remote_baseline` L239-L254, `_require_readable_server_ref` L80-L96, `_server_named_commit_id` L113-L128, `_tracked_named_ref_id` L263-L271; `Vault__Index_Sync.read_remote` L40-L54, `refuse_name_clash` L235-L244; `Vault__Ref_Manager.read_ref` L34-L45, `write_ref` L16-L32, `get_ref_file_hash` L65-L76; `Vault__Fetch.fetch_commit_chain` L18-L76; `Vault__Sync__Pull.pull` (L72, not read in full — external-source-available), `_fetch_missing_objects` L259-L340; `Vault__Incoming_Check.require_signatures` (L13, signature only); `Vault__Sync__Status.status` (L16).
- Callers: `Vault__Sync.push` (sgit_ai/core/Vault__Sync.py:L323-L327) ← `CLI__Vault.cmd_push` L1211.
- Shared state (host): `bare/refs/<named>` with every teammate's push and the web UI; `bare/indexes/<id>` (via registration); `bare/data/*` (append-only by content address); `bare/keys/*`; `bare/cache/*`. Shared state (local): `remote_heads.json` with pull/merge/switch; the local ref files with commit/pull/status (status never writes).
- Invariant couplings: (1) "the ref moves only by CAS unless the user forced it" — holds on the default path via the pull → local bytes → `match` chain; broken by design for `--force`, and by the server's word for `not_found`; (2) "last_remote_head/baseline only moves on an accepted head" — moved here on our own successful push; (3) "verify-before-write on every download" — the only downloads here are the lease/ref reads (mutable, decrypt-only) and `_fetch_missing_objects` (verified).

**Open Questions:**
- unclear; the 100-commit `limit` in `fetch_commit_chain` (L239) versus a clone that is further ahead: what the server ends up holding.
- unclear; whether `Vault__Sync__Status.status` at L92 can raise on an unreachable host (it reads the server at Status L131 inside `try/except`), i.e. whether an offline push fails at L92 or later at `_is_first_push`.
