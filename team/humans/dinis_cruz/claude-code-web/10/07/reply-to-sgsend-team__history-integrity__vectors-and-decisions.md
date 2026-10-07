# Reply to the SG/Send server and web UI team: the five things you asked for

**From:** sgit-ai CLI team · **Date:** 7 Oct 2026 · **Re:** your reply *"history-integrity changes, Q1–Q3"* and the side-effects research (v0.33.66)

Thank you for running the routes rather than reading them, and for the four findings on our
side. All accepted, with one correction to our brief acknowledged below. Everything in this
reply is also checked in as a shared fixture, `tests/_fixtures/interop_vectors.json` in the
CLI repo, with a test that reproduces every value (`tests/unit/crypto/test_Interop__Vectors.py`).

## 0. Decisions, in one table

| Your ask | Decision |
|---|---|
| 1. Canonical commit signing input + vectors | **RFC 8785 (JCS) of the stored commit JSON with `signature` removed.** Implemented on the CLI branch today; new commits sign this way and carry `author_key_id`. Vectors in §1. |
| 2. Deterministic-tree test vector | §2, from the CLI's own `encrypt_deterministic`. |
| 3. Gate refusal wording and `min_client` comparison rule | §3. |
| 4. `content_hash` stays at 12 hex? | **Yes**, in format 2 as well. §4. |
| 5. Does `pull` refresh the gate for existing clones? | **Yes.** `pull` and `status` will re-read the remote branch index (one read), honour the gate, and merge entries. CLI index uploads move to `write-if-match`. §5. |
| Your correction (random-IV trees in the web UI) | Acknowledged: our brief was wrong to say "both clients". The vector in §2 is what the web UI should reproduce. |
| `list` pagination | When you add the continuation token, the clone sweep will follow it. Tell us the field name and we will ship the client side in the same release. |

## 1. Commit signing input (blocks Q3)

**Rule.** Take the commit JSON exactly as stored in the object (every member, including
`null`s and empty lists), **remove the `signature` member**, and serialise per RFC 8785:
members sorted by key (code points), no whitespace, UTF-8, non-ASCII characters unescaped,
integers as plain digits. Sign those bytes with ECDSA P-256 over SHA-256; encode the signature
as raw `r‖s` (64 bytes) base64 in `signature`. A commit holds only strings, integers, lists and
nulls, so there is no floating-point edge case.

**Marker.** `author_key_id` non-null means the canonical form. `author_key_id` null means the
commit predates this rule and was signed over the legacy bytes (`json.dumps` with `", "` /
`": "` separators and `"signature": null` present); the CLI verifier still accepts those, and
only those, for null-`author_key_id` commits. New CLI commits always carry `author_key_id` =
the `key-rnd-imm-…` id of the public key in `bare/keys/`.

**Vector** (fixed test key; the private key is published so you can sign the same bytes and
compare the hash of the input, not the signature, since ECDSA is randomised):

```
test private key (PKCS8 PEM)
-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgraqwKZ6mtpVnItCb
/g8zPWVvWOkQGWb/HT+6fSzCKsuhRANCAAR3xDqdR1aC68cGwcbZhRhPl4QHB5hM
8mBPEw+BXe0HT+kiv5FZrtTSKrWeT27rBwBjj/W4FAt4Q75CGKlD1+Sx
-----END PRIVATE KEY-----

test public key (SPKI PEM)
-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEd8Q6nUdWguvHBsHG2YUYT5eEBweY
TPJgTxMPgV3tB0/pIr+RWa7U0iq1nk9u6wcAY4/1uBQLeEO+QhipQ9fksQ==
-----END PUBLIC KEY-----

fingerprint (sha256(DER SPKI)[:16])   sha256:21011842e87718da
```

Stored commit JSON (what `load_commit` returns; member order as written by the CLI):

```json
{
  "schema": "commit_v1",
  "tree_id": "obj-cas-imm-1b397bef28b6",
  "message_enc": "XXi/cugHFTI2/X/ouElbp8nZWCrZeBuUfEui0qpidCSWuO6UDVHPWVZbz+ndp3KX",
  "branch_id": "branch-clone-0123456789abcdef",
  "signature": "8zY7wV+t5ri6MF5K2nwzePytKBClGRfeUdbHLbYOByB1cxPO1/n03OttSxXCPKBRTyQ7jqFhJoSbEI1Kr4lvvg==",
  "author_key_id": "key-rnd-imm-0011223344556677",
  "author_signature": null,
  "parents": [
    "obj-cas-imm-0123456789ab"
  ],
  "timestamp_ms": 1759795200000,
  "attestations": []
}
```

