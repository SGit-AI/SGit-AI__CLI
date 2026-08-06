# Security Review — SGit-AI Cryptography, Key Entropy & Simple Tokens

**Reviewer:** Fable (architect capacity)  ·  **Date:** 2026-08-06  ·  **Scope:** `sgit_ai/crypto/**`, `sgit_ai/safe_types/**`, storage encryption call-sites, at-rest key handling
**Method:** direct source read + entropy/attack-cost computation against the real wordlist and KDF parameters. Every claim below cites `file:line`.

---

## 0. Executive summary

**The passphrase-vault path is cryptographically sound. The simple-token path is broken and should be treated as compromised for anything sensitive.**

- A **passphrase vault key** (`{24×[a-z0-9]}:{vault_id}`) carries **~124 bits** of entropy, stretched with **PBKDF2-HMAC-SHA256 at 600 000 iterations** into AES-256-GCM. This is not realistically recoverable from ciphertext. ✅
- A **simple token** (`word-word-NNNN`) carries **30.2 bits** (356-word list). Two independent, cheap attacks recover the full key:
  1. **`transfer_id` oracle (P0):** the *public* vault identifier is `sha256(token)[:12]` — an unsalted, un-stretched hash of the 30-bit secret (`Simple_Token.py:25-28`). Anyone who sees the storage path / API vault_id (cloud provider, CDN, log pipeline, object-store breach — i.e. exactly the parties the zero-knowledge model is supposed to defend against) recovers the token in **~0.1 s on one GPU**. The in-code comment calling this ID "safe to log in URLs" (`Vault__Crypto.py:117`) is **false** for tokens.
  2. **Fixed-salt precompute:** even without the oracle, `aes_key()` uses PBKDF2-600k with a **global constant salt** `b'sgraph-send-v1'` (`Simple_Token.py:9,30-36`). One precomputed table (~**21 GPU-hours**, one-time) decrypts *every simple-token vault ever created*.

So, answering the core question directly — *"is it realistic to find the keys from encrypted text?"* — **for simple-token vaults: yes, trivially (sub-second to sub-day). For passphrase vaults: no.**

Good news for the quantum question: vault **confidentiality is symmetric AES-256**, which is already quantum-resistant (128-bit post-Grover). "Harvest-now-decrypt-later" does **not** threaten vault contents via quantum — the only decryption path is the *classical* low-entropy-token weakness above. The genuinely quantum-vulnerable surface is the **PKI** (ECDSA P-256 signatures, RSA-4096 messaging), which is an authenticity/roadmap concern, not the front-line risk.

Priority ordering: **P0 = classical simple-token break (exploitable today with a laptop). P1 = PKI post-quantum migration (needs a quantum computer that does not yet exist).**

---

## 1. Cryptographic inventory

| Purpose | Primitive | Params | Where | Verdict |
|---|---|---|---|---|
| Passphrase → key | PBKDF2-HMAC-SHA256 | 600k iters, salt=`sg-vault-v1[:write]:{vault_id}` | `Vault__Crypto.py:26-32,57-63` | ✅ strong |
| Blob / commit / ref encryption | AES-256-GCM, random IV | 96-bit IV, 128-bit tag | `Vault__Crypto.py:199-210`; `Vault__Sub_Tree.py:145` | ✅ sound |
| Tree + entry-metadata encryption | AES-256-GCM, **deterministic IV** = `HMAC(key,pt)[:12]` | for CAS dedup | `Vault__Crypto.py:162-176`; `Vault__Sub_Tree.py:48-51,216` | ⚠ leaks equality/structure |
| Object / file IDs | SHA-256 **truncated to 48 bits** | `[:12]` hex | `Vault__Crypto.py:65-83,212-213` | ⚠ collision at scale |
| **Simple token → key** | SHA-256 (id) + PBKDF2-600k **fixed salt** + HKDF | 30-bit input | `Simple_Token.py:25-51` | ❌ broken |
| Author/branch signatures | **ECDSA P-256** (raw r‖s) | SHA-256 | `PKI__Crypto.py:24-26,66-76` | ⚠ classical-only (quantum-vulnerable) |
| Contact messaging | **RSA-4096-OAEP** wraps AES-256-GCM | SHA-256 | `PKI__Crypto.py:18-22,80-107` | ⚠ classical-only; HNDL-exposed |
| Structure/metadata sub-key | HKDF-SHA256 | salt=None, domain info | `Vault__Crypto.py:141-153` | ✅ fine |
| Local signing key at rest | PEM, **NoEncryption** | plaintext on disk | `Vault__Key_Manager.py:56-61` | ⚠ at-rest exposure |

