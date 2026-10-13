## `execute` / `_try_use_present_index` / `_fallback_single_branch` in sgit_ai/workflow/clone/Step__Clone__Download_Index.py (L34-L77, L89-L112, L114-L154)

**Purpose:** Clone step 3: the first server data a fresh clone accepts — the branch index (gate, policy, branch→key map, tags). There is no earlier local state to compare with.

**Order and checks:**
- L46-L47: `batch_read(bare/indexes/<id>)`. The id is HMAC-derived from the read key (`Vault__Crypto.derive_branch_index_file_id` L154-L156), so the host must serve the file under that name.
- L55: `workspace.save_file(sg_dir, index_fid, bytes)` — `Verified_Write.save`: `is_store_path` (regex + not protected) passes for `bare/indexes/x`; `classify` returns VERIFIED for a non-content-addressed id without checking anything (L54-L55 of Verified_Write). So the index bytes are **written before being decrypted** (L55 then L56-L57).
- L99-L104 `_try_use_present_index`: `load_branch_index` → decrypt (AES-GCM authenticates: a host-forged index fails here) → `Vault__Index_Reader.parse` → `check_client` (gate; `Vault__Client_Too_Old_Error` propagates, L101-L102). Any other exception ⇒ degrade to the single-branch fallback (L103-L104) — the undecryptable index file **stays on disk** under `bare/indexes/<id>` and the fallback then **overwrites it** with a synthesised index (`save_branch_index`, L150-L151).
- L106-L112: `obj_store.id_hex_len` from the index; branch `'current'` must exist.
- `_fallback_single_branch` (L114-L154): reads `bare/refs/ref-pid-muw-<hmac>` (must exist, else "Nothing to clone" L131-L141), synthesises `Schema__Branch_Index(branches=[current])` with **no gate fields and no features** and saves it locally (L150-L151).

**Assumes:** a fresh clone trusts the server's index as the owner's latest (threat model §5: "a fresh clone takes whatever the host serves"). The degrade path means a host that serves an index this client cannot parse (other than the gate error) produces a clone **with no `signatures-required` policy and format 1** — `Step__Clone__Verify_Signatures` then finds no feature (L38-L39) and returns. The index file written by the fallback carries none of the server's fields; a later pull's `_refresh_index` would merge the server copy back in (gate from remote, `Vault__Index_Sync.merge` L95-L100) — if the server copy parses then.

**Cross-Function Dependencies:** callees `Vault__API.batch_read`, `Clone__Workspace.save_file`, `Vault__Branch_Manager.load_branch_index` / `save_branch_index`, `Vault__Index_Reader.warn_new` (L105). Callers: `Workflow__Clone` L27, `__ReadOnly` L26.

**Open Questions:**
- unclear; whether "index present but unusable → single-branch fallback" should bypass the signature policy for a fresh clone (it does, by construction: no features survive). The interop reason (web-UI vaults, foreign schema) is documented at L8-L17; the policy consequence is not.
