## `execute` in sgit_ai/workflow/clone/Step__Clone__Verify_Signatures.py (L24-L71)

**Purpose:** Clone-side signature policy (TM-R04). After every object is local and before any branch is registered or any working-copy file written, refuse the clone when, under `signatures-required`, a commit since the recorded policy start does not verify.

**Inputs & Assumptions:**
- `input.named_commit_id`, `input.branch_index_file_id` (both required, L27-L28), `input.shallow_boundaries`, `input.range_from`.
- Implicit: the local index just downloaded (`index_path` L34-L36; "present but unreadable: fail closed" — `load_branch_index` at L37 is outside any `try`).
- `workspace.sync_client.api` for `Vault__Key_Fetch` (L62).

**Outputs & Effects:** returns `input` unchanged, or raises `Vault__Signature_Error` (L65-L70). Key files may be fetched (verified-by-decrypt) by `Vault__Key_Fetch`.

**Block-by-Block:**

```python
# L57-L61
bounds     = {str(b) for b in (input.shallow_boundaries or [])}
range_stop = {str(input.range_from)} if getattr(input, 'range_from', None) else set()
recorded   = Vault__Format().sig_anchor_of(index)
anchor     = self._anchor_commits(sg_dir, recorded)
limit      = 0 if (anchor or (recorded and bounds)) else 1    # no recorded start (policy set before 0.21): the head must verify
```
- **What:** Stop set = the local anchor commit(s) (+ `range_from` for clone-range); boundaries classified but not expanded; `limit=1` (head only) when there is no local anchor and no (recorded anchor + shallow boundaries).
- **Assumes:** `limit=1` fires in two cases: (a) a vault whose policy predates the `signed-since` record — documented; (b) a vault with a recorded anchor **that is not among the downloaded objects** on a full clone (e.g. the anchor commit is on another branch, or history was rewritten past it). In (b) only the head is verified; everything under it is unchecked. `test_TM_R04__clone_refuses_an_unsigned_commit_under_a_signed_head` covers the case where the anchor **is** local (policy set on the current head, then forged on top). Nothing found covering (b).
- **Establishes:** the arguments of `verify_chain`.

```python
# L62-L70
report = Vault__Signatures(crypto=crypto, key_fetch=Vault__Key_Fetch(crypto=crypto, api=workspace.sync_client.api)
                           ).verify_chain(c, read_key, named_commit_id, stop_at=anchor | range_stop, limit=limit, index=index, boundaries=bounds)
if report['first_failure']:
    raise Vault__Signature_Error(...'the clone was refused before any file was written'...)
```
- **Assumes:** `verify_chain` semantics; see record. On a shallow clone (`--depth`) with a recorded anchor not within depth, `limit=0` and `bounds` stop the walk at the boundary (classified, not expanded).

**Cross-Function Dependencies:**
- Callee `_anchor_commits` (L73-L83): prefix listing of `bare/data/`, same as `Vault__Incoming_Check.policy_start`.
- Callee `Vault__Components(...)` built by hand (L47-L56) with `vault_key` unset — fine, `verify_chain` does not use it.
- Callers: step 9 of `Workflow__Clone` (L33), step 9 of `Workflow__Clone__ReadOnly` (L32), and (per `test_K3`) `Workflow__Clone__Branch` / `__Range` (not read).
- Order: after `Step__Clone__Download_Blobs`, before `Step__Clone__Create_Clone_Branch` (writes clone ref, index entry, key pair) and `Step__Clone__Extract_Working_Copy`.

**Open Questions:**
- unclear; case (b) above — a recorded anchor that is not local on a full clone falls back to head-only verification. Whether that can arise on a legitimately maintained vault (anchor on a different named branch than `current`?) — `set_format._current_head` records the head of `'current'` (`Vault__Sync__Format.py:L72`), and clone follows `'current'` (`Step__Clone__Download_Index` L109), so on the main branch the anchor should be reachable unless history was rewound past it.