---

## 2. Findings (ranked)

### F1 — CRITICAL: simple-token keys are recoverable from public data / ciphertext
- **Entropy:** 356² × 10⁴ = 1.27×10⁹ = **30.2 bits** (`Simple_Token__Wordlist.py`, `Safe_Str__Simple_Token.py`).
- **Oracle:** `transfer_id = sha256(token)[:12]` is public (used as `vault_id` in S3 paths/URLs, `Vault__Crypto.py:110-117`) and is a *fast, unsalted* function of the token → brute-force the entire keyspace in **~0.1 s/GPU**, no PBKDF2 involved.
- **Amortized precompute:** fixed global PBKDF2 salt → one **~21 GPU-hour** table cracks all tokens forever.
- **Blast radius:** the token deterministically yields **read key, write key, and EC signing seed** (`Simple_Token.py:41-51`) → full read **and write** and identity forgery.
- **Failure scenario:** cloud/CDN/log operator (or anyone who breaches the object store) sees only opaque `vault_id`s → recovers tokens in seconds → decrypts and can tamper with every simple-token vault. This is exactly the adversary the zero-knowledge design promises to exclude.

### F2 — HIGH: token is an omnipotent, non-revocable, at-rest bearer credential
- One string = read + write + sign; no separation, no expiry, no revocation (self-contained by design).
- Stored at rest in cleartext: `Schema__Local_Config.edit_token` (`Schema__Local_Config.py:10`) → `.sg_vault/local/config.json`. Local disk read = full vault compromise.

### F3 — MEDIUM: local signing private key written unencrypted
- `store_private_key_locally` exports PEM with `NoEncryption()` (`Vault__Key_Manager.py:56-61`, `PKI__Crypto.py:36-44`). Any local-disk reader obtains the author signing key → commit forgery.

### F4 — MEDIUM: deterministic encryption leaks metadata/structure
- Filenames, sizes, content-hashes, content-types and whole tree objects are deterministically encrypted (`Vault__Sub_Tree.py:48-51,74-77,216`). A key-less server-side observer learns: equality of filenames across the vault/branches/history, equality of sizes and contents, and subtree/dedup structure. No plaintext recovery, but a real weakening of the "the server learns nothing" claim. (Blob ciphertext length already leaks approximate file size regardless.)

### F5 — MEDIUM: 48-bit content/file IDs collide at scale
- `obj-cas-imm-` object IDs and `derive_file_id` refs are SHA-256 truncated to 48 bits (`Vault__Crypto.py:65-83`). Birthday collision ≈ 2²⁴ ≈ 16 M objects. A CAS collision aliases two distinct ciphertexts → silent data loss or fetch-returns-wrong-object. Integrity, not confidentiality — but it grows with adoption.

### F6 — INFO/LOW
- `derive_keys_from_vault_key` auto-downgrades any token-shaped string to the weak path (`Vault__Crypto.py:99-108`) — the weakness leaks into the combined format.
- The "vault_id is safe to log" comment is correct for passphrase vaults (HMAC of a 124-bit key) but false for tokens.

### Positives (done right — keep)
PBKDF2-600k and 124-bit passphrase entropy; AES-256-GCM AEAD everywhere; random IVs for blobs/commits/refs; per-domain HKDF/`info` separation; opaque `vault_id` pattern to keep human words out of logs (`Vault__Crypto.py:24,43-55`); metadata-only "structure key" for least-privilege reads; payload version tags (`PKI__Crypto.py:96,112`) that make migration feasible.

---

## 3. (a) What is currently shipped for simple tokens

