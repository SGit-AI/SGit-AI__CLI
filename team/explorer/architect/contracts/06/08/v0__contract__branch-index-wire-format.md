# Contract v0 — Branch-Index Wire Format (CLI side draft)

**Version:** v0 — DRAFT pending Web mark-up
**Date:** 8 June 2026
**Owners:** SGit-AI CLI Architect (this document) + SG/Vault Web Architect (pending counter-sign)
**Status:** Draft for Web team mark-up. Citations point at live CLI code at `sgit_ai/_version.py == v0.1.0`. Once both sides sign, the citations become normative and any change to a pinned citation requires a contract amendment (§12).
**Supersedes:** nothing.

**Inputs (CLI side):**
- `team/humans/dinis_cruz/claude-code-web/06/08/cli-response__round-2-web-index-payload-bugs.md` (Round-2 bug-flagging brief — the empirical cause of this contract)
- `team/humans/dinis_cruz/claude-code-web/06/08/cli-response__clone-fails-no-branch-index-web-only-vault.md` (Round-1 brief — the absent-index fallback this contract pins in §9)
- The Web v0.33.5 reply (`web-response__cli-interop-fixed-branch-index-and-reconcile.md`) — proposed §7 contract structure (`display_name` + reference-payloads appendix). Referenced from memory of the chat record; CLI side is drafting from its quoted §-numbered claims.
- Live CLI code (see citations throughout).
- `team/explorer/architect/reviews/06/04/v0.1.0__architect-review__read-only-clone-contract.md` (storage-layout reference for `bare/indexes/`)

**Related reviews:**
- `team/explorer/architect/reviews/06/04/v0.1.0__architect-review__read-only-clone-contract.md`
- `team/explorer/architect/reviews/05/13/v0.1.0__architect-review__remote-config-health-and-migration.md`

---

## 1. Scope

This contract covers, exactly:

- The **encrypted branch-index object** stored at `bare/indexes/{index_file_id}` (its plaintext shape, its derivation, its envelope, its storage path, the lookup semantics for the named branch, and the tolerated encoding variants).

This contract **pins by reference, not by re-definition**:

- The **AES-GCM envelope** used for the index ciphertext — same envelope used for ref objects, refs already interop-verify between CLI and Web (cite `sgit_ai/crypto/Vault__Crypto.py:199-210`). See §5.
- The **HMAC-SHA256 file-id derivation primitive** used for refs — same primitive used for the index id (cite `Vault__Crypto.py:65-67`). See §4.

This contract **does NOT cover**:

- The shape, derivation, or storage of ref objects themselves (already mutually verified during the v0.33.5 round).
- Any web-side architecture (single-vault store, per-vault commit semantics, publish vs commit).
- Any CLI-side architecture (workflow steps, key-derivation helpers).
- The vault-key format, the `read_key` derivation chain (PBKDF2), or the `vault_id` grammar — all of these are upstream of this contract and unchanged.

This contract is **a wire-format contract**, not a feature spec. It says what bytes go on disk at the index path and how they are read; it does not say when or why either side writes them.

---

## 2. Wire format — `branch_index_v1` plaintext

The plaintext (post-AES-GCM-decrypt) of the index ciphertext is **a UTF-8 JSON document** matching `Schema__Branch_Index.from_json(...)` (`sgit_ai/schemas/Schema__Branch_Index.py:7-9`).

### 2.1 Root object

| Field      | Type                              | Required | Citation                              | Notes |
|------------|-----------------------------------|----------|---------------------------------------|-------|
| `schema`   | `Safe_Str__Schema_Version`        | required | `Schema__Branch_Index.py:8`           | MUST equal `"branch_index_v1"` for this contract version. Grammar: `^[a-z_]+_v\d+$` (`sgit_ai/safe_types/Safe_Str__Schema_Version.py:5`). |
| `branches` | `list[Schema__Branch_Meta]`       | required | `Schema__Branch_Index.py:9`           | MUST contain exactly one entry with `name == "current"` for any vault that wants the CLI to clone or read it. May contain zero or more additional clone branches. |

