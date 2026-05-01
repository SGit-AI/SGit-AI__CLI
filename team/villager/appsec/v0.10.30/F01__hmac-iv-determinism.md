# F01 — Deterministic HMAC IV: Leakage Map & Residual Risks

**Severity:** MEDIUM (residual) — accepted by threat-model; documentation gap is the
real-fix-needed.
**Class:** Cross-vault correlation / structural side channel
**Disposition:** ACCEPTED-RISK / DOCUMENT-ONLY
**Files:** `sgit_ai/crypto/Vault__Crypto.py:162-176`,
`sgit_ai/sync/Vault__Sub_Tree.py:81-84,106,156-159,181,245`

## 1. The Construction Under Audit

```python
# sgit_ai/crypto/Vault__Crypto.py:162-170
def encrypt_deterministic(self, key: bytes, plaintext: bytes) -> bytes:
    iv = hmac.new(key, plaintext, hashlib.sha256).digest()[:GCM_IV_BYTES]
    return self.encrypt(key, plaintext, iv=iv)
```

`key` is the per-vault `read_key` (32-byte PBKDF2 derivative of
`(passphrase, "sg-vault-v1:"+vault_id)`). `plaintext` is one of:

| Caller | Plaintext input | Domain |
|--------|-----------------|--------|
| `encrypt_metadata_deterministic(filename)` | UTF-8 file/folder name | Tree entry name |
| `encrypt_metadata_deterministic(str(size))` | ASCII decimal size | Tree entry size |
| `encrypt_metadata_deterministic(content_hash)` | 12-hex sha256 prefix | Tree entry CAS hint |
| `encrypt_metadata_deterministic(content_type)` | MIME string | Tree entry MIME |
| `encrypt_deterministic(tree_json)` | Serialised tree JSON (encrypted bytes) | `_store_tree` |

## 2. AES-GCM Nonce Safety — Verified OK

AES-GCM IND-CPA security requires nonces never repeat **under the same key** with
**different plaintexts**. Because `iv = HMAC(read_key, plaintext)[:12]`:

- Same plaintext → same IV → same ciphertext (intended; CAS dedup).
- Different plaintexts → different IVs (with overwhelming probability:
  collision resistance of HMAC-SHA256 truncated to 96 bits ≈ 2^-48 per pair).
- A nonce-reuse oracle on AES-GCM requires identical IV + different plaintext.
  This construction makes that impossible *unless* HMAC-SHA256 is broken.

**No catastrophic AES-GCM failure mode is reachable from this construction.**
The 96-bit truncation is the standard HKDF-SIV-style choice; a birthday
collision after ~2^48 distinct plaintexts under one key is theoretically
possible but operationally irrelevant for a per-vault read_key.

## 3. Domain-Separation Justification — OK

`read_key` is used as both:
- AES-256-GCM key
- HMAC-SHA256 key (for IV derivation, file_id derivation, ref id derivation)

Re-using a 256-bit uniformly random key for AES and HMAC is the standard
"GCM-SIV-style" pattern (RFC 8452). HMAC's PRF security and AES's PRP security
are independent cryptographic assumptions; no academic break is known to follow
from this re-use. **No finding here**, but worth one paragraph in the spec.

## 4. Concrete Leakage Map (the actual finding)

A passive server (or anyone holding ciphertexts) **cannot decrypt** anything,
**cannot recover plaintext or keys**, and **cannot forge ciphertext**. But
they CAN observe these structural facts because the IV is deterministic in
the plaintext:

