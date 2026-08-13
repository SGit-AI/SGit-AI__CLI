# Contract v0 — Cache Layer Wire Format (CLI side draft)

**Version:** v0 — DRAFT pending Web/API mark-up
**Date:** 2026-08-12
**Owners:** SGit-AI CLI Architect (this document) + SG/Vault Web Architect + SG/Send API Architect (pending counter-sign)
**Status:** Draft for counter-sign. Citations point at live CLI code at `sgit_ai/_version.py == v0.1.0`. Once signed, the citations become normative and any change to a pinned citation requires a contract amendment (§10).
**Supersedes:** nothing. **Depends on:** `08/12/v0.3__architecture__cache-layer-decisions.md` (D1–D9).
**Companion:** `08/06/v0__architecture__per-path-indexes.md`, `.1`, `.2`; readiness review `reviews/08/08/v0__architect-review__per-path-indexes-implementation-readiness.md` (F6).

---

## 1. Scope

This contract covers, exactly:

- The two **encrypted cache objects** — a **value cache** at `bare/cache/value/{cache_file_id}` and a **pointer cache** at `bare/cache/pointer/{cache_file_id}` — their plaintext shape, their id derivation, their envelope, their storage paths, and the read/verify/fallback semantics.

This contract **pins by reference, not by re-definition**:

- The **AES-256-GCM envelope** — the same random-IV envelope used for refs, commits, blobs and the branch index (`sgit_ai/crypto/Vault__Crypto.py:199-210`). See §5.
- The **HMAC-SHA256 file-id primitive** — `derive_file_id = HMAC-SHA256(read_key, domain)[:12]` (`Vault__Crypto.py:65-67`). See §4.
- The **batch transport** — `write` / `delete` ops carrying base64 `data` (`sgit_ai/core/actions/push/Vault__Batch.py:59-101,261-263`; `sgit_ai/network/api/Vault__API.py:60-76`). No new server capability.

This contract does **NOT** cover:

- When or why a writer creates or reconciles a cache object (that is `v0.3` §2 / the push reconcile). This is a wire-format contract: it says what bytes live at the cache paths and how they are read, not the maintenance policy.
- The tree/blob/commit/ref formats (unchanged and out of scope — the cache layer adds no marker to any of them).
- The `read_key` derivation chain (PBKDF2), the `vault_id` grammar, or the branch-index format (all upstream and unchanged).

---

## 2. Storage paths (normative)

| Object | Path | Producers MUST NOT |
|---|---|---|
| Value cache | `bare/cache/value/{cache_file_id}` | write these under `bare/indexes/` or `bare/data/` |
| Pointer cache | `bare/cache/pointer/{cache_file_id}` | " |

`bare/cache/` and its two subfolders are a new top-level namespace, disjoint from `bare/data|refs|keys|indexes|pending|branches`. `bare/indexes/` remains reserved for the single branch index; nothing under `bare/cache/` may be resolved as a branch index (this is what closes readiness-review F1). The `file_id` on the wire is the path relative to `.sg_vault/`, exactly as for every other object.

---

## 3. `cache_file_id` grammar (normative)

```
cache_file_id  = "cch-pid-" mutability "-" tail
mutability     = "snw" | "muw"
tail           = 12 * HEXLOWER          ; = derive_file_id(read_key, domain)  (§4)
```

Regex: `^cch-pid-(snw|muw)-[0-9a-f]{12}$`. The `snw|muw` label is an **output label, not hashed** — it mirrors the existing `ref-pid-muw-` / `idx-pid-muw-` convention (`Vault__Crypto.py:88-89`). The `cch-` family is grep-distinct from `obj-cas-imm-`, `ref-pid-`, `idx-pid-`, `key-rnd-imm-`.

---

## 4. Id derivation (normative)

```
tail = HMAC-SHA256(read_key, domain).hexdigest()[:12]

domain(value,   path) = "sg-vault-v1:file-id:cache-value:"   + vault_id + ":" + path
domain(pointer, path) = "sg-vault-v1:file-id:cache-pointer:" + vault_id + ":" + path
```

`kind` is part of the domain, so the value and pointer namespaces are fully independent: the same `path` yields two unrelated ids, and changing a path's kind is a new object, never a mutation of an existing one. `path` is the vault-relative POSIX path with `/` separators, no leading slash, NFC-normalised UTF-8, byte-identical to the key used in `flatten()` maps (`sgit_ai/storage/Vault__Sub_Tree.py:96`).

`read_key` is held only by key holders; the server never possesses it and therefore **cannot compute any `cache_file_id` nor link it to a `path`** — the cache layer is inside the zero-knowledge boundary (§8).

### 4.1 Reference vectors (normative — reproduce byte-for-byte)