**Unknown extra fields at the root** MUST be tolerated by receivers (CLI verified empirically — Type_Safe `from_json` silently drops unknown keys). Producers SHOULD NOT add unknown root fields in `v1`; instead, bump to `branch_index_v2` (§11).

### 2.2 `Schema__Branch_Meta` — per-branch row

Citation: `sgit_ai/schemas/Schema__Branch_Meta.py:10-19` (live code, all fields below).

| Field            | Wire type / source           | Required | Receiver action                                        | Producer rule |
|------------------|------------------------------|----------|--------------------------------------------------------|---------------|
| `branch_id`      | `Safe_Str__Branch_Id`        | required | Lookup id; presence verified; format-checked on parse  | MUST match regex `^branch-(named\|clone)-[0-9a-f]{8,64}$` (`sgit_ai/safe_types/Safe_Str__Branch_Id.py:5`). Opaque. NOT a human label. |
| `name`           | `Safe_Str__Branch_Name`      | required | **Lookup key for the named branch** — see §7          | MUST equal `"current"` for the named branch row. Grammar: `^[a-zA-Z0-9_\-]{1,64}$` (`sgit_ai/safe_types/Safe_Str__Branch_Name.py:5`). |
| `branch_type`    | `Enum__Branch_Type`          | required | Dispatch on `"named"` vs `"clone"`                    | MUST be `"named"` for the `name="current"` row. Other rows MAY be `"clone"`. Source enum: `sgit_ai/safe_types/Enum__Branch_Type.py`. |
| `head_ref_id`    | `Safe_Str__Ref_Id`           | required | Resolves to a ciphertext at `bare/refs/{head_ref_id}`  | MUST match regex `^ref-pid-(muw\|snw)-[0-9a-f]{12}$` (`sgit_ai/safe_types/Safe_Str__Ref_Id.py:5`). For `branch_type=="named"`, MUST start `ref-pid-muw-`; for `branch_type=="clone"`, by convention `ref-pid-snw-`. |
| `public_key_id`  | `Safe_Str__Key_Id`           | optional | Loaded for signature verification when present         | Grammar `^key-rnd-imm-[0-9a-f]{8,64}$` (`sgit_ai/safe_types/Safe_Str__Key_Id.py:5`). |
| `private_key_id` | `Safe_Str__Key_Id`           | optional | Loaded for signing when present                        | MUST be absent (`null`) on clone-branch rows (private key stored locally per `Schema__Branch_Meta.py:16` comment). |
| `created_at`    | int-ms OR ISO-8601 string    | optional | Parsed via `Timestamp_Now` (accepts both encodings)    | See §8 for canonical-emit recommendation. Default if omitted: `Timestamp_Now(0)` (`Schema__Branch_Meta.py:17`). |
| `creator_branch` | `Safe_Str__Branch_Id` or null | optional | Audit / lineage display                                | Same grammar as `branch_id`. `null` for the initial named branch. |
| `display_name`   | `Safe_Str__Branch_Name`      | optional | **NEVER used for lookup.** Display only.               | New field added in CLI v0.1.0 in anticipation of this contract (`Schema__Branch_Meta.py:19`). Producers MAY emit a human label here (e.g., `"main"`) while keeping `name=="current"`. Receivers MUST ignore for lookup; MAY surface in UI. |

### 2.3 Reference payload — single named branch

Pasted verbatim from `Schema__Branch_Index(schema='branch_index_v1', branches=[Schema__Branch_Meta(...)]).json()`:

```json
{
  "schema": "branch_index_v1",
  "branches": [
    {
      "branch_id":      "branch-named-0123456789abcdef",
      "name":           "current",
      "branch_type":    "named",
      "head_ref_id":    "ref-pid-muw-da0dea46b649",
      "public_key_id":  null,
      "private_key_id": null,
      "created_at":     1717851600000,
      "creator_branch": null,
      "display_name":   "main"
    }
  ]
}
```