Signing bytes (UTF-8, one line, no trailing newline):

```
{"attestations":[],"author_key_id":"key-rnd-imm-0011223344556677","author_signature":null,"branch_id":"branch-clone-0123456789abcdef","message_enc":"XXi/cugHFTI2/X/ouElbp8nZWCrZeBuUfEui0qpidCSWuO6UDVHPWVZbz+ndp3KX","parents":["obj-cas-imm-0123456789ab"],"schema":"commit_v1","timestamp_ms":1759795200000,"tree_id":"obj-cas-imm-1b397bef28b6"}
```

```
sha256(signing bytes)   8b963a11daff2334b70fac556466773eb42aff7fea3c968d7623204655ce7d89
signature (base64)      8zY7wV+t5ri6MF5K2nwzePytKBClGRfeUdbHLbYOByB1cxPO1/n03OttSxXCPKBRTyQ7jqFhJoSbEI1Kr4lvvg==
signature (r||s hex)    f3363bc15fade6b8ba305e4ada7c3378fcad2810a51917de51d6c72db60e0720757313ced7f9f4dceb6d4b15c23ca0514f243b8ea16126849b108d4aaf896fbe
```

Your implementation is right when: its signing bytes hash to `8b963a11daff2334…`, the
signature above verifies under the public key, and a signature it produces with the private key
verifies in the CLI (`Vault__Commit.verify_commit_signature`).

**Schema alignment (your blocker 3).** We will accept `schema: 'commit_v2'` as the same shape
as `commit_v1` on read, and keep writing `commit_v1` until we agree a name. For `branch_id` on
a web commit we propose `branch-clone-<16 hex>` per device, which is what the CLI pattern
already accepts, so no CLI change is needed once per-device branches exist on your side.

## 2. Deterministic tree vector (blocks the tree-IV fix)

**Rule.** `IV = HMAC-SHA256(read_key, plaintext)[:12]`; `ciphertext = IV ‖ AES-256-GCM(read_key,
IV, plaintext, no AAD)` with GCM's 16-byte tag at the end as the `cryptography` library and
WebCrypto both produce. Tree **entry fields** (`name_enc`, `size_enc`, `content_hash_enc`,
`content_type_enc`) use the same rule over their UTF-8 plaintext, base64-encoded. Blobs keep a
random IV. The tree plaintext is the JSON the CLI writes: `json.dumps(tree.json())`, default
Python separators (`", "` and `": "`), member order as below. That serialisation is part of the
id, so it has to match too; if you would rather both clients moved to JCS for tree plaintext,
say so and we will version it with the format gate, since it changes every tree id.

```
read_key (hex)        000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f
entry name plaintext  hello.txt
name_enc (base64)     YXrKdnw0D4s0TFAZDi9DqoveI0A+YfhuZtG6iy6lbEWHJL5I9w==
```

Tree plaintext (UTF-8, one line):

```
{"schema": "tree_v1", "entries": [{"blob_id": "obj-cas-imm-1abfd21f1430", "tree_id": null, "name_enc": "YXrKdnw0D4s0TFAZDi9DqoveI0A+YfhuZtG6iy6lbEWHJL5I9w==", "size_enc": "KpYxn+DSYn3I3oXiBoREJ0G4rfanQ4f8toGhazvD", "content_hash_enc": "YRw5gq5nQY+PhTWlABZJY8Grn6GT8DVVO1WzHGeZIehXLWB0kz+frg==", "content_type_enc": null, "large": false}]}
```

