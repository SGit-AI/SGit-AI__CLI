## `_pull_state_to_dict` in sgit_ai/core/actions/pull/Vault__Sync__Pull.py (L144-L182)

**Purpose:** Converts the final `Schema__Pull__State` to the legacy result dict the CLI prints (`status`, `added/modified/deleted`, `kept_dirty`, `rewound`, `reapplied`).

**Inputs & Assumptions:** `state` with `merge_status` in `{'', 'up_to_date', 'conflict', 'fast_forward', 'merge', 'rewound'}`; `remote_reachable` bool.

**Outputs & Effects:** dict; no effects; no key material (commit ids and file paths only). `rewound`/`reapplied` (L179-L181) drive the CLI's rewind wording (`CLI__Vault.cmd_pull` L1006-L1013).

**Cross-Function Dependencies:** callers `pull` L108, `pull_read_only` L142.

**Open Questions:** none.

---

## `_pull_stats_line` in sgit_ai/core/actions/pull/Vault__Sync__Pull.py (L184-L194)

**Purpose:** Formats commit/tree/blob counts and seconds. No callers found in this file; pure formatting. No effects.

---

## `_find_missing_blobs` in sgit_ai/core/actions/pull/Vault__Sync__Pull.py (L196-L216)

**Purpose:** The blob ids in `commit_id`'s (scoped) tree that are absent locally; `Step__Pull__Fetch_Missing` refuses the pull when any remain (L91-L98 of the step), so a HEAD whose blobs the host withheld or served corrupt never becomes a working copy with silently missing files.

**Inputs & Assumptions:** `commit_id` local (else `[]` via the broad `except`, L212-L213 — so an *unreadable* commit reads as "nothing missing"; the earlier policy/fetch steps would have refused or the merge step raises on `load_commit`). `scope` optional.

**Outputs & Effects:** list of blob ids; no writes.

**Cross-Function Dependencies:** callers `Step__Pull__Fetch_Missing.execute` L92-L96 (non-sparse only); uses `Vault__Sub_Tree.flatten` / `Vault__Scoped_Tree.flatten`.

**Open Questions:** the `except Exception: return []` at L212-L213 turns a flatten failure into "complete"; whether a later step always catches that case.

---

## `_classify_chunk_exception` in sgit_ai/core/actions/pull/Vault__Sync__Pull.py (L218-L250)

**Purpose:** Build a `Schema__Fetch_Failure` from an exception: 404/'Not found' → ABSENT, 403/'Forbidden' → FORBIDDEN, else TRANSIENT; `Safe_Str__Object_Id(oid)` best-effort (L242-L245). Message text (`str(error)`) becomes `Safe_Str__Error_Message`; `Vault__API._api_error` masks token/key headers before that string exists (L477-L482 of API).

**Outputs & Effects:** returns the schema; no writes.

**Cross-Function Dependencies:** callers `_fetch_missing_objects` L306, L471.

---

## `_commit_tree_local` in sgit_ai/core/actions/pull/Vault__Sync__Pull.py (L252-L257)

**Purpose:** True when `commit_id` decrypts and its `tree_id` object exists locally — the "complete below" test in the commit walk (L364). Any exception → False (re-fetch).

**Cross-Function Dependencies:** caller `_fetch_missing_objects` L364 only.

**Open Questions:** none.