**Chain A — pure HMAC (KDF-independent; the primary interop vector).**
`read_key = 000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f` (hex), `vault_id = "7y6uk6gj"`:

| kind | path | domain | `cache_file_id` (snw) |
|---|---|---|---|
| value | `pages/home.md` | `sg-vault-v1:file-id:cache-value:7y6uk6gj:pages/home.md` | `cch-pid-snw-4aa53f5467b6` |
| value | `keys/api.json` | `sg-vault-v1:file-id:cache-value:7y6uk6gj:keys/api.json` | `cch-pid-snw-309e3f5c6400` |
| pointer | `media/photos` | `sg-vault-v1:file-id:cache-pointer:7y6uk6gj:media/photos` | `cch-pid-snw-51416375f368` |
| pointer | `pages/home.md` | `sg-vault-v1:file-id:cache-pointer:7y6uk6gj:pages/home.md` | `cch-pid-snw-13b79ad675e8` |

(The `muw` variant is byte-identical except the label: e.g. `cch-pid-muw-4aa53f5467b6`.)

**Chain B — full derivation (shows the whole chain).**
`passphrase = "test-vector-passphrase-0001"`, `vault_id = "7y6uk6gj"`,
`read_key = PBKDF2-HMAC-SHA256(passphrase, "sg-vault-v1:7y6uk6gj", 600000, 32) = 363032d8b69a4ea947385a6f26aff18c2394d513f990aa25fe73892cf2b7f8e0`:

| item | value |
|---|---|
| value id, `pages/home.md` | `cch-pid-snw-23f9f166b48a` |
| pointer id, `media/photos` | `cch-pid-snw-a3f9b74ad988` |
| branch-index id (family cross-check) | `idx-pid-muw-bb5912c7f5bd` |

Any implementation (CLI, browser WASM/JS, server-side helper) that does not reproduce Chain A exactly is non-conformant. Chain B additionally validates the PBKDF2 leg.

---

## 5. Envelope (pinned by reference)

The stored bytes at a cache path are `IV(12) ‖ AES-256-GCM-ciphertext ‖ tag(16)`, produced by `Vault__Crypto.encrypt(read_key, plaintext)` with a **random IV** (`Vault__Crypto.py:199-204`). AAD is empty, matching every other object. On the batch wire, `data` is base64 of these bytes.

Cache objects MUST use the random-IV `encrypt`, **never** `encrypt_deterministic` (`Vault__Crypto.py:162-170`): they are mutable, and a deterministic IV would leak value-equality across paths and updates. This is the inverse of the tree rule (trees use deterministic IV for CAS dedup; caches must not).

---

## 6. Plaintext schemas (normative)

Decrypted plaintext is UTF-8 JSON matching one of the two Type_Safe schemas below. All fields are `Safe_*`-typed and round-trip-tested (`from_json(x.json()).json() == x.json()`). Receivers MUST tolerate unknown extra fields (Type_Safe drops them on `from_json`); producers SHOULD NOT add unknown fields in `v1` — bump to `_v2` (§9).

### 6.1 `cache_value_v1`

| field | type | req | notes |
|---|---|---|---|
| `schema` | `Safe_Str__Schema_Version` | ✓ | MUST equal `"cache_value_v1"` |
| `kind` | `Safe_Str` (`"value"`) | ✓ | redundant with the folder; present for self-description |
| `path` | `Safe_Str__File_Path` | ✓ | the indexed path — verified by readers against the derived id (48-bit collision guard) |
| `mutability` | `Safe_Str` (`"snw"`\|`"muw"`) | ✓ | matches the id label |
| `commit_id` | `Safe_Str__Object_Id` | ✓ | the named-branch commit this reflects — staleness marker |
| `content_type` | `Safe_Str__Content_Type` | ✓ | |
| `size` | `Safe_UInt__File_Size` | ✓ | plaintext byte length |
| `content_hash` | `Safe_Str__Content_Hash` | ✓ | `sha256(plaintext)[:12]`, as `flatten()` reports (`Vault__Sub_Tree.py:142`) |
| `value_b64` | `Safe_Str__Base64_Data` | ✓ | base64 of the file's plaintext content (a copy; distinct ciphertext from the blob) |

### 6.2 `cache_pointer_v1`

| field | type | req | notes |
|---|---|---|---|
| `schema` | `Safe_Str__Schema_Version` | ✓ | MUST equal `"cache_pointer_v1"` |
| `kind` | `Safe_Str` (`"pointer"`) | ✓ | |
| `path` | `Safe_Str__File_Path` | ✓ | collision guard |
| `mutability` | `Safe_Str` (`"snw"`\|`"muw"`) | ✓ | |
| `commit_id` | `Safe_Str__Object_Id` | ✓ | staleness marker |
| `content_type` | `Safe_Str__Content_Type` | ✓ | |
| `size` | `Safe_UInt__File_Size` | ✓ | |
| `target_kind` | `Safe_Str` (`"blob"`\|`"tree"`) | ✓ | whether `target_id` is a file blob or a folder/subtree |
| `target_id` | `Safe_Str__Object_Id` | ✓ | `obj-cas-imm-…`; a `blob_id` (file) or `tree_id` (folder) |
| `content_hash` | `Safe_Str__Content_Hash` | — | present when `target_kind == "blob"` |

