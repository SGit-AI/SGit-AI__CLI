## `_accept` in sgit_ai/workflow/pull/Step__Pull__Fetch_Missing.py (L29-L44)

**Purpose:** "Verify-then-accept, the only writer of a writable clone's named ref and baseline" (docstring L30-L31). Writes `bare/refs/<named_ref_id>` and `local/remote_heads.json`.

**Inputs & Assumptions:**
- `workspace.remote_ref_data` (bytes | None): the server's exact ref bytes from step 3 (L96 of Fetch_Remote_Ref).
- `input.remote_reachable`, `input.named_ref_id`, `input.clone_ref_id`: all must be truthy (L32-L33) — so **offline pulls never move the ref or baseline**, and the read-only workflow never reaches the body (`clone_ref_id` is `None` there).
- `named_commit_id`: the decrypted head.
- Preconditions (established by the caller's ordering in `execute`, L69-L101): `_enforce_signature_policy` returned (policy passed or not applicable); `_fetch_missing_objects` ran; `_find_missing_blobs` found nothing (non-sparse). Nothing inside `_accept` re-checks any of these; it trusts its position in `execute`.

**Outputs & Effects:**
- **Write 1:** `bare/refs/<named_ref_id>` ← `raw` server bytes via plain `open(..., 'wb')` (L37-L41); or, if `raw` is somehow absent while `remote_reachable` is True, `ref_manager.write_ref` re-encrypts (L42-L43, which also appends to the reflog, `Vault__Ref_Manager.write_ref` L19-L24). **The raw-bytes branch does not append to the reflog** (it bypasses `Vault__Ref_Manager`).
- **Write 2:** baseline via `_write_remote_baseline` (L44) → `Vault__Secret_File.write` (0600 temp + rename) and `config.json` marker (`_mark_remote_heads_file`).
- Not a ref write of the **clone** branch — that is step 5.

**Block-by-Block:**

```python
# L36-L41
raw = getattr(workspace, 'remote_ref_data', None)
if raw:
    ref_path = os.path.join(str(input.sg_dir), 'bare', 'refs', named_ref_id)
    os.makedirs(os.path.dirname(ref_path), exist_ok=True)
    with open(ref_path, 'wb') as f: f.write(raw)
```
- **What:** Store the server's ciphertext verbatim so `get_ref_file_hash` (`Vault__Ref_Manager.py:L65-L76`) matches the server for push's compare-and-swap.
- **Assumes:** `named_ref_id` is path-safe: `Safe_Str__Ref_Id` on `Schema__Pull__State` (regex MATCH mode, `Safe_Str__Ref_Id.py:L9-L11`; `REF_ID__REGEX` not read here — see Open Questions) and it originated from the index's `head_ref_id` (same type, `Schema__Branch_Meta.py:L14`).
- **Establishes:** local named ref == server's bytes at the moment they were verified.

```python
# L42-L44
elif workspace.ref_manager.read_ref(named_ref_id, read_key) != named_commit_id:
    workspace.ref_manager.write_ref(named_ref_id, named_commit_id, read_key)
workspace.sync_client._write_remote_baseline(str(input.directory), workspace.storage, named_ref_id, named_commit_id)
```
- **What:** fallback encryption write; then the baseline.
- **Assumes:** `_write_remote_baseline` never raises in a way that matters — it swallows `Vault__Ref_Rewind_Error` from a damaged record (L243-L246 of Base, "reached only after an accepted head: start afresh") and writes a fresh file. So an accepted pull over a damaged record **rebuilds** it (`tests/security/test_Security__Fixed__Baselines.py::test_accept_rewind_rebuilds_the_record`). Other exceptions (disk full) propagate out of the step after the ref was already written — ref moved, baseline not; the next pull then has `last_known` from the old record (or `''`).

**Cross-Function Dependencies:**
- Callee `Vault__Sync__Base._write_remote_baseline` (L239-L254) → `_save_remote_baselines` (L193-L198) → `Vault__Secret_File.write` + `_mark_remote_heads_file` (L208-L222).
- Callers: `execute` L101 — **after** `_enforce_signature_policy` (L69), `_fetch_missing_objects` (L85), `_find_missing_blobs` refusal (L91-L98). **Before** `Step__Pull__Merge` (dirty-tree guard, checkout, clone ref).
- Sibling writers of the same files: `Step__Pull__RO__Checkout` L94-L100 (readers); `Vault__Sync._fetch_branch_for_switch` L206-L211 (switch to a never-fetched branch, after `require_signatures`); push (its own successful push moves the baseline, per the Base comment L152-L157; not read). `Step__Clone__Setup_Local_Config` writes the legacy `last_remote_head` (L30) at clone time — the first baseline.
- Tests: `test_Security__Fixed__Verify_Then_Accept.py::test_N3__a_refused_pull_leaves_no_local_ref_for_a_switch_to_check_out`, `::test_a_good_pull_still_accepts_and_status_still_counts`.

**Open Questions:**
- unclear; the raw-bytes write skips the reflog (`Vault__Ref_Manager.write_ref` is the only reflog appender). `sgit history reflog` therefore shows named-ref moves only on the `elif` path. Whether the reflog is meant to cover named refs at all.
- unclear; `REF_ID__REGEX` content (`sgit_ai/safe_types/Safe_Str__Ref_Id.py`) — assumed to exclude `/` and `..`; not read in this pass.
