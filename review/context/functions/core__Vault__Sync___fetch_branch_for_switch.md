## `_fetch_branch_for_switch` in sgit_ai/core/Vault__Sync.py (L173-L211)

**Purpose:** Before `sgit branch switch <name>` to a branch this clone never fetched, bring its server head and objects in, run the signature policy, and only then write the local named ref (server bytes) and the baseline — the third writer of a named ref, alongside pull's `_accept` and the RO checkout.

**Inputs & Assumptions:** `directory`, `name` (branch name or id; user input, resolved against the index L185-L186).

**Order traced:**
1. L184-L191: components, index, branch meta; if a local ref or a baseline already exists for the branch ⇒ return ("the pull after the switch guards its moves").
2. L192-L195: read + decrypt the server ref (`head` is the raw `json.loads(...).get('commit_id')` — **not** passed through `Safe_Str__Commit_Id` on this path; see `_fetch_missing_objects` record for where it is used).
3. L196-L198: `_fetch_missing_objects(head, …)` — object downloads (verified writes).
4. L199-L201: `held` = this clone's own head.
5. L202-L203: **any exception in 1-4 ⇒ return silently** ("offline: switch from what this clone has") — including a `Vault__Client_Too_Old_Error` from `load_branch_index` at L185 and a `Vault__Unreadable_Ref_Error`-type situation (an undecryptable ref raises inside `json.loads(decrypt(...))` → swallowed → the switch proceeds with no fetch). Contrast pull, which refuses an unreadable server ref (F9).
6. L204-L205: `require_signatures(directory, c, read_key, head, held)` — **outside** the `try`, so a refusal propagates (`Vault__Signature_Error`).
7. L206-L211: if the head object is local, write `bare/refs/<ref_id>` with the server's exact bytes (plain `open`, no reflog) and `_write_remote_baseline`.

**Assumes:** the policy is read from the clone's **local** index (via `require_signatures` L27-L30) — nothing in this function refreshes the index first. Whether `Vault__Branch_Switch.switch`/`branch_list` refreshed it earlier was not traced.

**Cross-Function Dependencies:** callers — `Vault__Sync.switch_branch` (not read; the test `test_N2__switch_to_a_never_fetched_branch_refuses_an_unsigned_head` drives it and asserts the working copy and local ref are untouched on refusal). Callees as above.

**Open Questions:**
- unclear; the `except Exception: return` at L202-L203 makes an undecryptable or 403'd server ref indistinguishable from "offline" for a switch (pull distinguishes them, F9). The switch then checks out whatever the clone already has for that branch (nothing, if never fetched).
- unclear; whether the index is refreshed before this call (policy freshness, as noted in `require_signatures`).
