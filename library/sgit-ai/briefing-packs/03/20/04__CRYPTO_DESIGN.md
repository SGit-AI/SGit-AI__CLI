# 04 — Cryptographic Design

**Author:** Architect
**Audience:** Security reviewers, Architects

## Zero-Knowledge Architecture

The server is a **dumb key-value store**. It never receives:
- Plaintext file contents
- File names or directory structure
- Commit messages
- Branch names
- Encryption keys or passphrases

```
  USER SIDE (trusted)              SERVER SIDE (untrusted)
  ====================             =======================

  passphrase:vault_id              vault_id (public)
       |                                |
       v                                v
  PBKDF2(600K iterations)          opaque blob storage
       |                           {vault_id}/{file_id} -> bytes
       v
  read_key (32 bytes AES)
  write_key (32 bytes)
       |
       v
  AES-256-GCM encrypt
       |
       v
  ciphertext ----upload---->  stored as-is
```

## Key Derivation Chain

```
  vault_key = "my-secret-passphrase:abc12345"
                |                      |
                v                      v
           passphrase              vault_id
                |                      |
                +----------+-----------+
                           |
                           v
           PBKDF2-SHA256(passphrase, "sg-vault-v1:{vault_id}")
           iterations = 600,000
           key_length = 32 bytes
                           |
                           v
                      read_key (32 bytes)
                      Used for: AES-GCM encrypt/decrypt of ALL vault data
                           |
                           |
           PBKDF2-SHA256(passphrase, "sg-vault-v1:write:{vault_id}")
                           |
                           v
                      write_key (32 bytes, hex-encoded for API header)
                      Used for: server-side write authorization


  read_key + domain strings
       |
       +-- HMAC-SHA256(read_key, "sg-vault-v1:file-id:ref:{vault_id}")[:12]
       |   -> ref_file_id (where to store named branch HEAD)
       |
       +-- HMAC-SHA256(read_key, "sg-vault-v1:file-id:branch-index:{vault_id}")[:12]
       |   -> branch_index_file_id (where to store branch index)
       |
       +-- HMAC-SHA256(read_key, "sg-vault-v1:file-id:branch-ref:{vault_id}:{name}")[:12]
           -> branch ref file IDs (per-branch HEAD locations)
```

## Encryption Primitives

### AES-256-GCM (Primary Encryption)

Used for all data encryption: blobs, commits, trees, refs, branch indexes, metadata.

```
encrypt(key, plaintext):
    iv         = random(12 bytes)        # GCM_IV_BYTES = 12
    ciphertext = AES-GCM(key, iv, plaintext, aad=None)
    return iv || ciphertext              # 12 + len(plaintext) + 16 (tag)

decrypt(key, data):
    iv         = data[:12]
    ciphertext = data[12:]
    return AES-GCM-decrypt(key, iv, ciphertext, aad=None)
```

**Constants:**
- `AES_KEY_BYTES = 32` (256-bit key)
- `GCM_IV_BYTES = 12` (96-bit IV, standard for GCM)
- `GCM_TAG_BYTES = 16` (128-bit authentication tag)

### PBKDF2-SHA256 (Key Derivation from Passphrase)

```
derive_key(passphrase, salt):
    return PBKDF2(
        algorithm  = SHA256,
        length     = 32 bytes,
        salt       = salt,
        iterations = 600,000
    )
```

Salt formats:
- Read key:  `"sg-vault-v1:{vault_id}"`
- Write key: `"sg-vault-v1:write:{vault_id}"`

### HKDF-SHA256 (File-Level Key Derivation)

```
derive_file_key(vault_key, file_context):
    return HKDF(
        algorithm = SHA256,
        length    = 32 bytes,
        salt      = None,
        info      = "sg-send-file-key" || file_context
    )
```

Currently reserved for future per-file key isolation. Not actively used for vault
objects (vault read_key is used directly).

### Content Hashing

```
content_hash(plaintext):
    return SHA256(plaintext)[:12]    # 12 hex chars = 48 bits
```

Used for change detection. Stored encrypted in tree entries (`content_hash_enc`).
The 48-bit truncation is a trade-off: collision resistance is ~2^24 (16M files),
which is sufficient for change detection within a single vault.

### Object ID Computation

```
compute_object_id(ciphertext):
    raw = SHA256(ciphertext)[:12]    # 12 hex chars
    return "obj-cas-imm-" + raw
```

**Important:** The hash is of the **ciphertext**, not the plaintext. This means the
server can verify object integrity without being able to decrypt the content.

## Metadata Encryption

Tree entries store file names, sizes, and content hashes encrypted:

```
encrypt_metadata(read_key, "hello.txt"):
    plaintext  = "hello.txt".encode('utf-8')
    ciphertext = AES-GCM(read_key, random_iv, plaintext)
    return base64_encode(iv || ciphertext)

decrypt_metadata(read_key, base64_string):
    ciphertext = base64_decode(base64_string)
    return AES-GCM-decrypt(read_key, ciphertext).decode('utf-8')
```

This ensures the server cannot see file names, sizes, or structure.

## PKI Layer

### Branch Signing (ECDSA P-256)

Each branch has an EC P-256 key pair:
- **Public key** — stored in `bare/keys/` (encrypted), shared with all clones
- **Private key** — stored in `local/keys/` (PEM, never synced)

Commits are signed by the creating branch's private key:

```
commit_data = JSON(commit_without_signature)
signature   = ECDSA-P256-SHA256(private_key, commit_data)
commit.signature = base64(signature)
```

### User PKI (RSA-4096 + ECDSA P-256)

For file-level signing and encryption between users:
- `pki keygen` — generates RSA-4096 (encryption) + ECDSA P-256 (signing)
- `pki sign/verify` — detached ECDSA signatures
- `pki encrypt/decrypt` — RSA-OAEP encryption

## Browser Interop Requirement

All crypto operations must produce output that matches the **Web Crypto API**
byte-for-byte given the same inputs:

```
Python: AES-GCM(key, iv, plaintext) == Browser: crypto.subtle.encrypt({name:'AES-GCM', iv}, key, plaintext)
```

This is critical because vaults may be opened in both the CLI and the browser.
Test vectors are mandatory for any crypto changes.

## Threat Model Summary

| Threat                        | Mitigation                                   |
|-------------------------------|----------------------------------------------|
| Server compromise             | All data encrypted client-side (AES-256-GCM) |
| Server reads file names       | Names encrypted in tree entries               |
| Server reads commit messages  | Messages encrypted (message_enc)              |
| Brute-force passphrase        | PBKDF2 with 600K iterations                  |
| Replay/tampering              | GCM authentication tag (128-bit)             |
| Object substitution           | CAS: ID = hash(ciphertext)                   |
| Unauthorized writes           | write_key derived separately, sent as header  |
| Commit forgery                | ECDSA P-256 signature per branch             |