Notes:
- `display_name:"main"` is the **web's preferred human label**; the CLI ignores it for lookup. The web UI MAY show "main" everywhere; on the wire, the lookup name MUST remain `"current"`.
- `created_at` is shown as int-ms (canonical emit format, §8). The ISO-8601 form `"2026-06-08T13:00:00Z"` is also accepted by parsers on both sides.
- `null` for optional fields is the JSON encoding of Python `None` in `Type_Safe`'s `.json()` output; receivers MAY also tolerate the field being absent entirely (verified empirically).

(See §10 for a second fixture covering the multi-branch case.)

---

## 3. Determinism property — `branch_id` ↔ `index_file_id` tail (RECOMMENDED, not REQUIRED)

If the **web** derives the named branch's `branch_id` as:

```
branch_id = "branch-named-" + HMAC-SHA256(read_key, "sg-vault-v1:file-id:branch-index:{vault_id}").hex()[:12]
```

— i.e., the same 12-hex tail as the `index_file_id` — then a vault-spot-check tool can verify the two ids share a tail. This is a **convenience for debugging** (the web team flagged it as a useful spot-check in their §3).

CLI receivers do **NOT** enforce this property. `Safe_Str__Branch_Id` accepts any conforming `^branch-(named|clone)-[0-9a-f]{8,64}$`, and `get_branch_by_name(index, 'current')` does not inspect the tail (`sgit_ai/storage/Vault__Branch_Manager.py:100-104`). The CLI's own `Vault__Branch_Manager.create_named_branch` uses `secrets.token_hex(8)` (`Vault__Branch_Manager.py:30`), which is **non-deterministic** — so a CLI-created and a web-created vault will have different `branch_id` tails by construction, both valid.

**Recommendation:** Producers MAY use either scheme. The opaque-random scheme remains the default for CLI; the deterministic scheme is acceptable as long as it stays within the §2 regex.

**OPEN — for Web team:** confirm whether the web wants this pinned as `MUST` (deterministic) or `MAY` (convenience). Default if no reply: leave as `MAY`.

---

## 4. Identifier derivation — `index_file_id`

The on-disk file name is `idx-pid-muw-{HMAC-SHA256(read_key, domain)[0:12].hex()}` where `domain = "sg-vault-v1:file-id:branch-index:{vault_id}"`.

### 4.1 Live code

| Step                                       | Citation                                            |
|--------------------------------------------|-----------------------------------------------------|
| Domain string constant                     | `Vault__Crypto.py:36` — `BRANCH_INDEX_DOMAIN = 'sg-vault-v1:file-id:branch-index'` |
| Bare tail derivation (returns 12 hex chars)| `Vault__Crypto.derive_branch_index_file_id:73-75`   |
| HMAC primitive (returns first 12 hex chars)| `Vault__Crypto.derive_file_id:65-67`                |
| Stored-id prefix concatenation (caller)    | `Vault__Crypto.derive_keys:89`, `Vault__Crypto.derive_keys_from_simple_token:119`, `Vault__Crypto.import_read_key:132`, `Vault__Transfer.collect_head_files:77` |

### 4.2 The two layers — bare tail vs stored file id

The contract distinguishes:

- **Bare tail:** `derive_branch_index_file_id(read_key, vault_id) -> "b69ec449a18c"` (12 hex chars, no prefix). Returned by `Vault__Crypto`.
- **Stored file id:** `"idx-pid-muw-" + bare_tail -> "idx-pid-muw-b69ec449a18c"` (24 chars). The string actually used as a path component at `bare/indexes/{stored_file_id}`. Grammar: `^idx-pid-muw-[0-9a-f]{12}$` (`sgit_ai/safe_types/Safe_Str__Index_Id.py:5`).

The `idx-pid-muw-` prefix is a **caller-side concern** on the CLI: `Vault__Crypto.derive_branch_index_file_id` returns the bare tail; every caller (`derive_keys:89`, `derive_keys_from_simple_token:119`, `import_read_key:132`, `Vault__Transfer.py:77`) concatenates `"idx-pid-muw-"` themselves. Both sides MUST emit the prefix when writing to or reading from `bare/indexes/`.

### 4.3 Required equality (test vector)

For any `read_key` (32 bytes), `vault_id` (matching `Vault__Crypto.VAULT_ID_PATTERN`):

