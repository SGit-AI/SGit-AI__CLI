## `create_named_branch` in sgit_ai/storage/Vault__Branch_Manager.py (L24-L47)

```python
# L27-L47
if timestamp_ms is None: timestamp_ms = int(time.time() * 1000)
branch_id   = 'branch-named-' + secrets.token_hex(8)
ref_id      = head_ref_id or ('ref-pid-muw-' + secrets.token_hex(6))
pub_key_id  = 'key-rnd-imm-' + self.key_manager.generate_key_id()
_private_key, public_key = self.key_manager.generate_branch_key_pair()
self.key_manager.store_public_key(pub_key_id, public_key, read_key)
# The private half is deliberately NOT stored. (L36-L39)
meta = Schema__Branch_Meta(branch_id=..., name=name, branch_type=NAMED, head_ref_id=ref_id, public_key_id=pub_key_id, created_at=timestamp_ms)
return meta
```

**Purpose:** Mint a named branch's metadata and its public key file. Since 10/09 the named branch's private key is generated and discarded (L36-L39; TM-R02 fix), so no read-key holder can sign "as the branch"; commits are signed by the writing clone's own key.

**Inputs & Assumptions:** `directory` unused in the body (the key manager uses its own `vault_path`); `name` → `Safe_Str__Branch_Name` (strict `^[a-zA-Z0-9_\-]{1,64}$`, raises on anything else — the CLI validates before, not checked here); `read_key` for encrypting the public key file; `head_ref_id` optional override (`Vault__Sync.init` L78 passes the HMAC-derived ref so the named ref is deterministic; `Vault__Branch_Switch.branch_create` L219 passes none → random `ref-pid-muw-<12 hex>`).

**Outputs & Effects:** Writes `bare/keys/key-rnd-imm-<16 hex>` (plain `open('wb')`, `Vault__Key_Manager.store_public_key` L24-L31) with the PEM public key encrypted under the read key. Returns the meta; the caller must add it to the index and write the ref (`Vault__Sync.py:L78-L111`, `Vault__Branch_Switch.py:L219-L240`). `_private_key` is dropped at function return — it lives in memory until then (the `cryptography` object; no explicit zeroisation, which Python cannot guarantee anyway).

**Cross-Function Dependencies:** `Vault__Key_Manager.generate_key_id` L21-L22 (`secrets.token_hex(8)`), `generate_branch_key_pair` L18-L19 → `PKI__Crypto.generate_signing_key_pair` L24-L26 (P-256), `store_public_key` L24-L31. Callers: `Vault__Sync.init` L78, `Vault__Branch_Switch` L219. Tests: `tests/unit/sync/test_Vault__Branch_Manager.py::test_create_named_branch`; `tests/security/test_Security__Known_Gaps.py::test_TM_R27__a_legacy_named_private_key_stays_readable_until_the_vault_is_moved` (older vaults still hold one).

**Open Questions:** none.