From this session's work (commits `2dd1bd7`, `1d7b656`): **simple-token *creation* is already disabled at the CLI** — `vault export`, `vault share`, `share send`, `share publish` route to a disabled stub, `sgit clone <simple-token>`'s transfer-mint step is gated, and `init`/`create` no longer auto-mint tokens. **Consumption remains**: `share receive`, `sgit clone <token>`, `vault probe`, and the whole backend derivation (`Simple_Token`, `derive_keys_from_simple_token`) are intact and unit-tested. Net: no *new* 30-bit vaults are minted from the CLI, but (i) any already-created simple-token vault is still live and breakable, (ii) the SG/Send transfer feature and web UI may still mint them, and (iii) the derivation code is one call away from re-exposure. **The CLI gate is necessary but not sufficient — the derivation itself is the vulnerability.**

---

## 4. (b) Can we keep simple tokens by increasing key size?

**Yes — but only if three things change together, and only ~6 words is genuinely secure.** The unavoidable math: a *self-contained shareable* token has no server secret in the loop, so `security ≤ token_entropy + KDF_work_factor`, and a fixed/public salt means an attacker can always precompute against a target.

Mandatory, in order:
1. **Remove the fast-hash oracle (non-negotiable).** Derive the public `vault_id` from the *expensive* KDF output (e.g. `HKDF(argon2id(token))` → truncate), **not** from `sha256(token)`. Otherwise no entropy or KDF change helps — the oracle bypasses all of it.
2. **Raise entropy.** Move to the **EFF-large wordlist (7776 words = 12.9 bits/word)** and pick a target:

   | scheme | entropy | offline-attack outlook (with Argon2id) |
   |---|---|---|
   | current `word-word-NNNN` (356 words) | 30 bits | broken (seconds) |
   | 4 EFF words | 51.7 bits | weak; well-resourced precompute feasible |
   | 5 EFF words | 64.6 bits | borderline |
   | **6 EFF words** | **77.5 bits** | **practical floor for durable secrets** |
   | 8 EFF words | 103 bits | comfortable |

3. **Switch the token KDF from PBKDF2 to Argon2id (memory-hard).** Add `argon2-cffi` on demand; target e.g. 256–512 MB, t=3. Memory-hardness defeats the GPU/ASIC amortization that makes the fixed-salt precompute cheap, buying ~20–30 effective bits and making a full-space table infeasible below ~80 bits of input.

