# Brief for the SG/Send server and web UI team: history-integrity changes planned in sgit-ai, and three questions

**From:** the sgit-ai CLI team · **Date:** 7 Oct 2026 · **Status:** proposal, nothing shipped yet
**Context you may already have:** sgit-ai 0.18.0 (partial clones, bulk-fetch clone, pull guard)
is on PyPI since this morning. It needed nothing new from the server. The changes below might.

## 1. Why we are writing

A review of the CLI's integrity story found three gaps. None is a bug in your code; two of the
fixes are CLI-only, one touches the contract between the CLI, the API and the web UI, and that
is the one we need your answers on before we design it.

| Gap | What the CLI does today | Fix |
|---|---|---|
| Commit signatures are produced but never verified | every CLI commit carries an ECDSA P-256 signature (`signature` in `commit_v1`); no pull, status or fsck checks it; web-UI commits are unsigned | verify on pull/status/fsck; populate the reserved `author_key_id` field; per-vault policy `warn` → `required` |
| A ref can be rolled back without anyone noticing | the named ref is an AES-GCM-encrypted pointer; nothing checks the new head descends from the last known one | client-side monotonicity check; `push --force` records intent |
| Object ids are 48-bit | `obj-cas-imm-` + `sha256(ciphertext)[:12]` (12 hex). Fine against the host (forged bytes do not decrypt); not fine against a key holder: a second preimage is 2⁴⁸ work, hours on a GPU | 128-bit ids: `obj-cas-imm-` + 32 hex, new objects only, old ids stay valid in the same vault |

Measured on the 674-commit / 19,780-object collaboration vault: signature verification of the
whole history 39 ms, the monotonicity walk 155 ms worst case, 128-bit ids +1.5 % of store bytes.
Not a performance question on either side.

## 2. The compatibility plan, so you know what the CLI will do

- A **format gate** in the branch index (`format`, `min_client`, `features`; absent means
  format 1). Every existing vault stays format 1 and behaves as today. A vault owner raises a
  vault deliberately; CLI clients newer than the gate refuse a vault that needs a newer client
  by name; nothing ever requires a `vault move`.
- Signature verification and ref monotonicity need **no format change** and no server change.
- 128-bit ids are **format 2**, per vault, mixed: new objects get 32-hex ids, old objects keep
  12-hex ids, trees and commits reference both. `vault move` remains the optional full rewrite.

## 3. The three questions

### Q1. Does the server accept a 44-character `file_id` under `bare/data/`?

Today every object is written as `bare/data/obj-cas-imm-<12 hex>` (24 characters). Format 2
writes `bare/data/obj-cas-imm-<32 hex>` (44 characters) alongside them. Please confirm, for
each of these, that a 44-character object name is accepted with no change, or say what limits
or validation apply:

- `PUT  /api/vault/write/{vault_id}/{file_id}` and `DELETE /api/vault/delete/...`
- `POST /api/vault/batch/{vault_id}` operations `read`, `write`, `write-if-match`, `delete`
- `GET  /api/vault/read/{vault_id}/{file_id}`
- `GET  /api/vault/list/{vault_id}` (prefix listing; the clone sweep lists `bare/data/` once
  and expects every id back; 19,780 today, listing size grows by ~400 KB at format 2)
- presigned multipart `initiate` / `complete` / `read-url` (large blobs use the same id)
- any S3 key-length or key-charset rule behind the API, and any cache or CDN layer keyed on it

The CLI does not use any other id-length-dependent surface. Refs (`bare/refs/ref-pid-*`),
indexes, keys and cache ids are unchanged.

### Q2. Can the web UI read and write both id lengths?

The web UI reads trees, commits and blobs by id, and writes commits (we see them in the
vault: unsigned, `branch_id` outside the CLI pattern, ISO timestamps). For format 2 it must:

- parse a tree entry whose `blob_id` / `tree_id` is 12 or 32 hex, and a commit whose
  `tree_id` / `parents` are either;
- compute ids for anything it writes the same way as the CLI: `sha256(ciphertext)` as hex,
  truncated to 12 characters on a format-1 vault and 32 on a format-2 vault, both with the
  `obj-cas-imm-` prefix (test vectors below);
- read the format gate from the branch index and refuse, with a message, a vault whose
  `min_client` it does not meet, exactly as the CLI will.

Please tell us where id length is assumed (regexes, fixed-width parsing, UI column widths)
and whether the id computation is shared code we can give a test vector to.

### Q3. Can the web UI sign the commits it writes, and under which key?

A `required` signature policy only works if every writer signs. The CLI signs with the
clone branch's P-256 key (public key stored at `bare/keys/key-rnd-imm-<id>`, mapped from the
branch in the index). We need to know:

- whether the web UI has, or can hold, a per-user or per-session P-256 signing key that it
  can register the same way;
- whether it can populate `author_key_id` on every commit it writes (the field exists in
  `commit_v1`, reserved, currently `null`);
- failing that, whether a vault-level policy of "web-UI commits are accepted unsigned when
  made under a server-authenticated session" is something the server could attest to, so the
  policy has something to check.

Until we have an answer, the CLI policy will default to `warn`, which changes nothing for
web-UI users.

## 4. Test vectors (the id computation must match byte for byte)

Ids are over the **ciphertext** (IV ‖ AES-GCM output), never the plaintext. Given ciphertext
bytes `c`, `hex = sha256(c).hexdigest()`:

| format | id |
|---|---|
| 1 (today) | `'obj-cas-imm-' + hex[:12]` |
| 2 | `'obj-cas-imm-' + hex[:32]` |

Concrete, for `c = b'sgit test vector 0001'` (21 ASCII bytes, used only as a vector):

```
sha256(c)  = 1abfd21f14308c611fe591dc4d6de2859249189637fd8d682c8d1d1515ef5479
format 1   = obj-cas-imm-1abfd21f1430
format 2   = obj-cas-imm-1abfd21f14308c611fe591dc4d6de285
```

We will ship these as fixtures in the CLI suite under `tests/unit/crypto/`.

Trees already use deterministic encryption (IV = HMAC-SHA256(key, plaintext)[:12]) so that
the same folder content gives the same tree id in both clients; that rule is unchanged.

## 5. What we are not asking

- No change to refs, the branch index file ids, keys, caches, tokens or auth headers.
- No change to the batch endpoint semantics. One expectation we now enforce client-side, for
  the record: a batch read result naming a `file_id` that was not requested is ignored by the
  CLI (0.18.0), because the id names where bytes are written on disk.
- No server-side verification of ids or signatures is required; the model stays zero-knowledge.

## 6. What we need back, and when

1. Q1 as a yes/no per surface, or the limits. This decides whether format 2 is a CLI-only
   change plus a web UI change, or also a server change.
2. Q2 and Q3 as a short assessment and, if work is needed, a rough size. We will not ship
   format 2 or a `required` signature policy until both clients handle them.
3. Anything else in the server or web UI that assumes 12-hex ids or unsigned commits.

The CLI side ships in this order regardless of the answers: the format gate, `author_key_id`
on new commits and signature verification in `warn` mode (0.19), ref monotonicity (0.20),
then format 2 once Q1 and Q2 are confirmed. Existing vaults are never touched by any of it.

*Background with the measurements: `team/humans/dinis_cruz/claude-code-web/10/07/history-integrity__cost-and-compatibility.md` in the SGit-AI__CLI repo.*
