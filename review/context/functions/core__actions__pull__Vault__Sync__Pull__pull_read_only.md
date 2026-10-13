## `pull_read_only` in sgit_ai/core/actions/pull/Vault__Sync__Pull.py (L110-L142)

**Purpose:** The read-only clone's pull: 4 steps (`Workflow__Pull__ReadOnly`): derive keys → load named head (index refresh, rewind guard, nothing written) → fetch missing (**signature policy**, objects) → RO checkout (straight checkout, **then** accept: named ref + baseline). No merge, no commit, no clone ref (docstring L111-L113).

**Inputs & Assumptions:** as `pull`, minus `merge_from`. `_init_components` for a read-only clone derives keys from `clone_mode.json` (`Vault__Sync__Base._derive_keys_for_directory` L311-L313) and sets `vault_key=''` (L370-L371); `write_key` is `''` (`import_read_key`, `Vault__Crypto.py:L230`).

**Outputs & Effects:** working copy rewritten to the named head; `bare/refs/<named>` and `remote_heads.json` written **after** the checkout (`Step__Pull__RO__Checkout` L94-L100); returns `_pull_state_to_dict`.

**Order of checks before the accept (traced):**
1. `Step__Pull__RO__Load_Named_Head.execute` (L32-L131): index refresh with no write key (L45-L50, every exception swallowed); `accepted = _accepted_head(...)` (L74-L80; damaged record raises unless accepted); `cached` = accepted or the local ref, cleared if its object is absent (L81-L83); server ref read (L92); `_guard_rewind` with `last_known = accepted` (L90, L97-L98); unreadable ref refuses (L102-L104). Nothing written (comment L112-L114).
2. `Step__Pull__Fetch_Missing.execute`: `_enforce_signature_policy(named, cached)` (L69) → `require_signatures`; `_fetch_missing_objects` with `stop_at = cached` (L79); `_find_missing_blobs` refusal (non-sparse); `_accept` returns immediately because `input.clone_ref_id` is `None` on this path (L32 of the step; `RO__Load_Named_Head` sets `clone_ref_id=None`, L125).
3. `Step__Pull__RO__Checkout.execute` (L31-L125): `_checkout_flat_map` + `_remove_deleted_flat` with the **disk scan** as the deletion baseline (L83-L86) — no dirty-tree guard on a read-only clone (uncommitted edits are overwritten; there is nothing to commit them to); then, if `named_commit_id and remote_reachable and named_ref_id`, `write_ref` + `_write_remote_baseline` (L94-L100). Baseline write failures are swallowed (L96-L100).

Note the RO path writes the named ref via `ref_manager.write_ref` (re-encrypting `{commit_id}` under the read key with a fresh IV) rather than storing the server's exact bytes as the writable path does (`Step__Pull__Fetch_Missing._accept` L37-L41). A reader never pushes, so there is no compare-and-swap to match.

**Cross-Function Dependencies:**
- Callers: `CLI__Vault._cmd_pull_read_only` (L1037-L1038), dispatched by `cmd_pull` when `clone_mode.json` says `read-only` (L957-L960).
- Tests: `tests/security/test_Security__Fixed__Trust_And_Policy.py::test_K2__a_refused_read_only_pull_refuses_again` (accept after policy), `::test_TM_R05__read_only_clone_refuses_a_rollback`, `tests/security/test_Security__Fixed__Verify_Then_Accept.py::test_N3__status_between_read_only_pulls_does_not_get_past_the_policy`.

**Open Questions:**
- unclear; the RO checkout uses `disk_map` for deletions, so an *untracked* file in a read-only clone is deleted on pull if the new head does not contain it (comment L80-L82 of RO__Checkout describes it as pruning). Whether that is the intended reader experience.