```
index_file_id == "idx-pid-muw-" +
                 hmac_sha256(read_key, b"sg-vault-v1:file-id:branch-index:" + vault_id_bytes)
                 .hexdigest()[0:12]
```

The CLI side has verified this empirically against the live `test-vault-1` derivation (round-1 brief, §3): `vault_id == "7y6uk6gj"` → `index_file_id == "idx-pid-muw-b69ec449a18c"`. The web side claims byte-equality with this derivation (their §3); pinning this here as a **shared test vector** turns any future drift into a failing test on both sides.

**Acceptance:** both sides MUST publish a unit test that asserts the above for at least one known `(read_key, vault_id)` pair. CLI side: an existing test under `tests/unit/crypto/` covers `derive_branch_index_file_id` and `derive_keys`; the contract requires this is augmented with the literal `"idx-pid-muw-{tail}"` value, not just the bare tail. (Action: hand-off to QA.)

---

## 5. Crypto envelope (BY REFERENCE)

The branch-index ciphertext uses the **same AES-256-GCM envelope as ref objects**, which already interop-verifies between CLI and Web.

| Aspect              | Value / citation                                                                                       |
|---------------------|--------------------------------------------------------------------------------------------------------|
| Algorithm           | AES-256-GCM (no AAD)                                                                                   |
| IV length           | 12 bytes, random (`os.urandom`) on encrypt — `Vault__Crypto.encrypt:199-204`                            |
| Tag length          | 16 bytes, appended by `AESGCM.encrypt` after the ciphertext (Web Crypto's `AES-GCM` append is identical) |
| Wire layout         | `IV(12) ‖ ciphertext_with_tag` — `Vault__Crypto.encrypt:204`, mirrored by `Vault__Crypto.decrypt:206-210` |
| Key                 | `read_key` (32 bytes, from PBKDF2 — `Vault__Crypto.derive_read_key:57-59`)                              |
| Plaintext           | `json.dumps(Schema__Branch_Index(...).json()).encode()` — the §2 JSON document, UTF-8 encoded           |
| AES-GCM AAD         | `None` — same as refs (`encrypt:203`: `aesgcm.encrypt(iv, plaintext, None)`)                            |

**Structural test-vector property:** an index byte-vector is **structurally equivalent** to a ref byte-vector with the index plaintext substituted. There is no need for a separate envelope test fixture; reuse the ref-vector test machinery, plug in the §2.3 fixture A as the plaintext, and verify byte-equality of the ciphertext (modulo the random IV — the deterministic case requires the producer to fix the IV in the test).

**Recommendation:** QA SHOULD add one fixed-IV interop test for the index, structured identically to the existing fixed-IV ref interop test, using §2.3 fixture A's plaintext.

---

## 6. Storage path

The encrypted index lives at:

```
bare/indexes/{index_file_id}
```

where `index_file_id` is the stored-file-id form (§4.2).

| Layout constant              | Citation                                                                 |
|------------------------------|--------------------------------------------------------------------------|
| `'indexes'` segment          | `sgit_ai/storage/Vault__Storage.py:12` — `BARE_INDEXES = 'indexes'`       |
| `bare_indexes_dir(directory)`| `Vault__Storage.py:39-40`                                                |
| `index_path(directory, ...)` | `Vault__Storage.py:102-103`                                              |
| Wire path on download        | `sgit_ai/workflow/clone/Step__Clone__Download_Index.py:44` — `f'bare/indexes/{index_id}'` |

**Note on the prior path-mismatch finding:** the Round-1 brief documented that an earlier web revision used `bare/idx/` while the CLI uses `bare/indexes/`. The v0.33.5 web fix moved to `bare/indexes/` (the web team's §2 + their §5 fixture). This contract pins `bare/indexes/` as the canonical, normative path. **Producers MUST NOT write to `bare/idx/`.** Receivers MUST NOT read from `bare/idx/`.

---

## 7. Lookup semantics — finding the named branch

The named-branch row MUST be located by `get_branch_by_name(index, "current")`.

| Lookup primitive            | Citation                                                                 |
|-----------------------------|--------------------------------------------------------------------------|
| `get_branch_by_name(...)`   | `sgit_ai/storage/Vault__Branch_Manager.py:100-104`                       |
| Comparison key              | `str(branch.name) == name` — `Vault__Branch_Manager.py:102`              |

The literal `'current'` is the canonical lookup key, hardcoded at minimum at the following CLI sites (verified by grep at `sgit_ai/_version.py == v0.1.0`):

- `sgit_ai/core/Vault__Sync.py:88` — initial creation
- `sgit_ai/workflow/clone/Step__Clone__Download_Index.py:102, 104, 139` — clone resolve + fallback synth
- `sgit_ai/workflow/clone/Step__Clone__ReadOnly__Setup_Config.py:22` — `DEFAULT_BRANCH_NAME = 'current'`
- `sgit_ai/workflow/pull/Step__Pull__Load_Branch_Info.py:42`
- `sgit_ai/workflow/pull/Step__Pull__RO__Load_Named_Head.py:8` (default via `_tracked_branch_name`)
- `sgit_ai/workflow/fetch/Step__Fetch__Load_Branch_Info.py:34`
- `sgit_ai/workflow/push/Step__Push__Local_Inventory.py:36`
- `sgit_ai/core/actions/push/Vault__Sync__Push.py:73`
- `sgit_ai/core/actions/status/Vault__Sync__Status.py:109`
- `sgit_ai/core/actions/backup/Vault__Restore.py:196`
- `sgit_ai/core/actions/diff/Vault__Diff.py:782`
- `sgit_ai/core/Vault__Sync__Base.py:101, 107, 110, 113, 117, 127` — default in shared helper

The Round-2 brief documented this same set of callsites as the reason that `name:"main"` was a blocking break.

**Rule:** Producers MUST emit `name == "current"` for the named-branch row. Receivers MUST NOT lookup by `branch_id`, `display_name`, or any web-side label. Receivers MUST NOT change the literal `'current'` without a contract amendment.

**Human label:** producers MAY emit a human label in `display_name` (e.g., `"main"`); receivers MAY surface it. See §2.2.

---

## 8. Encoding tolerances and canonical emit

### 8.1 `created_at` accepts two encodings

`Timestamp_Now` (`Schema__Branch_Meta.py:17`) accepts:

- **int milliseconds** (default; `Timestamp_Now(0)`, `int(time.time()*1000)`)
- **ISO-8601 string** (`"2026-06-08T13:00:00Z"`, `"2026-06-08T13:00:00+00:00"`) — parsed by `Timestamp_Now.parse_string_value` (osbot-utils package, verified at the live install path during this review).

Both sides MUST tolerate both forms on read.

### 8.2 Canonical emit format (RECOMMENDED)

**Both producers SHOULD emit `created_at` as int milliseconds.** Rationale:
- `Timestamp_Now`'s `.json()` representation is integer-valued (`__str__ -> str(int(self))`).
- The CLI emits int-ms by construction (`Vault__Branch_Manager.create_named_branch:28` — `int(time.time() * 1000)`).
- Tolerating both forever is fine; recommending one as canonical avoids a "prefer X" wrinkle that complicates spec evolution.

**OPEN — for Web team:** confirm whether the web is willing to emit int-ms canonically (its read parser already accepts both). Default if no reply: pin as `RECOMMENDED int-ms`, both forms remain valid on read.

### 8.3 Unknown extra fields are tolerated

`Type_Safe.from_json` silently drops unknown keys on both `Schema__Branch_Index` and `Schema__Branch_Meta`. Receivers MUST tolerate unknown extra fields. Producers SHOULD NOT rely on unknown fields making it across; if a field needs to be guaranteed, add it to this contract and bump to `branch_index_v2` (§11).

### 8.4 `null` for optional fields

Optional fields (`public_key_id`, `private_key_id`, `creator_branch`, `display_name`) MAY be `null` on the wire (Python `None` → JSON `null`) or absent entirely. Both are equivalent on read. Producers MAY emit either; receivers MUST tolerate both.

---

## 9. Receiver resilience contract

Both sides MUST tolerate the following malformed-index conditions by **degrading to the single-branch fallback** (§9.1), NOT by crashing the operation.

### 9.1 Degrade conditions (CLI side already shipped)

The CLI implements the receiver resilience in `sgit_ai/workflow/clone/Step__Clone__Download_Index.py:49-66`:

| Condition                                                  | Action                                                                                                           | CLI citation                                  |
|------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|------------------------------------------------|
| Index present, decrypt or parse failure (any `Exception`)  | Synthesise a single-branch index from the deterministic named ref (§9.1.1)                                       | `Step__Clone__Download_Index.py:98-101`        |
| Index present, parses, no branch matches `name=="current"` | Same — synthesise the single-branch index                                                                        | `Step__Clone__Download_Index.py:102-104`       |
| Index absent (404 on read)                                 | Same — synthesise the single-branch index                                                                        | `Step__Clone__Download_Index.py:67-71`         |
| Index forbidden (403 on read)                              | **MUST surface honestly as access denied** — never mask as "no index"                                            | `Step__Clone__Download_Index.py:79-87`         |

This is a `MUST` for the receiver. It absorbs:
- Foreign-named single named branch (e.g., a future producer emits `name=="main"`).
- Malformed `branch_id` (e.g., the Round-2 `branch-named-main` payload).
- An unrecognised `branch_type` value.
- Partial writes during a producer's update.

#### 9.1.1 Single-branch fallback synth (the §9 receiver-side recipe)

When the receiver degrades, it synthesises:

```python
Schema__Branch_Meta(
    branch_id   = 'branch-named-' + derive_file_id(read_key, f'branch:current:{vault_id}'),
    name        = 'current',
    branch_type = Enum__Branch_Type.NAMED,
    head_ref_id = 'ref-pid-muw-' + derive_ref_file_id(read_key, vault_id))
```

— see `Step__Clone__Download_Index.py:137-141`. The synthesised index uses a deterministic, derived `branch_id` so subsequent runs are stable. The fallback is **gated on the named ref actually existing** on the server (`Step__Clone__Download_Index.py:118-135`) — if neither the index NOR the named ref is present, the receiver MUST surface a clear "nothing to clone" error (see same lines), not crash silently.

### 9.2 Producer resilience contract

Producers MUST NOT:
- Emit a `branch_id` violating the §2 regex (the round-2 break).
- Emit a `name` other than `"current"` for the named-branch row (the round-2 break).
- Emit a `head_ref_id` violating the §2 regex.
- Write to `bare/idx/` (the legacy path).

Producers MAY:
- Add unknown fields to `Schema__Branch_Meta` rows for forward compatibility (but receivers will silently drop them per §8.3; these fields are best treated as ephemeral).
- Emit `display_name` for a human label (§2.2, §7).

### 9.3 Access-denied honesty (MUST)

A 403 on the index read is **NOT** a malformed-index condition. It is an access-control problem (the vault requires an access key the client lacks). Receivers MUST distinguish 403 from 404 and surface 403 as access-denied with an actionable hint. CLI implementation: `Step__Clone__Download_Index._raise_if_forbidden:79-87`.

This is `MUST` because masking 403 as "no index" caused round-1 confusion on the `test-vault-1` Access Key case — the user is then told to "Publish in the web UI", which doesn't fix the access problem.

---

## 10. Reference payloads (appendix)

Both sides SHOULD paste these into a shared interop test and verify their producer emits a payload conformant to one of these shapes.

### 10.1 Fixture A — single named branch (the v0.33.5 case)

Same as §2.3. Reproduced here for completeness:

```json
{
  "schema": "branch_index_v1",
  "branches": [
    {
      "branch_id":      "branch-named-0123456789abcdef",
      "name":           "current",
      "branch_type":    "named",
      "head_ref_id":    "ref-pid-muw-da0dea46b649",
      "public_key_id":  null,
      "private_key_id": null,
      "created_at":     1717851600000,
      "creator_branch": null,
      "display_name":   "main"
    }
  ]
}
```

**Interop assertion (both sides):**
```
Schema__Branch_Index.from_json(fixture_A).json() == fixture_A
get_branch_by_name(Schema__Branch_Index.from_json(fixture_A), 'current').head_ref_id == 'ref-pid-muw-da0dea46b649'
```

### 10.2 Fixture B — multi-branch (CLI-emitted today; web does not yet write multi-branch)

This shape represents what the CLI emits today for a vault with a named branch and one clone branch (the common state after `sgit clone` + a local commit). The web does not yet write multi-branch indexes; this fixture pins the shape for when it does.

```json
{
  "schema": "branch_index_v1",
  "branches": [
    {
      "branch_id":      "branch-named-0123456789abcdef",
      "name":           "current",
      "branch_type":    "named",
      "head_ref_id":    "ref-pid-muw-da0dea46b649",
      "public_key_id":  "key-rnd-imm-aaaa0000bbbb1111",
      "private_key_id": "key-rnd-imm-cccc2222dddd3333",
      "created_at":     1717851600000,
      "creator_branch": null,
      "display_name":   null
    },
    {
      "branch_id":      "branch-clone-fedcba9876543210",
      "name":           "alice-laptop",
      "branch_type":    "clone",
      "head_ref_id":    "ref-pid-snw-1122334455aa",
      "public_key_id":  "key-rnd-imm-eeee4444ffff5555",
      "private_key_id": null,
      "created_at":     1717952600000,
      "creator_branch": "branch-named-0123456789abcdef",
      "display_name":   null
    }
  ]
}
```

**Interop assertions (both sides):**
```
get_branch_by_name(index, 'current').branch_type == Enum__Branch_Type.NAMED
get_branch_by_name(index, 'current').head_ref_id.startswith('ref-pid-muw-')
get_branch_by_name(index, 'alice-laptop').branch_type == Enum__Branch_Type.CLONE
get_branch_by_name(index, 'alice-laptop').head_ref_id.startswith('ref-pid-snw-')
get_branch_by_name(index, 'alice-laptop').private_key_id is None  # clone-branch private key is local-only
```

**OPEN — for Web team:** Fixture B currently encodes the CLI's clone-branch convention (`ref-pid-snw-`, `private_key_id == null`, `creator_branch` set). The web's `ref-pid-snw-web-ui` is the same family. Confirm whether the web wants to define its own clone-branch row when it writes one, or accept this shape. Default if no reply: pin Fixture B as the CLI-emitted reference, web aligns at its own pace.

---

## 11. Versioning and compatibility

### 11.1 Version bump rule

This contract is `branch_index_v1`. The `schema` string MUST be exactly `"branch_index_v1"`.

A version bump (`branch_index_v2`) is REQUIRED when any of the following changes:

- A new MUST-required root field is added.
- An existing field's type, encoding, or regex changes incompatibly.
- An existing field is removed or renamed.
- The lookup name (`"current"`) is changed.
- The storage path (`bare/indexes/`) is changed.
- The crypto envelope (§5) is changed.
- The file-id derivation domain string (`sg-vault-v1:file-id:branch-index`) is changed.

A version bump is NOT REQUIRED when:

- A new optional field is added with a tolerated default.
- A new optional value is added to an existing enum, AND the receiver-resilience clause (§9.1) covers the unknown-value case.
- A clarification or test vector is added.

### 11.2 Within-`v1` rules

Within `v1`, fields can only be **added** (as optional, with a tolerated default). Renames, type changes, and removals are forbidden. Receivers MUST tolerate unknown extra fields (§8.3).

### 11.3 Mixed-version vaults

If a receiver encounters `schema != "branch_index_v1"`, the behaviour is governed by the receiver-resilience clause (§9.1): the parse will fail at the `Safe_Str__Schema_Version` regex check or at the `schema` value check, and the receiver MUST degrade to the single-branch fallback rather than crash.

**OPEN — for Web team:** confirm whether `v2` should be defined defensively now (e.g., reserve a `display_label` root field for the human label of the whole vault) or strictly on need. Default if no reply: define `v2` only when a concrete need arises.

---

## 12. Change control

| Change type                                                             | Procedure |
|-------------------------------------------------------------------------|-----------|
| **Contract amendment** — touches any pinned-by-citation rule in §2-§9   | Requires both CLI Architect and Web Architect to counter-sign a follow-up contract revision. The amendment MUST cite the old + new code locations, the rationale, the migration path for existing vaults, and the receiver-resilience update if any. |
| **Implementation change** — code citation moves, no behaviour change    | Implementer updates the citation in the next contract revision; no counter-sign required if the rule itself (regex, enum value, key string, path constant) is unchanged byte-for-byte. |
| **Implementation change** — adds a tolerated-but-unused field           | No amendment required; document in next revision under §8.3. |
| **Test vector addition**                                                | No amendment required; addition only. Either side can propose. |

### 12.1 Test-suite enforcement (MUST)

Both sides MUST land a unit test that:

1. Parses Fixture A (§2.3 / §10.1) into the receiver's `Schema__Branch_Index` equivalent without error.
2. Asserts `get_branch_by_name(parsed, 'current').head_ref_id == 'ref-pid-muw-da0dea46b649'` (or equivalent on the web).
3. Asserts the `index_file_id` derivation in §4.3 for at least one known `(read_key, vault_id)`.
4. Asserts the receiver-resilience clause (§9.1): given a payload with `branch_id="branch-named-main"` AND `name="main"`, the receiver degrades to the single-branch fallback (does NOT crash).

CLI-side test for (4): the multi-condition degrade test (delete index OR present-but-malformed) is the QA hand-off. The CLI shipped the production code (§9.1) before the contract was signed; the matching test MUST follow. (Action: QA.)

---

## 13. Open questions for Web team mark-up

Consolidated from inline OPEN markers:

| # | Section | Question | CLI default if no reply |
|---|---------|----------|-------------------------|
| Q1 | §3 | Should the `branch_id` ↔ `index_file_id` tail-determinism be `MUST` or `MAY`? | MAY (recommendation only) |
| Q2 | §8.2 | Will the web emit `created_at` as int-ms canonically? | int-ms RECOMMENDED, ISO-8601 also valid on read |
| Q3 | §10.2 | Is Fixture B's clone-branch shape acceptable to the web, or does the web want a different `ref-pid-snw-` convention? | CLI's shape pinned as reference |
| Q4 | §11.3 | Define `v2` defensively now, or wait for a concrete need? | Wait for a concrete need |
| Q5 | §2.2 | Confirm the web is willing to emit `display_name` and treat `name:"current"` as the wire lookup name (separation pinned). | Yes (this matches their v0.33.5 fix intent) |

Receivers on both sides also have one shared task (Action: QA on both sides): cross-check the §10 fixtures against the actual on-wire payload from `test-vault-1` once the web's v0.33.5 fix lands in production. If they differ, the difference is a contract violation by definition — file an amendment per §12.

---

## 14. Summary — what changed vs. what's pinned

| What this contract pins                              | What was previously implicit                              |
|------------------------------------------------------|-----------------------------------------------------------|
| `name == "current"` is the named-branch lookup key   | Hardcoded in CLI; round-2 break came from web not knowing |
| `branch_id` regex is opaque, not a human label       | Round-2 break: web emitted `branch-named-main`            |
| `bare/indexes/` is the canonical storage path        | Round-1 break: web wrote to `bare/idx/`                   |
| Receivers degrade malformed index → single-branch    | Round-1 fix; round-2 elevated as receiver MUST            |
| 403 surfaces honestly, never as "no index"           | Round-1 fix                                               |
| `display_name` is the optional human label slot      | Implicit in the round-2 negotiation; now spec'd           |
| `created_at` accepts int-ms AND ISO-8601             | Tolerated by `Timestamp_Now`; now spec'd                  |
| Crypto envelope = same as refs (BY REFERENCE)        | True empirically; never written down                       |
| `index_file_id` derivation is HMAC-SHA256 of domain  | True in code; first time pinned with test vector          |

---

## End notes

This is a wire-format contract. It does not prescribe when either side writes the index, how the producer derives the named branch's signing keys, or what the receiver does with the named-branch HEAD once resolved. It only pins what bytes appear at the wire and how those bytes are decoded.

Future evolution: contract amendments per §12. Future `branch_index_v2`: §11.

— End of contract v0 (CLI-side draft). —
