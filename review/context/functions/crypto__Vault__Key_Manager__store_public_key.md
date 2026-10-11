## `store_public_key` in sgit_ai/crypto/Vault__Key_Manager.py (L24-L31)

```python
# L25-L31
pem  = self.pki.export_public_key_pem(public_key)
data = json.dumps({'type': 'public', 'pem': pem}).encode()
ciphertext = self.crypto.encrypt(read_key, data)
path = self._key_path(key_id)
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'wb') as f:
    f.write(ciphertext)
```

**Purpose:** Writes a branch's public signing key to `.sg_vault/bare/keys/<key_id>` as a read-key-encrypted JSON `{type:'public', pem}`. This file is later pushed to the host (`Vault__Sync__Push._ensure_public_key` L928-L931) and is what every teammate uses to verify this branch's commits (`Vault__Signatures.py:L38`).

**Inputs & Assumptions:**
- `key_id` (str): `'key-rnd-imm-' + token_hex(8)` from `Vault__Branch_Manager.py:L32,L58`. Trust: trusted at these call sites. `_key_path` does `os.path.join(vault_path, 'bare/keys', key_id)` with no shape check (L78-L79); the shape `^key-rnd-imm-[0-9a-f]{8,64}$` is enforced elsewhere (`Safe_Str__Key_Id`, `Vault__Key_Fetch.py:L33`).
- `public_key`: just generated (L21-L22).
- `read_key` (bytes): the vault read key.
- Implicit: `self.vault_path` — a `Safe_Str__Vault_Path` (L14), see the accessors record for the sanitising rule.

**Outputs & Effects:**
- File write with plain `open(..., 'wb')` (umask mode, not 0600). The content is a PUBLIC key encrypted under the read key, so file mode is not a secrecy boundary here; the encryption keeps the host from learning the key's existence/identity.
- `os.makedirs` creates `bare/keys` if missing.
- Not atomic (no temp+rename): an interrupted write leaves a truncated file that `decrypt` later rejects.

**Block-by-Block:** L25-L26 serialise with a `type` tag; L27 encrypt; L28-L31 write.

**Cross-Function Dependencies:**
- Callees: `export_public_key_pem` (`PKI__Crypto.py:L30-L34`), `encrypt` (`Vault__Crypto.py:L294-L299`, random IV, no AAD → TM-R03 "swapping two key files makes signatures fail"), `_key_path` (L78-L79).
- Callers: `Vault__Branch_Manager.create_named_branch` L35, `create_clone_branch` L62; tests' adversary (`tests/_helpers/vault_adversary.py:L123`) uses it to mint a key as a read-key holder (TM-R01).
- Shared state: `bare/keys/` is also written directly by `Vault__Key_Fetch.fetch_missing` (L47-L50: host-served blobs, accepted after `_is_public_key` decrypts and finds `type == 'public'`).
- Invariant: the `type` tag is what `_is_public_key` (L57) and `Step__Move__Build_Temp_Vault._drop_shared_private_keys` rely on to tell public from legacy private files.

**Open Questions:** none.