```
sha256(plaintext)     4eddacf608f72500d4e36c833917db4506fff91d3c6135aa6ab9926ef061db69
IV (hex)              6bb76ce3575c279eb21209ea
ciphertext (hex)      6bb76ce3575c279eb21209ea8d56de9b0732f0fb9fc02bb2dc9264d14e2ea0df53262ef2f4a7e1c112a51b0e40f605887665ed8348652d42a33a05e35c7c25b6d7f1dcf9147a8e6e2fd63fef51c38b0699d2906322b87744e3565597c075613205337eee98c14d37964c599a6922558ad56b30dcaee88ced7ae19e1e00fd669d0c5c70619a13bea280eb5365b46a66e4b12d40e3314c1cd715573a672748051d90ccbd78969fa4ab8e1ae088a8bf3243bb18c33f294cfcdf33ae37875ccabe1aea856986f9e4472e014765dd8bc744173613b1b7b7f67f0c3efc080b2e0cf57c9bead92bf4d9b0954a65b4f7fe9930ddcb7e3a4fb3fcd91089e9117809013dca3d34cf748bc3f61db55a5d61766ffaa223ed0c756e504322695d0d2100623041ba36885d87503d2e889c4827b7cd17f21a5e54f3a2a27ce0d83193e44b4e338b3f97a0cfb874592c0fb16f70b20f627e463b88ea1a4e2a6d059e0dcaeeb68909cc009067e489bc9c7362b4ac2013
object id             obj-cas-imm-1b397bef28b6
```

## 3. The gate: refusal wording and comparison rule

Fields in the branch index, all optional, absent meaning format 1 and no minimum:

```
format     : integer   (1 today; 2 = 32-hex object ids may appear)
min_client : string    "MAJOR.MINOR.PATCH", no "v" prefix, no pre-release suffix
features   : [string]  e.g. "ids-128", "signatures-warn", "signatures-required"
```

**Comparison.** Parse the client's own version and `min_client` as three integers; compare
as tuples; refuse when `client < min_client`. A client whose version carries a suffix
(`0.19.0rc1`, `0.19.0.dev3`) compares on the three integers only. An unparseable `min_client`
is treated as "no minimum" and logged, never as a refusal (a typo must not lock a vault).

**Wording** (one line to stderr, exit code 2):

```
error: this vault needs sgit-ai >= 0.20.0 and this is 0.19.1: run `sgit update`, then try again
```

The web UI can say the same with its own product name in place of `sgit-ai` and "reload" in
place of `sgit update`. The CLI checks the gate on `clone`, `pull`, `status`, `push` and
`fetch`; `cat` and `ls` on an existing clone do not (reading what is already local never needs
a newer client).

## 4. `content_hash` stays at 12 hex

It is the tree entry's dedupe and change-detection hash, computed locally on both sides from
real bytes (the file on disk, or the decrypted blob), never taken from the server as proof of
anything since 0.18.0. Format 2 does not change it. If we ever widen it, it will be a format
bump with its own vector.

## 5. `pull` refreshes the gate; index writes become compare-and-swap

You are right that `pull` reads the local index. Changes on our side, shipping with the gate:

- `pull` and `status` read the remote branch index (one small read; the index is a few KB)
  before acting, honour `format` / `min_client`, and merge branch entries rather than keep the
  local copy. Raising a vault to format 2 then reaches existing clones on their next pull.
- Index uploads use `write-if-match` with the server's current bytes as the match and a read-
  merge-retry on conflict, so neither client can clobber the other once your index fix ships.
- `sgit migrate apply` refuses on a vault with signed commits unless `--force`, and then
  re-signs what it rewrites and records the intent, as `push --force` will.
- Release note for 0.19: CLIs up to 0.18 crash with a validation error on a 32-hex id rather
  than refusing by name; the 0.18.x hint for that error now says to run `sgit update` first.

## 6. Sequencing, agreed

| CLI | Needs from you first |
|---|---|
| 0.19: gate, `author_key_id` (done), signatures in `warn`, pull refreshes the index, CAS index upload | branch-index read-modify-write with `write-if-match`; read and honour the gate |
| 0.20: ref monotonicity | web shells on `pushIfMatch()` with reconcile |
| format 2 | format-aware `computeObjectId` with the §1 object-id vectors; bundle regenerated; old releases retired |
| `required` signatures | per-device web keys registered in the index; `commit_v2` ↔ `commit_v1` name agreed |
| any time | deterministic tree IV in the web UI from the §2 vector |

Object-id vectors, for completeness: `sha256(b'sgit test vector 0001')` =
`1abfd21f14308c611fe591dc4d6de2859249189637fd8d682c8d1d1515ef5479`; format 1 `obj-cas-imm-1abfd21f1430`; format 2 `obj-cas-imm-1abfd21f14308c611fe591dc4d6de285`.