### 6.3 Reference fixtures (plaintext, normative)

Fixture V (value), for `path = "pages/home.md"`, content `"# Home\n"` (7 bytes):
```json
{"schema":"cache_value_v1","kind":"value","path":"pages/home.md","mutability":"snw",
 "commit_id":"obj-cas-imm-aaaaaaaaaaaa","content_type":"text/markdown","size":7,
 "content_hash":"c8e5a6f1b2d3","value_b64":"IyBIb21lCg=="}
```
Fixture P (pointer), for `path = "media/photos"` (a folder):
```json
{"schema":"cache_pointer_v1","kind":"pointer","path":"media/photos","mutability":"snw",
 "commit_id":"obj-cas-imm-aaaaaaaaaaaa","content_type":"application/x-directory","size":0,
 "target_kind":"tree","target_id":"obj-cas-imm-bbbbbbbbbbbb"}
```
(`content_hash` in Fixture V is illustrative; the id lives at `bare/cache/value/cch-pid-snw-4aa53f5467b6` under Chain A's `read_key`.)

---

## 7. Read protocol (normative for readers)

To read a known `path` P (reader holds `read_key`, knows `vault_id`, knows or guesses the kind):

1. Compute `cache_file_id` locally (no request, §4).
2. **One batch read** of `{named_ref_id, cache_file_id}` together — breadth, one round trip (`api.batch_read`).
3. Decrypt (§5) and branch:
   - **hit AND `path` matches AND `commit_id == ref's commit`** → fresh. Value: use `value_b64` (done, 1 RT). Pointer: fetch `target_id` (2 RTs), or start a walk mid-tree.
   - **hit BUT `commit_id` older than ref** → lagging. Use opportunistically, or fall back to a tree walk from the ref for strong freshness (caller's tolerance).
   - **miss (404) OR `path` mismatch** → not cached / 48-bit collision → fall back to the full tree walk from root.

Correctness MUST NOT depend on a cache object being present or fresh: every miss/stale/mismatch has the existing tree walk as its floor. A reader that does not know the kind MAY batch both candidate ids in the same request (one extra op, still one round trip).

---

## 8. Zero-knowledge acknowledgement

The server gains, versus today: two folder names (`bare/cache/value`, `bare/cache/pointer`) and, per kind, an object count and update frequency. It does **not** gain: any `path`, any `read_key`, any linkage between a `cache_file_id` and a path (the id is `HMAC(read_key, …)`; ids were already opaque for refs/index). The marginal disclosure is that *some* paths are cached and how often they change — accepted (per the 4-Aug decision), minimised by keeping the cached set small and declared. Value ciphertexts use random IV (§5), so no value-equality leaks.

---

## 9. Versioning

Bump the `schema` string to `cache_value_v2` / `cache_pointer_v2` for any change to a required field, a field type, the envelope, the domain strings, the path grammar, or the storage paths. Within `v1`, only optional-field additions are permitted, and receivers already tolerate unknown fields. A `v2` reader MUST be able to read a `v1` object.

---

## 10. Change control

Amendments require counter-sign by all three owners (§ header). The interop vectors in §4.1 and the fixtures in §6.3 are the definition of done: they MUST be asserted in the CLI Python suite and mirrored in the browser and server suites before any side ships write support.

---

## 11. Open questions (CLI default if no reply)

| # | Question | CLI default |
|---|---|---|
| Q1 | Does the SG/Send API itself *write* vaults? | Assume yes → it MUST run the same push reconcile, or its writes go silently stale |
| Q2 | Value/pointer threshold that steers `cache add` | 4 KB; per-invocation override |
| Q3 | Is `content_hash` on a pointer worth carrying for `tree` targets? | No — omit for `target_kind=="tree"`; keep for `"blob"` |
| Q4 | Should the id domain ever include a version tag? | No in v1; a format change bumps the `schema` field, not the domain |
| Q5 | Path normalisation form | NFC, POSIX `/`, no leading slash — MUST match `flatten()` keys byte-for-byte |

---

*Drafted against `dev` (`sgit_ai/_version.py == v0.1.0`) on 2026-08-12. All §4.1 vectors and §6.3 fixtures were computed with the live derivation primitive; Chain A is KDF-independent and is the primary cross-runtime assertion. Pending counter-sign by the SG/Vault Web and SG/Send API architects.*
