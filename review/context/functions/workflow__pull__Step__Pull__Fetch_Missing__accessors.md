## `_enforce_signature_policy` in sgit_ai/workflow/pull/Step__Pull__Fetch_Missing.py (L14-L27)

**Purpose:** Adapter: early-returns when nothing is incoming (L22-L23) or no index file exists (L24-L25), else calls `Vault__Incoming_Check.require_signatures(directory, _init_components(directory), read_key, named_commit_id, clone_commit_id)` (L26-L27). On the read-only workflow `clone_commit_id` is the reader's cached accepted head (`RO__Load_Named_Head` L127).

**Inputs & Assumptions:** `named_commit_id`, `clone_commit_id` as str (sanitised `Safe_Str__Commit_Id` upstream). Duplicates the index-presence check that `require_signatures` repeats (L27-L29 of Incoming_Check).

**Outputs & Effects:** none of its own; raises what `require_signatures` raises.

**Cross-Function Dependencies:** caller `execute` L69 — first thing after reading local config, before any fetch of objects for this head and before `_accept`.

---

## `execute` in sgit_ai/workflow/pull/Step__Pull__Fetch_Missing.py (L46-L121)

**Purpose:** Step 4 (both workflows): policy → fetch objects → refuse an incomplete HEAD → accept.

**Order (the record that matters):** L69 `_enforce_signature_policy` → L70-L85 `_fetch_missing_objects` (only when `named != clone`) → L91-L98 `_find_missing_blobs` refusal (non-sparse; message from `_build_missing_message`) → L101 `_accept`. When `named_commit_id == clone_commit_id` nothing is fetched but `_accept` still runs (L99-L101) — a no-op ref write (L42 compares first) and a baseline write that refreshes `remote_heads.json` to the same head.

**Inputs & Assumptions:** `is_sparse` and `scope` from local config, every exception → not sparse (L60-L65).

**Outputs & Effects:** state with `n_objects_fetched`; writes via callees.

**Cross-Function Dependencies:** `_fetch_missing_objects` (see record), `_find_missing_blobs`, `_accept`, `_build_missing_message` (L123-L196, pure formatting of ABSENT/FORBIDDEN/TRANSIENT counts; no secrets).

**Open Questions:** none beyond `_accept`'s.