Plus server-side guardrails (a self-contained token can't self-revoke): **rate-limit** `vault_id` lookups, **TTL/expiry**, and a **revocation list**.

**Recommendation — a tiered credential model:**
- **Durable / sensitive vaults:** full 124-bit vault keys (already the secure default). Steer here.
- **Human-friendly durable token (if product-required):** ≥6 EFF words + Argon2id + oracle removed. Secure, but no longer "simple."
- **Ephemeral SG/Send transfers only:** the short token is acceptable *only* for throwaway, non-secret, server-rate-limited, short-TTL shares, clearly labelled "not for secrets" — and still with the oracle removed.

---

## 5. (c) Post-quantum: what's actually at risk, and how hard

**What is already safe:** AES-256-GCM (→128-bit post-Grover) and SHA-256/HKDF/PBKDF2 (→128-bit). **Vault confidentiality needs no cipher change.** HNDL does not threaten vault contents.

**What is quantum-vulnerable (Shor):**
- **ECDSA P-256** author/branch signatures (`PKI__Crypto.py:24-26,66-76`) → forgeable → integrity/authenticity.
- **RSA-4096-OAEP** contact messaging (`PKI__Crypto.py:18-22,80-107`) → **HNDL-exposed**: messages harvested today are decryptable once a CRQC exists. This is the one place "start now" is warranted if those messages are long-lived secrets.

**Approach & effort (moderate, dominated by cross-runtime interop):**
- **Signatures → hybrid Ed25519/ECDSA **+** ML-DSA (Dilithium, FIPS 204)**, concatenated, payload-versioned. Keeps classical interop while adding PQC. Libs: `liboqs-python` or `pqcrypto` (server/CLI); browser needs a **WASM** PQC lib (`noble-post-quantum` JS or liboqs-WASM).
- **Messaging → hybrid X25519 **+** ML-KEM-768 (Kyber, FIPS 203)** wrapping the AES key, replacing RSA-OAEP.
- **The hard constraint** is CLAUDE.md's byte-for-byte browser interop: **Web Crypto supports neither Argon2 nor PQC**, so every KDF/PQC change must be mirrored in browser WASM with shared test vectors. That coordination — not the Python — is the bulk of the work. Sizes grow (ML-DSA sig ≈2.4 KB, key ≈1.3 KB) but are tolerable.

**Sequencing:** ship P0 (simple-token) first; treat PQC as a versioned roadmap item; pull the messaging-KEM migration forward if PKI messages are meant to stay secret for years.

---

## 6. (d) Threat model

**Trust boundary:** client (trusted, holds keys) ↔ server/object-store/CDN (untrusted; zero-knowledge promise).
**Assets:** vault content confidentiality; write-integrity/authenticity; metadata privacy; availability.
**Actors:** cloud/CDN/log operator (passive, sees paths+ciphertext); object-store breacher; passive network observer; malicious collaborator; local-disk attacker; future quantum adversary.

| # | Threat | Actor | Enabled by | Sev | Status |
|---|---|---|---|---|---|
| T1 | Recover token → decrypt+tamper any simple-token vault | operator/breacher | F1 (oracle + 30-bit + fixed salt) | **Critical** | live |
| T2 | Full vault compromise from a stolen laptop | local-disk | F2 (edit_token at rest), F3 (plaintext PEM) | High | live |
| T3 | Author/commit forgery | collaborator/local | F3; (future) ECDSA break | Med | live/roadmap |
| T4 | Metadata/structure inference (filenames, sizes, dedup) | operator | F4 (deterministic enc) | Med | live |
| T5 | CAS aliasing → data loss/wrong-object | operator/scale | F5 (48-bit IDs) | Med | grows |
| T6 | HNDL decryption of PKI messages | quantum (future) | RSA-4096 messaging | Med | roadmap |
| T7 | Passphrase-vault ciphertext attack | anyone | — (124-bit + PBKDF2-600k) | — | **not viable ✅** |

---

## 7. (e) Proposed changes (prioritized)

**P0 — classical, exploitable today**
- **C1 (F1):** Remove the `sha256(token)` public-ID oracle — derive `vault_id` from the expensive KDF output. *Mandatory before any token keeps being usable.*
- **C2 (F1):** Simple-token KDF → **Argon2id** (`argon2-cffi`), per-purpose HKDF unchanged; keep PBKDF2 only for legacy read.
- **C3 (F1):** EFF-large wordlist + **≥6 words** for any durable token; retain the 30-bit token *only* for ephemeral, rate-limited, expiring, non-secret transfers.
- **C4 (F2/F3):** Encrypt at rest — wrap `edit_token` and local `.pem` signing keys (OS keychain or passphrase-derived wrap); stop writing `NoEncryption()` PEMs.
- **C5 (server):** Rate-limit `vault_id` lookups, add TTL + revocation for token-addressed vaults.
- **C6 (F6):** Make the token→weak-path auto-downgrade explicit/opt-in, not silent.

**P1 — integrity & quantum roadmap**
- **C7 (F5):** Widen object/file IDs to ≥128 bits (full SHA-256 or 32 hex).
- **C8 (F4):** Document the deterministic-encryption metadata leak in the threat model; evaluate randomized-with-scoped-dedup or accept explicitly.
- **C9 (F6/T3/T6):** Hybrid PQC — Ed25519+ML-DSA signatures, X25519+ML-KEM messaging, payload-versioned, with browser-WASM test vectors.

**Cross-cutting:** shared client/browser/server crypto test vectors for every KDF/PQC change; a one-time migration plan for existing simple-token vaults (re-key to passphrase vaults; treat the old tokens as burned).

---

## Appendix — reproduced numbers
- Wordlist = 356 unique words → `word-word-NNNN` = 1,267,360,000 ≈ **2³⁰·²**.
- `transfer_id` brute force: whole space ≈ **0.1 s** @10 GH/s (one GPU).
- Fixed-salt PBKDF2-600k full table: 2⁴⁹·⁴ SHA-256 ≈ **21 GPU-h** (1 GPU) / **~13 min** (100 GPU) / minutes (ASIC).
- Passphrase vault: 24×[a-z0-9] ≈ **124 bits**; with PBKDF2-600k, not recoverable.