| What server can do | Mechanism | Implication |
|--------------------|-----------|-------------|
| Tell whether two tree entries (within one vault) hold the same filename | Equal `name_enc` ciphertexts | Folder structure churn visible |
| Tell whether two trees are byte-identical | Equal tree object IDs (`obj-cas-imm-{sha256[:12]}`) | Unchanged subtrees produce equal blob ids — **intended** for CAS dedup |
| Track when a renamed-or-edited file appears | New `name_enc` value at same path slot | Distinguish edit from rename |
| Detect equal sizes across files in same vault | Equal `size_enc` | Reveals duplicate-sized files |
| Detect equal content_hash prefixes | Equal `content_hash_enc` | Reveals two files with same first 12 hex of sha256 (i.e., effectively same content) |
| Detect equal MIME types | Equal `content_type_enc` | All `.txt` files share an enc value |
| Compare two vaults by tree-id | **CANNOT** — different `read_key`s give different IVs and different ciphertext | Cross-vault leakage = NONE |

### What is NOT leaked

- Plaintext file names, sizes, hashes, MIME — all stay encrypted.
- Read key, write key, vault key, passphrase — never derivable from observed IVs.
- Cross-vault correlation — different vaults have different `read_key`s, so the
  same filename in two vaults gives **different** `name_enc`. Verified by code
  reading: `read_key = PBKDF2(pass, "sg-vault-v1:"+vault_id)` so vault_id acts
  as a per-vault salt.

### Realistic attacker scenarios

- **Server detective:** "Does vault X contain a file named the same as a known
  file in vault X?" → can answer yes/no for any candidate plaintext name only
  if the attacker also has the vault's `read_key` (they don't). With ciphertext
  alone the server can only see *which entries within a vault are equal*, not
  *what they decrypt to*. **Attack does not work without key.**
- **Repo-pattern correlation:** Server sees `git`-style commit deltas — which
  blob IDs and tree IDs change between commits. With deterministic IVs, an
  unchanged subtree in a deep folder produces an unchanged tree_id, so the
  server sees exactly which subtrees changed at every commit. This is the
  classic **CAS-dedup side channel** common to all encrypted Git-like systems.
  Mitigation = put high-churn data in a separate vault.
- **Filename-equality dictionary:** Server sees `name_enc("README.md")`
  recurring across many entries within one vault. Because a vault has at most
  one file at each path, this is mostly limited to subdirectory entries with
  the same folder name (e.g., `src/test/README.md` and `src/main/README.md`
  → equal `name_enc` because both decrypt to `README.md`). Reveals folder
  structure repetition. Marginal info-leak.

## 5. Verification of "no plaintext or key material exposed"

- `Vault__Crypto.encrypt_deterministic` only takes `key` and `plaintext` and
  returns `iv || ciphertext || tag`. No key bytes appear in output.
- The IV is `HMAC(key, plaintext)[:12]` — leaks no key material because HMAC
  is a PRF (output computationally indistinguishable from random for fixed key).
- The IV does not leak plaintext beyond "two equal plaintexts produce equal
  IVs" — i.e., it leaks the equality relation only.
- Confirmed by reading `Vault__Sub_Tree._store_tree` (line 242-246): only
  the encrypted tree bytes are stored, no plaintext field.

## 6. Test-suite Coverage

| Test | Coverage |
|------|----------|
| `Test_Vault__Crypto__Tampering.test_encrypt__deterministic_with_same_iv` | Confirms `encrypt(key, p, iv=fixed)` is deterministic — does NOT cover `encrypt_deterministic` itself |
| `Test_Vault__Crypto__Hardening` | No test calls `encrypt_deterministic` directly |
| `Test_Vault__Sub_Tree` | Round-trip only — does not assert IV reuse properties |

**Gap:** No test would catch:
- `iv = hashlib.sha256(plaintext).digest()[:12]` (M1 — drops HMAC key)
- `iv = b'\x00'*12` (constant IV mutation)
- `iv = os.urandom(12)` inside `encrypt_deterministic` (M3 — breaks CAS dedup)

QA Phase 3 should add: cross-vault tree_id divergence, same-vault same-tree
determinism, IV-equality-iff-plaintext-equality property tests.

## 7. Recommendation

- Document the leakage map (this section 4) in the user-facing security model.
- Add three property tests (see Mutation Matrix M1, M2, M3).
- No code change needed; the construction is sound for the threat model.
