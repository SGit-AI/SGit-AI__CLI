## `_guard_rewind` in sgit_ai/workflow/pull/Step__Pull__Fetch_Remote_Ref.py (L15-L56)

**Purpose:** Refuse, before the local ref is touched, a remote named head that does not descend from the last one this clone accepted — unless `--accept-rewind`. Used by both the writable pull (L89) and the read-only pull (`Step__Pull__RO__Load_Named_Head` L97-L98).

**Inputs & Assumptions:**
- `workspace` (Pull__Workspace): `sync_client`, `obj_store`, `ref_manager`, `accept_rewind`, `rewound_from`.
- `input` (Schema__Pull__State): `directory`, `clone_commit_id`, `named_ref_id`.
- `read_key`: trusted.
- `remote_ref_data` (bytes): the server's ref ciphertext. Trust: **untrusted bytes**; only their decryption under the read key is used (L26).
- `last_known` (str): the baseline from `_accepted_head`. `''` ⇒ return (L23-L24).

**Outputs & Effects:**
- Returns `None` (FORWARD / UNKNOWN / accepted REWOUND) or raises `Vault__Ref_Rewind_Error`.
- **Writes:** commit objects fetched by `_fetch_commit_chain` (verified); `workspace.rewound_from = last_known` when a rewind is accepted (L54) — read by `Step__Pull__Merge` L73-L82 to re-apply only this clone's own work.
- No ref or baseline write.

**Block-by-Block:**

```python
# L26-L28
remote_head = Vault__Sync__Status(...)._parse_ref(remote_ref_data, read_key)
if not remote_head or remote_head == last_known:
    return
```
- **What:** Decrypt; an undecryptable ref is `''` here and returns (the caller refuses it at L91-L94 of `execute` as `Vault__Unreadable_Ref_Error`).

```python
# L29-L43
c = sync._init_components(directory)
boundaries = …from_local_config…boundary_ids()  (except → set())
status = Vault__Sync__Status(...)
fetched, connected = status._fetch_commit_chain(c, workspace.obj_store, read_key, remote_head,
                        limit=int(getattr(sync, 'commit_fetch_limit', 50) or 50),
                        boundaries=boundaries,
                        known={last_known, str(input.clone_commit_id or ''), workspace.ref_manager.read_ref(named_ref_id) or ''})
guard   = Vault__Ref_Guard(crypto=sync.crypto)
verdict = guard.classify(c, read_key, remote_head, last_known, connected, getattr(status, '_chain_reached_known', False), boundaries)
```
- **What:** Fetch up to 50 commits of the remote lineage, stopping at known heads; classify.
- **Why here:** the walk needs objects; it writes them verified (`Vault__Sync__Status.py:L304`) — object writes are not "accepts".
- **Assumes:** `commit_fetch_limit` (default 50; `Vault__Sync.status` passes it from `self.commit_fetch_limit`, `Vault__Sync.py:L240-L241`, but `Vault__Sync__Pull` is constructed without it at `Vault__Sync.pull` L244, so the default 50 applies here). A lineage longer than 50 unrelated commits ⇒ `connected=False` ⇒ UNKNOWN (see `classify` record).
- **Establishes:** `verdict`.

```python
# L44-L49
except Exception as exc:
    if getattr(workspace, 'accept_rewind', False):
        workspace.progress('warn', ...); return
    raise Vault__Ref_Rewind_Error(f'could not check whether the server moved this branch backwards ({exc}); nothing was changed…')
```
- **What:** Any exception in the check refuses (review K2) unless the user already accepted.
- **Assumes:** exceptions are the failure mode of "cannot decide". `_fetch_commit_chain` catches API errors internally and returns `connected=False` (L300-L302 of Status) — so an offline server does **not** raise; it yields UNKNOWN, which L50-L51 lets through. So "offline pull with a baseline" proceeds to accept whatever head the local walk could not classify. Nothing found that refuses UNKNOWN.

```python
# L50-L56
if verdict != REWOUND: return
if accept_rewind:
    workspace.progress('warn', f'Accepting a rewound named branch: {last_known} -> {remote_head}')
    workspace.rewound_from = last_known
    return
raise Vault__Ref_Rewind_Error(guard.message(remote_head, last_known))
```
- **What:** Refuse a rewind, or record it for the merge step.
- **Establishes:** on return, either the head is forward/unknown or the user opted in.
- **Depended on by:** `Step__Pull__Fetch_Missing._accept` (writes the ref), `Step__Pull__Merge` (rewind merge).

**Cross-Function Dependencies:**
- Callee `Vault__Sync__Status._fetch_commit_chain` (internal, L255-L326): read in full; sets `self._chain_reached_known` as a side attribute (L284, L290, L322) read back at L43 — an attribute on a throwaway object, so safe from cross-call leakage.
- Callee `Vault__Ref_Guard.classify` (internal): see record.
- Callee `Vault__Sync__Base._init_components` (L364-L396): re-derives keys (PBKDF2 cached, `Vault__Crypto.py:L27`).
- Callers: `execute` L89 (writable); `Step__Pull__RO__Load_Named_Head.execute` L97-L98 with a synthetic `guard_input` whose `clone_commit_id` is the reader's cached head (L94-L96).
- Shared state: object store (writes), `workspace.rewound_from`.
- Tests: `tests/security/test_Security__Fixed__Trust_And_Policy.py::test_TM_R05__read_only_clone_refuses_a_rollback`, `tests/security/test_Security__Fixed__Baselines.py::*`.

**Open Questions:**
- unclear; UNKNOWN proceeds (see `classify` record). Whether an offline/limit-exceeded check should refuse is a design question the K2 comment seems to answer "yes" for exceptions only.
