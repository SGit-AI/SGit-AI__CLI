## `_refresh_index` in sgit_ai/workflow/pull/Step__Pull__Load_Branch_Info.py (L17-L45)

**Purpose:** Pull step 2's first act: take the server's branch index, merge it with ours, save locally, write the merge back with compare-and-swap when we have a write key, then fetch any teammate key files the merged index names. This is where the policy (`features`), `min_client` and `format` a pull enforces come from.

**Inputs & Assumptions:** `workspace.sync_client` (api, crypto); `c = sync._init_components(directory)` (L22; applies the local gate first).

**Outputs & Effects:**
- Local index file rewritten when the merge differs (`Vault__Index_Sync.refresh` L286-L288).
- Server index possibly rewritten (CAS) when we carry entries it lacks (L292-L298 of Index_Sync); clashes by name are kept local and warned (L24-L26 here).
- `workspace.obj_store.id_hex_len` set from the merged index (L38) — new objects this pull creates (merge commit, trees) use the server's format width.
- Key files fetched (L39-L41).
- `Vault__Client_Too_Old_Error` re-raised (L42-L43); **every other exception is a warning** (L44-L45) — offline pulls proceed on the local copy.

**Block-by-Block:**

```python
# L23
out = Vault__Index_Sync(crypto=sync.crypto, api=sync.api).refresh(c, directory, write_key=c.write_key or None)
```
- **Assumes:** `Vault__Index_Sync.merge` (L72-L115): branches = union by id (remote wins per field); gate = **remote's** unless the remote has no gate fields at all (L95-L100); format never lowered (`max`, L98). So after a refresh the local `features` list equals the server's — a server copy without `signatures-required` turns the policy off for this clone (TM-R29; documented in the threat model §5 Format-gate row). `read_remote` applies `check_client` on the server copy (L53 of Index_Sync) — raising `Vault__Client_Too_Old_Error` through here.

```python
# L37-L41
index = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
workspace.obj_store.id_hex_len = Vault__Format().id_hex_len(index)
fetch = Vault__Key_Fetch(crypto=sync.crypto, api=sync.api)
fetch.fetch_missing(c, fetch.branch_key_ids(index))
```
- **What:** Reload the merged index; pre-fetch keys for every branch.

**Cross-Function Dependencies:**
- Callee `Vault__Index_Sync.refresh` (L271-L300), `merge` (L72-L115), `upload` (L169-L198, CAS with up to 3 re-merges; `require_written` L246-L255).
- Callee `Vault__Key_Fetch.fetch_missing` (see record).
- Callers: `execute` L67, before the branch lookups (L69-L86) that produce `named_ref_id` and `clone_commit_id`.
- Tests: `tests/unit/review/test_Signature_Policy_And_Rewind__Fixes.py::test_refresh_merges_locally_and_does_not_raise`, `::test_the_owner_can_switch_the_policy_off_for_a_stale_clone`, `::test_set_format_from_a_stale_clone_keeps_the_gate_the_server_has`.

**Open Questions:**
- unclear; whether the branch→`public_key_id` mapping taken from the server copy (remote wins per field, L88-L92 of Index_Sync) can be used to re-point an *existing* branch at a different key id. Only commits without `author_key_id` consult that mapping (`Vault__Signatures._key_for` L30-L32), and the attacker needs the read key either way (TM-R01).
