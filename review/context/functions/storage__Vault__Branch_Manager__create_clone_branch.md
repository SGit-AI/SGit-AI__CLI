## `create_clone_branch` in sgit_ai/storage/Vault__Branch_Manager.py (L49-L74)

```python
# L53-L74
branch_id  = 'branch-clone-' + secrets.token_hex(8)
ref_id     = head_ref_id or ('ref-pid-snw-' + secrets.token_hex(6))
pub_key_id = 'key-rnd-imm-' + self.key_manager.generate_key_id()
private_key, public_key = self.key_manager.generate_branch_key_pair()
self.key_manager.store_public_key(pub_key_id, public_key, read_key)
local_dir = self.storage.local_dir(directory)
self.key_manager.store_private_key_locally(pub_key_id, private_key, local_dir)
meta = Schema__Branch_Meta(..., branch_type=CLONE, ..., creator_branch=creator_branch_id)
return meta
```

**Purpose:** Mint this clone's own branch: a public key in the shared store and the private half **only** in `.sg_vault/local/<key_id>.pem` (threat model §2 "Clone signing keys (private)").

**Inputs & Assumptions:** as `create_named_branch`, plus `creator_branch_id` (the named branch this clone tracks, consumed by `tracked_named_branch`). `directory` is the raw user path (used for `local_dir`), while `key_manager.vault_path` is the sanitised one — the two-convention issue noted in `storage__Vault__Object_Store__object_path.md` applies: public key path vs. private key path may diverge on an exotic directory name.

**Outputs & Effects:** Writes `bare/keys/<id>` (plain open) and `local/<id>.pem` via `Vault__Key_Manager.store_private_key_locally` L56-L61 → `Vault__Secret_File.write` (0600 temp + rename; `# 0600, never through a link` L61). The PEM is PKCS8 **unencrypted** (`PKI__Crypto.export_private_key_pem` L36-L42, `NoEncryption()` when no passphrase — none passed).

**Cross-Function Dependencies:** Callers: `Vault__Sync.init` L81, `Vault__Branch_Switch` L97, L226, `Step__Clone__Create_Clone_Branch` L28. Tests: `tests/unit/sync/test_Vault__Branch_Manager.py::test_create_clone_branch`; `tests/security/test_Security__Fixed__Symlinks_And_Local.py::test_clone_and_read_only_clone_write_their_keys_owner_only`.

**Open Questions:** none.
