## `_clone_with_keys` in sgit_ai/core/actions/clone/Vault__Sync__Clone.py (L85-L137)

**Purpose:** The full (writable) clone: builds `Workflow__Clone` (12 steps) and runs it. Every check and every write of a clone lives in the steps, in this order (`Workflow__Clone.py:L24-L37`): derive keys → check directory → download index → download branch meta → bulk fetch → walk commits → walk trees → download blobs → **verify signatures** → create clone branch → extract working copy → setup local config (vault key + config written **last**).

**Inputs & Assumptions:**
- `vault_key` (str): `passphrase:vault_id`, prefix already stripped by the CLI. Trust: user input; it is **the** secret. Wrapped as `Safe_Str__Vault_Key` (L103) into the workflow state, which is JSON-serialised into the workflow workspace under `tmp` (`Workflow__Workspace`, manifest/state files — see Open Questions).
- `directory`, `sparse`, `depth`, `scope_paths`.
- Implicit: `self.api` (base URL and token were resolved by the CLI, `CLI__Vault.cmd_clone` L210-L214).

**Outputs & Effects:**
- A new vault directory with `.sg_vault/bare/*`, `.sg_vault/local/{config.json, vault_key, <key>.pem, pending_registration.json}` and a working copy — all written by steps.
- `tmp` (`/tmp/sgit-clone-*`) holds the workflow workspace while running; removed in `_run_clone_workflow`'s `finally` (L62-L66).
- Returns a dict that **includes `vault_key`** (L128) — the caller (`CLI__Vault.cmd_clone`) does not print that field, but any other caller gets the secret back in a plain dict.
- Exceptions from steps propagate with their type (`Workflow__Runner.py:L126-L130`); `FileNotFoundError` for a refused object is translated to `Vault__Integrity_Error` (L57-L61).

**Order of checks before each clone write (traced through the steps):**
1. `Step__Clone__Download_Index` (L34-L77): server index saved via `workspace.save_file` (`Vault__Verified_Write`; an index is not content-addressed so the only check is `is_store_path`, L55), parsed with the gate applied (`_try_use_present_index` L89-L112: `Vault__Client_Too_Old_Error` is "the one thing never degraded around", L101-L102; any other parse failure degrades to the single-branch fallback, L103-L104). **A fresh clone takes whatever gate and policy the host serves** (threat model §5 Format-gate row: "a fresh clone takes whatever the host serves").
2. Steps 4-8: refs, commits, trees, blobs, keys downloaded through `Clone__Workspace.save_file` (L53-L69) → `Verified_Write.save`; refused objects are recorded in `integrity_failures` and reported by `_warn_integrity_fallbacks` (L18-L37).
3. `Step__Clone__Verify_Signatures` (L24-L71): under `signatures-required`, `verify_chain` from the head down to the recorded anchor (or head-only when none is recorded, L61); any failure raises **before** "the clone registers a branch or writes a file" (docstring L5-L6). The read-only clone runs the same step (`Workflow__Clone__ReadOnly.py:L32`).
4. `Step__Clone__Create_Clone_Branch` (L16-L61): generates this clone's signing key pair, writes the public key to `bare/keys/` and the private key to `local/<id>.pem` (0600 via `Vault__Secret_File`), writes the clone ref ← named head (L34-L36), appends to the local index (L38-L41), writes `pending_registration.json` (L44-L54, plain write then chmod 0600).
5. `Step__Clone__Extract_Working_Copy` (L14-L45): checkout; a HEAD file whose blob is absent/refused fails the clone (`_refuse_incomplete` L47-L60) — so a clone never silently drops a file.
6. `Step__Clone__Setup_Local_Config` (L14-L38): `config.json` (with `last_remote_head = named_commit_id`, L30 — the first baseline) and **`local/vault_key`** (L35-L36, `write_private` → `Vault__Secret_File`, 0600, prefixed form). Because the key file is written last, a refused clone leaves no key on disk (the `_refuse_incomplete` message says so, L57).

**Cross-Function Dependencies:**
- Callees: `_run_clone_workflow` (L44-L66), `_normalised_scope` (L139-L141), the 12 steps.
- Callers: `clone` (L8-L16) ← `Vault__Sync.clone` ← `CLI__Vault.cmd_clone` L291 and `_offer_clone_recovery` L117.
- Tests: `tests/security/test_Security__Fixed__Trust_And_Policy.py::test_TM_R04__clone_refuses_an_unsigned_head`, `::test_TM_R04__clone_refuses_an_unsigned_commit_under_a_signed_head`, `::test_K3__every_clone_entry_point_checks_signatures`, `tests/security/test_Security__Fixed__Symlinks_And_Local.py::test_clone_and_read_only_clone_write_their_keys_owner_only`.

**Open Questions:**
- unclear; whether `Workflow__Workspace` persists the step input/output state (which carries `vault_key` and `read_key_hex`) to files under `tmp` (`ws.write_manifest`, `Workflow__Runner.py:L97, L116`). If it does, the secret is on disk in `/tmp/sgit-clone-*` for the duration of the clone, removed by `shutil.rmtree(tmp_root, ignore_errors=True)` (L66). Not read in this pass: `sgit_ai/workflow/Workflow__Workspace.py`.
- unclear; the result dict returning `vault_key` (L128) — whether any caller logs or serialises it.
