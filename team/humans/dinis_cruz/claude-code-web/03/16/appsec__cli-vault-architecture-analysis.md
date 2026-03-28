# AppSec Analysis — sg-send-cli & Vault Architecture

**Date:** 2026-03-16
**Analyst:** AppSec Agent (Claude)
**Scope:** Full client + server API surface, crypto model, data flow, threat model
**Version:** v0.8.2

---

## 1. Executive Summary

sg-send-cli implements a zero-knowledge encrypted vault system where all plaintext is encrypted client-side before touching the network. The crypto primitives (AES-256-GCM, PBKDF2-SHA256, HKDF-SHA256, ECDSA P-256) are industry-standard and correctly applied. Existing AppSec tests verify encryption-at-rest, key separation, and tamper detection.

However, the **server API surface** exposes several design properties that create real attack vectors — not because the crypto is broken, but because of **what the API allows unauthenticated or with partial credentials**. This analysis focuses heavily on those.

**Risk Rating:** The cryptographic core is **strong**. The API authorization model has **medium-severity gaps** that need attention before production.

---

## 2. Server API Surface — What Is Actually Exposed

### 2.1 Vault API Endpoints

| Endpoint | Method | Auth Required | What It Does |
|----------|--------|---------------|-------------|
| `/api/vault/read/{vault_id}/{file_id}` | GET | **NONE** | Download any vault file by ID |
| `/api/vault/list/{vault_id}` | GET | **NONE** | List all file IDs in a vault |
| `/api/vault/write/{vault_id}/{file_id}` | PUT | Token + Write Key | Write/overwrite a vault file |
| `/api/vault/delete/{vault_id}/{file_id}` | DELETE | Token + Write Key | Delete a vault file |
| `/api/vault/batch/{vault_id}` | POST | Token + Write Key | Atomic batch write/delete |

### 2.2 Transfer API Endpoints

| Endpoint | Method | Auth Required | What It Does |
|----------|--------|---------------|-------------|
| `/api/transfers/create` | POST | Token | Create a new transfer |
| `/api/transfers/upload/{id}` | POST | Token | Upload encrypted payload |
| `/api/transfers/complete/{id}` | POST | Token | Finalize transfer |
| `/api/transfers/info/{id}` | GET | **NONE** | Get transfer metadata |
| `/api/transfers/download/{id}` | GET | **NONE** | Download encrypted payload |
| `/api/transfers/download-base64/{id}` | GET | **NONE** | Download as base64 |
| `/api/transfers/check-token/{name}` | GET | **NONE** | Check if token exists |
| `/api/transfers/validate-token/{name}` | GET | **NONE** | Validate & consume token use |

### 2.3 Presigned/Large File API

| Endpoint | Method | Auth Required | What It Does |
|----------|--------|---------------|-------------|
| `/api/presigned/capabilities` | GET | **NONE** | Check S3 support status |
| `/api/presigned/initiate` | POST | Token | Start multipart upload |
| `/api/presigned/complete` | POST | Token | Finalize multipart |
| `/api/presigned/abort/{id}/{uid}` | POST | Token | Cancel multipart |
| `/api/presigned/upload-url/{id}` | GET | Token | Get presigned upload URL |
| `/api/presigned/download-url/{id}` | GET | **NONE** | Get presigned download URL |

---

## 3. Threat Model

### 3.1 Actors

| Actor | Capabilities | Goal |
|-------|-------------|------|
| **Passive Network Observer** | Can see TLS metadata (IP, timing, sizes) | Metadata analysis, traffic correlation |
| **Unauthenticated Attacker** | Can call any endpoint marked "NONE" above | Enumerate vaults, download ciphertexts, metadata harvesting |
| **Token Holder (no vault key)** | Has access token but not the passphrase | Create transfers, write garbage to vault IDs, denial of service |
| **Write Key Holder** | Has write key but not read key | Overwrite/delete vault objects (destructive), can't decrypt |
| **Full Key Holder (compromised)** | Has vault key (passphrase + vault_id) | Full read/write/decrypt — game over for that vault |
| **Malicious Server Operator** | Controls the API server | Serve stale data, drop writes, metadata analysis, storage-level DoS |

