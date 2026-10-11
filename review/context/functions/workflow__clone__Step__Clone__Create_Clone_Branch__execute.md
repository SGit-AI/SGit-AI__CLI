## `execute` in sgit_ai/workflow/clone/Step__Clone__Create_Clone_Branch.py (L16-L61)

**Purpose:** Register this clone's own branch: a fresh ECDSA P-256 key pair, the clone ref pointed at the named head, the index entry (locally; pushed to the server on first push via `pending_registration.json`).

**Inputs & Assumptions:** `index_id`, `named_commit_id`, `named_branch_id`, `read_key`. Runs **after** `Step__Clone__Verify_Signatures` (`Workflow__Clone.py:L33-L34`).

**Outputs & Effects (all local):**
- `Vault__Branch_Manager.create_clone_branch` (L28-L32 → `Vault__Branch_Manager.py:L49-L74`): random `branch_id`, `ref_id`, `pub_key_id` (`secrets.token_hex`); **public key** encrypted under the read key to `bare/keys/<id>` (L62; `store_public_key` plain `open`); **private key** PEM to `local/<id>.pem` via `Vault__Secret_File` (L65 → `store_private_key_locally`, `Vault__Key_Manager.py:L56-L61`). The private key is never stored under the read key (threat model §2 "Named-branch signing key: no longer stored").
- `write_ref(clone ref, named_commit_id)` (L34-L36): the clone branch starts at the verified head.
- Index: append + `save_branch_index` (L38-L41; re-encrypts the whole index locally; the server copy is untouched until push).
- `pending_registration.json` (L44-L54): plain `open('w')` then `chmod_local_file` (0600) — the only `.sg_vault/local/` file in this step not written through `Vault__Secret_File`; it holds ids, not key material.

**Assumes:** the named head was verified by the previous step when the policy is on; nothing here re-checks.

**Cross-Function Dependencies:** callers `Workflow__Clone` L34 only (RO clones have no clone branch). Readers: push registers the branch from `pending_registration.json` (not read).

**Open Questions:** none.