### 3.2 Trust Boundaries

```
┌─────────────────────────────────────────────────────────┐
│  CLIENT (trusted zone)                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Vault__Sync │→ │ Vault__Crypto│  │ PKI__Crypto   │  │
│  │ (plaintext) │  │ (keys, enc)  │  │ (sign/verify) │  │
│  └──────┬──────┘  └──────────────┘  └───────────────┘  │
│         │ encrypted only                                │
│  ┌──────▼──────┐                                        │
│  │  Vault__API │  ← TLS envelope                        │
│  └──────┬──────┘                                        │
├─────────┼───────────── TRUST BOUNDARY ──────────────────┤
│         ▼                                               │
│  ┌─────────────────────────────────────────┐            │
│  │  SG/Send Server (untrusted for content) │            │
│  │  - Stores opaque ciphertext             │            │
│  │  - Validates write_key hash             │            │
│  │  - Validates access token               │            │
│  │  - CAN see: vault_id, file_id, sizes   │            │
│  │  - CANNOT see: plaintext, filenames     │            │
│  └─────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Findings

### FINDING 1 — Unauthenticated Read Access to All Vault Data [MEDIUM]

**Endpoints:** `GET /api/vault/read/{vault_id}/{file_id}`, `GET /api/vault/list/{vault_id}`

**Issue:** Anyone who knows (or guesses) a `vault_id` can:
1. **List all file IDs** in the vault via `/api/vault/list/{vault_id}`
2. **Download every encrypted object** via `/api/vault/read/{vault_id}/{file_id}`

**Why this matters:**
- Vault IDs are 8 hex characters = 4.3 billion possibilities. This is enumerable at scale with no rate limiting.
- The vault ID is embedded in the shareable vault key (`passphrase:vault_id`) and in URLs.
- Once an attacker has the ciphertexts, they can mount offline brute-force against the passphrase at their leisure.
- The file ID list leaks structural metadata (number of files, naming patterns like `bare/data/obj-*`, `bare/refs/ref-*`).

**Attack scenario:**
1. Attacker enumerates vault IDs (brute force or leaked from URLs/logs)
2. Downloads all ciphertexts for a target vault
3. Mounts offline PBKDF2 brute-force (600k iterations helps, but doesn't stop state-level actors or weak passphrases)

**Mitigations already in place:**
- PBKDF2 with 600k iterations raises cost (~1ms per guess on modern hardware)
- AES-256-GCM provides authenticated encryption
- Object IDs are SHA-256 hashes of ciphertext (don't leak plaintext info)

**Recommended mitigations:**
- **Server-side rate limiting** on `/api/vault/list` and `/api/vault/read` — cap reads per IP per vault per minute
- **Require read_key_hash for list operations** — similar to how writes require write_key, list should require a read-side proof
- **Increase vault_id entropy** — 8 hex chars (32 bits) is low; consider 16+ chars (64+ bits)
- **Monitor and alert** on bulk download patterns

**Severity:** MEDIUM — Encryption is the real defense, but unauthenticated access to ciphertexts enables offline attacks.

---

### FINDING 2 — Vault ID Enumeration [MEDIUM]

**Endpoint:** `GET /api/vault/list/{vault_id}`

**Issue:** The list endpoint returns an empty list (not 404) for non-existent vault IDs, and returns file IDs for existing ones. This is an oracle that confirms vault existence.

**Attack scenario:**
1. Attacker scripts calls to `/api/vault/list/{candidate_id}` for all 8-hex-char IDs
2. Non-empty responses confirm vault existence
3. Confirmed vaults become targets for Finding 1

**Impact:** With 8 hex characters (16^8 = ~4.3B combinations), a distributed enumeration could find all active vaults. At 1000 req/sec, full enumeration takes ~50 days — feasible for a motivated attacker.

**Recommended mitigations:**
- **Rate limit** the list endpoint (already mentioned above)
- **Return identical responses** for existing-empty and non-existent vaults
- **Increase vault_id length** to make enumeration computationally infeasible

---

### FINDING 3 — Write Key Is Independent but Deterministic [LOW]

**Design property:** `write_key = PBKDF2(passphrase, "sg-vault-v1:write:{vault_id}", 600k)`

**Good:** The write key is derived with a different salt than the read key, so compromising one doesn't directly reveal the other.

**Concern:** Both keys derive from the same passphrase. If the passphrase is weak, both are weak. There's no option for separate read-only vs. read-write passphrases.

**Impact:** This is a design trade-off (single vault key simplicity), not a vulnerability. But it means vault sharing is all-or-nothing: you can't give someone read access without also giving them write access.

**Recommendation:** Consider a future "read-only vault key" that derives only the read key, for sharing scenarios where recipients shouldn't be able to modify the vault.

---

### FINDING 4 — Push Silent Failure on Remote Write Error [HIGH]

**Code:** `Vault__Sync.py` push path, `Vault__Batch.py` fallback path

**Issue:** When the batch API call fails, the CLI falls back to individual writes. But the individual write path (`execute_individually`) does not check API response status codes beyond HTTP errors. If the server accepts the request but silently drops the write (e.g., storage full, partial failure), the CLI reports success.

**Impact:** **Data loss.** The user believes their push completed, but some or all objects were not persisted. On the next clone or pull from another machine, the data is missing.

**Evidence:** This is already tracked as an xfail test: `test_push_with_write_failure_raises`.

**Recommendation:**
- After batch or individual push, **verify** that the ref was updated by re-reading it from the server
- Return the list of written file IDs in the API response and cross-check against expected operations
- Treat any discrepancy as a push failure

---

### FINDING 5 — No Server-Side Integrity Verification [MEDIUM]

**Issue:** The server stores opaque ciphertext and has no way to verify that:
1. The data written is actually valid AES-256-GCM ciphertext
2. The data hasn't been corrupted in transit
3. The data matches any claimed content hash

**Attack scenario (malicious writer):**
1. Attacker obtains write key (from compromised vault key)
2. Writes garbage data to `bare/data/obj-*` paths
3. Other users pull and get decryption failures — **denial of service against the vault**

**Attack scenario (malicious server):**
1. Server operator replaces a ciphertext blob with a different one
2. Client decrypts and gets garbage (GCM tag check fails) or a *different valid ciphertext* from another vault

**Mitigations already in place:**
- AES-GCM authentication tag detects random corruption
- Object IDs are SHA-256 of ciphertext — client can verify `hash(downloaded) == expected_id`

**Gap:** The client does NOT currently verify object integrity on download. `Vault__Object_Store.load()` reads the file but doesn't check that `compute_object_id(data) == file_id`.

**Recommendation:**
- **Verify object integrity on every download** — `assert compute_object_id(data) == expected_id`
- This is a one-line fix with high security value
- Protects against both server tampering and storage corruption

---

### FINDING 6 — CAS (Compare-and-Swap) Only on Named Ref [LOW]

**Code:** `Vault__Batch.py:62-67`

**Issue:** The `write-if-match` CAS operation is only applied to the named branch ref (`bare/refs/{named_ref_id}`). All other operations (blob writes, commit writes, tree writes) use plain `write` with no CAS.

**Why it's mostly OK:** Content-addressed objects are immutable — writing the same object twice is idempotent. The CAS on the ref prevents lost updates.

**Gap:** The browser-compatible dual-write at line 73 uses plain `write` (no CAS) for the HMAC-derived ref path. If two pushes race, the browser-facing ref could point to a different commit than the CLI-facing ref.

**Recommendation:**
- Apply CAS to the browser-compatible ref write as well
- Or ensure both ref writes are in the same atomic batch (they already are, but without CAS on the second)

---

### FINDING 7 — Token Stored in Plaintext on Disk [LOW]

**Code:** `CLI__Token_Store.py` — saves token to `.sg_vault/token` as plain text

**Issue:** The access token is stored unencrypted in the vault's `.sg_vault/token` file. Anyone with filesystem access to the vault directory can read the token.

**Mitigations:**
- The token alone is not sufficient for destructive operations (also needs write key)
- The token is a session/access credential, not a long-lived secret
- The vault key (which IS the real secret) is stored similarly in `.sg_vault/local/vault_key`

**Recommendation:**
- Document that the `.sg_vault/` directory should have restrictive permissions (700)
- Consider encrypting the token at rest using the vault's read key
- Mark `.sg_vault/` as a sensitive directory in any gitignore/backup exclusion

---

### FINDING 8 — HMAC-Derived File IDs Use Truncated Hashes [LOW]

**Code:** `Vault__Crypto.py:42-44` — `hmac.hexdigest()[:12]` = 48 bits

**Issue:** File IDs derived via HMAC-SHA256 are truncated to 12 hex characters (48 bits). Within a single vault this is unlikely to collide, but:
- 48-bit collision resistance means ~2^24 (~16M) files before birthday-bound collision
- Cross-vault collisions are irrelevant (different vault_id = different HMAC domain)

**Impact:** Negligible for normal usage. Would only matter for extremely large vaults.

**Recommendation:** No action needed for current scale. Document the limit.

---

### FINDING 9 — Object ID Collision at 48 bits [LOW]

**Code:** `Vault__Crypto.py:62-63` — `sha256(ciphertext).hexdigest()[:12]` = 48 bits

**Issue:** Same truncation as Finding 8, but for content-addressed object IDs. With random IVs, each encryption produces a unique ciphertext, so collisions require ~16M objects in a single vault.

**Practical impact:** Low. But if two different ciphertexts happen to produce the same 48-bit prefix, one would silently overwrite the other.

**Recommendation:** Consider increasing to 16 hex chars (64 bits) in a future version. This would raise the collision bound to ~4 billion objects.

---

### FINDING 10 — No Replay Protection on Refs [MEDIUM]

**Issue:** The CAS mechanism (`write-if-match`) prevents concurrent writes but doesn't prevent **rollback attacks**. A malicious server or attacker with write access can:

1. Save the current ref ciphertext (pointing to commit N)
2. Allow a push to update the ref (now pointing to commit N+1)
3. Overwrite the ref with the saved ciphertext (rolling back to commit N)

**Impact:** The victim's next pull would see commit N as the latest, losing visibility of commit N+1. The objects for N+1 still exist on the server but are unreferenced.

**Mitigations:**
- Commit chains include parent pointers — a client that remembers its last-seen commit would detect the rollback
- But the CLI currently trusts the remote ref unconditionally during pull

**Recommendation:**
- During pull, verify that the remote commit is a **descendant** of the last-known local commit
- If the remote commit is an ancestor (rollback) or unrelated, warn the user
- This is partially implemented (divergence detection in `Vault__Fetch`) but not enforced as a security check

---

### FINDING 11 — No AAD (Additional Authenticated Data) in AES-GCM [LOW]

**Code:** `Vault__Crypto.py:107` — `aesgcm.encrypt(iv, plaintext, None)` — AAD is `None`

**Issue:** AES-GCM supports Additional Authenticated Data (AAD) which binds the ciphertext to a context (e.g., the file path, vault ID, or object ID). Without AAD, a ciphertext from one vault could theoretically be transplanted to another vault that uses the same key.

**Impact:** Very low in practice because:
- Each vault has a unique key derived from a unique passphrase + vault_id
- The same key is never used across vaults
- Object IDs are content-addressed, so transplanted objects would need matching hashes

**Recommendation:** Consider binding AAD to `vault_id + file_id` in a future protocol version. This is defense-in-depth, not a current vulnerability.

---

### FINDING 12 — Passphrase Entropy Not Enforced [MEDIUM]

**Code:** `Safe_Str__Vault_Passphrase.py` — allows any printable ASCII 1-256 chars

**Issue:** The CLI generates strong 24-character random passphrases for new vaults, but users can supply their own passphrase via `--vault-key`. There is no minimum entropy check on user-supplied passphrases.

**Attack scenario:**
1. User creates vault with weak passphrase: `password:a1b2c3d4`
2. Attacker enumerates vault (Finding 2), downloads ciphertexts (Finding 1)
3. Offline PBKDF2 brute-force at ~1000 guesses/sec (600k iterations per guess)
4. "password" is cracked in seconds from any dictionary

**Recommendation:**
- Warn users when they supply custom vault keys with low-entropy passphrases
- Consider a minimum passphrase length (e.g., 16 characters) for user-supplied keys
- Document that the auto-generated passphrase (24 chars, a-z0-9) provides ~124 bits of entropy

---

## 5. What the API Makes Possible — Capability Matrix

This section maps what each credential level can do through the exposed API:

### With NO credentials (anonymous):

| Action | Possible? | Via |
|--------|----------|-----|
| List file IDs in any vault | YES | `GET /api/vault/list/{vault_id}` |
| Download any encrypted object | YES | `GET /api/vault/read/{vault_id}/{file_id}` |
| Enumerate vault existence | YES | `GET /api/vault/list/{vault_id}` (empty vs populated) |
| Download any transfer | YES | `GET /api/transfers/download/{id}` |
| Get transfer metadata | YES | `GET /api/transfers/info/{id}` |
| Check token existence | YES | `GET /api/transfers/check-token/{name}` |
| Get presigned download URL | YES | `GET /api/presigned/download-url/{id}` |
| Decrypt anything | NO | Requires passphrase |
| Write/modify anything | NO | Requires token + write key |

### With access token only (no vault key):

| Action | Possible? | Via |
|--------|----------|-----|
| Everything above | YES | — |
| Create transfers | YES | `POST /api/transfers/create` |
| Upload data to transfers | YES | `POST /api/transfers/upload/{id}` |
| Write garbage to a vault (if guessing write key) | NO | Write key is 64 hex chars (256 bits) |
| Initiate multipart uploads | YES | `POST /api/presigned/initiate` |

### With access token + write key (but no read key):

| Action | Possible? | Via |
|--------|----------|-----|
| Everything above | YES | — |
| Write arbitrary data to vault | YES | `PUT /api/vault/write/{vault_id}/{file_id}` |
| Delete any file from vault | YES | `DELETE /api/vault/delete/{vault_id}/{file_id}` |
| Overwrite refs (rollback attack) | YES | batch or individual write |
| Decrypt anything | NO | Write key != read key |

### With full vault key (passphrase + vault_id):

| Action | Possible? | Via |
|--------|----------|-----|
| Everything above | YES | Derives both read + write keys |
| Decrypt all vault contents | YES | AES-256-GCM with read key |
| Create valid encrypted objects | YES | Encrypt with read key |
| Forge commits (unsigned) | YES | If no signing key required |
| Forge commits (signed) | NO | Requires ECDSA private key |

---

## 6. Crypto Assessment Summary

| Property | Status | Notes |
|----------|--------|-------|
| Encryption algorithm (AES-256-GCM) | STRONG | Industry standard, authenticated |
| Key derivation (PBKDF2, 600k iters) | STRONG | Meets OWASP 2024 recommendation |
| Per-file key derivation (HKDF) | STRONG | Proper domain separation |
| IV generation (12 bytes random) | STRONG | `os.urandom()`, no reuse |
| Tamper detection (GCM auth tag) | STRONG | Tested with hardening tests |
| Key separation (read vs write) | STRONG | Different PBKDF2 salts |
| Signature algorithm (ECDSA P-256) | STRONG | Web Crypto interop verified |
| Hybrid encryption (RSA-4096 + AES) | STRONG | Proper key wrapping |
| Secrets at rest | STRONG | AES-GCM with master key |
| Test coverage | STRONG | 975 unit tests, dedicated AppSec + hardening suites |

---

## 7. Prioritized Recommendations

### P0 — Fix Before Production

1. **Verify push actually persisted** (Finding 4) — Re-read the ref after push to confirm server-side state matches expectation. Currently the CLI can report "push successful" when data was silently dropped.

2. **Verify object integrity on download** (Finding 5) — Add `assert compute_object_id(downloaded_data) == expected_id` to every object download path. One-line fix, high value.

### P1 — Fix Before Public Launch

3. **Rate limit unauthenticated reads** (Finding 1) — Server-side rate limiting on `/api/vault/list` and `/api/vault/read` per IP.

4. **Increase vault_id entropy** (Finding 2) — Move from 8 hex chars (32 bits) to 16+ chars (64+ bits) to make enumeration infeasible. This is a breaking change for existing vaults, so plan a migration path.

5. **Rollback detection on pull** (Finding 10) — Verify remote ref is a descendant of last-known local commit. Warn on apparent rollback.

6. **Warn on weak user-supplied passphrases** (Finding 12) — At minimum, warn when passphrase is under 16 characters or appears in a common password list.

### P2 — Harden in Future Versions

7. **CAS on browser-compatible ref** (Finding 6) — Apply `write-if-match` to the HMAC-derived ref path.
8. **Bind AAD in AES-GCM** (Finding 11) — Future protocol version.
9. **Read-only vault keys** (Finding 3) — Separate sharing model.
10. **Encrypt token at rest** (Finding 7) — Defense-in-depth for `.sg_vault/` contents.

---

## 8. Existing Security Tests — Coverage Map

| Test Class | What It Verifies | Findings Covered |
|------------|-----------------|------------------|
| `Test_AppSec__No_Plaintext_In_Object_Store` | File contents encrypted before storage | Crypto correctness |
| `Test_AppSec__Vault_Key_Not_In_Object_Store` | Vault key never persisted as object | Key hygiene |
| `Test_AppSec__Secrets_Encrypted_At_Rest` | Secret store file is opaque ciphertext | Finding 7 (partial) |
| `Test_AppSec__Key_Derivation_Constants` | PBKDF2=600k, correct salts, read!=write, 32 bytes | Finding 3 |
| `Test_AppSec__Commit_Metadata_No_Sensitive_Data` | Commit objects don't contain keys | Key hygiene |
| `Test_AppSec__Tree_Structure_Encrypted` | Filenames encrypted in tree objects | Crypto correctness |
| `test_Vault__Crypto__Hardening` | IV corruption, ciphertext tampering, tag tampering, IV uniqueness | Finding 5, 11 |
| `test_PKI__Crypto__Hardening` | Signature truncation, corruption, wrong-key rejection | Crypto correctness |

### Gaps in AppSec Test Coverage

| Missing Test | Would Cover |
|-------------|-------------|
| Object integrity verification on download | Finding 5 |
| Push failure detection (remote write error) | Finding 4 |
| Rollback detection on pull | Finding 10 |
| Vault ID enumeration resistance | Finding 2 |
| Weak passphrase warning | Finding 12 |
| Cross-vault ciphertext transplant rejection | Finding 11 |

---

## 9. Architecture Strengths

1. **True zero-knowledge design** — Server never sees plaintext, filenames, or keys. Encryption is not optional.
2. **Key separation** — Read key, write key, file keys, signing keys, secrets master key all use distinct derivation paths with domain-separated salts.
3. **Content-addressed storage** — Objects are immutable and self-verifying (once the integrity check is added).
4. **Atomic batch operations with CAS** — Prevents lost updates on concurrent pushes.
5. **Commit chain with signatures** — ECDSA-signed commits provide non-repudiation and tamper evidence.
6. **Web Crypto interop** — Byte-for-byte compatibility with browser implementation, verified by test vectors.
7. **No mocks in tests** — All tests use real crypto primitives against real objects.

---

*End of analysis.*
