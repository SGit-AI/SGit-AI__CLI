# Vault Web — Timestamp field conventions in sgit schemas

**Date:** 2026-05-07
**Audience:** SG/Send Vault web team (`createFromToken` and any code that writes to `bare/...` objects)
**Triggering bug:** `sgit clone coral-bank-5246` failed with `Cannot convert '2026-05-07T01:28:18.495Z' to integer` because `Schema__Branch_Meta.created_at` was written as an ISO string instead of epoch milliseconds.

---

## TL;DR

Sgit uses **two distinct timestamp types** for different purposes. Both are valid; the choice depends on the field. Writing the wrong type into a field will fail to parse on the sgit side.

| Sgit type | Wire format | Where it's used |
|---|---|---|
| `Safe_UInt__Timestamp` | **Integer** — epoch milliseconds | All wire-protocol/object data: commits, branch index, change packs, stash, archive manifest |
| `Safe_Str__ISO_Timestamp` | **String** — `YYYY-MM-DDTHH:MM:SS[.fff]Z` (UTC, `Z` required) | Local audit/log records: migrations, transaction logs, workflow manifests, PKI key metadata |

**Rule of thumb for the web team:** if you're writing data that goes onto the SG/Send server (anything under `bare/`), it's almost always `Safe_UInt__Timestamp` — use **epoch milliseconds as integer**.

---

## The bug that triggered this debrief

```
$ sgit-ac clone coral-bank-5246
  ▸ Downloading vault index
error: Cannot convert '2026-05-07T01:28:18.495Z' to integer
```

`Schema__Branch_Meta.created_at` is declared as `Safe_UInt__Timestamp` in `sgit_ai/schemas/Schema__Branch_Meta.py:17`. The web client wrote an ISO string. Sgit's parser correctly rejected it.

The ISO format `'2026-05-07T01:28:18.495Z'` is valid `Safe_Str__ISO_Timestamp` — but it was written into the wrong field type. The fix is to convert to epoch ms before encrypting and writing.

---

## How to write each type from JavaScript

### `Safe_UInt__Timestamp` (the common case for wire data)

```javascript
// Right
created_at: Date.now()                       // 1714867698495  (integer)

// Right (if working from a Date object)
created_at: someDate.getTime()                // 1714867698495

// Wrong — this is an ISO string and will fail to parse
created_at: new Date().toISOString()          // '2026-05-07T01:28:18.495Z'
```

**Format:** non-negative integer, milliseconds since Unix epoch. Sgit's max is 99999999999999 (covers ~year 5138 — effectively unbounded).

**Validation when reading:** sgit's parser will reject any value that can't be parsed as a non-negative integer. Floats, strings, negative values all fail.

### `Safe_Str__ISO_Timestamp` (audit/log records, less common for web)

```javascript
// Right
applied_at: new Date().toISOString()          // '2026-05-07T01:28:18.495Z'

// Right (no milliseconds is also fine)
applied_at: '2026-05-07T01:28:18Z'

// Wrong — missing Z; non-UTC offsets not allowed
applied_at: '2026-05-07T01:28:18+00:00'
applied_at: '2026-05-07T01:28:18'

// Wrong — not a string (would fail Safe_Str validation)
applied_at: Date.now()
```

**Format:** ISO 8601 with required `Z` UTC suffix. Sub-second precision optional (1–3 digits). Max 30 chars. Regex: `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,3})?Z$`.

**Why the strictness?** Sgit's `Safe_Str__ISO_Timestamp` enforces UTC and a fixed format because mixing local times into an audit record creates ambiguity. If the web team encounters a field of this type, always use UTC.

---

## Field-by-field reference (for fields the web team is likely to write)

### `bare/indexes/<index-id>` → `Schema__Branch_Index`

Each entry in `branches[]` is a `Schema__Branch_Meta`:

```python
class Schema__Branch_Meta(Type_Safe):
    branch_id      : Safe_Str__Branch_Id
    name           : Safe_Str__Branch_Name
    branch_type    : Enum__Branch_Type
    head_ref_id    : Safe_Str__Ref_Id
    public_key_id  : Safe_Str__Key_Id
    private_key_id : Safe_Str__Key_Id
    created_at     : Safe_UInt__Timestamp    # ← INTEGER (epoch ms)
    creator_branch : Safe_Str__Branch_Id
```

**Web action:** write `created_at` as `Date.now()`, not `new Date().toISOString()`.

### `bare/data/<commit-id>` → `Schema__Object_Commit`

```python
class Schema__Object_Commit(Type_Safe):
    schema             : Safe_Str__Schema_Version
    tree_id            : Safe_Str__Tree_Id
    parents            : list[Safe_Str__Commit_Id]
    timestamp_ms       : Safe_UInt__Timestamp   # ← INTEGER (epoch ms)
    message_enc        : Safe_Str__Encrypted
    branch_id          : Safe_Str__Branch_Id
    public_key_id      : Safe_Str__Key_Id
    signature          : Safe_Str__Signature
    ...
```

**Web action:** write `timestamp_ms` as `Date.now()`.

### `bare/data/<change-pack-id>` → `Schema__Change_Pack` (rarely written by web today)

```python
class Schema__Change_Pack(Type_Safe):
    ...
    created_at   : Safe_UInt__Timestamp   # ← INTEGER (epoch ms)
```

### `.vault-settings` blob → `Schema__Vault_Settings` (incoming with brief 07)

```python
class Schema__Vault_Settings(Type_Safe):
    schema_version : Safe_UInt__Schema_Version
    vault_name     : Safe_Str__Vault_Name
    created        : Safe_Str__ISO_Timestamp     # ← STRING (ISO 8601, UTC, Z-required)
    created_by     : Safe_Str__Semver
```

Note: `.vault-settings.created` is `Safe_Str__ISO_Timestamp` — it's an audit record stored alongside human-readable user text, so ISO 8601 is the better fit. **This is the one case where the web team should use `toISOString()`.** Will land with brief 07.

### `Schema__Vault_Move_Record` (incoming with brief 02)

```python
class Schema__Vault_Move_Record(Type_Safe):
    from_vault_id  : Safe_Str__Vault_Id
    to_vault_id    : Safe_Str__Vault_Id
    rotated_at     : Safe_Str__ISO_Timestamp   # ← STRING (ISO 8601)
    ...
```

Audit record → ISO 8601. Same convention as `.vault-settings`.

---

## Quick reference: which to use when

If you're writing into a field you're unsure about, check the schema definition in `sgit_ai/schemas/`:

```bash
grep -rn "<field-name>" sgit_ai/schemas/
```

Then look at the type:
- Imported from `Safe_UInt__Timestamp` → integer (epoch ms)
- Imported from `Safe_Str__ISO_Timestamp` → ISO string

Or use this heuristic:
- Field name ends in `_ms` or is plain `created_at` / `timestamp_ms` / `duration_ms` → almost always integer
- Field appears in a "record" or "log" or "manifest" schema → often ISO string
- Field appears in a wire-protocol object (commit, tree, ref, index) → almost always integer

---

## What sgit will do better on its side

Brief 09 in the v0.14.x sprint adds structured error handling at every wire-boundary `Schema__*.from_json(...)` call. After it lands, the same `coral-bank-5246` failure will produce a far more actionable error:

```
error: Failed to parse Schema__Branch_Meta from
       branch <branch-id> in vault index;
       field "created_at" rejected value '2026-05-07T01:28:18.495Z';
       (underlying: Cannot convert ... to integer)

  This usually means the vault was created or modified by a client
  that wrote 'Schema__Branch_Meta' in an incompatible format.

  Likely causes:
    - The SG/Send web client wrote the data with a different type
      than sgit expects (e.g. ISO timestamp string instead of epoch
      milliseconds).
```

That makes the debugging loop fast even if a future field type mismatch slips through. But it doesn't replace getting the format right at the source — please use the right type per the field.

---

## Action items for the web team

1. **Audit `createFromToken`** for any `created_at` / `timestamp_ms` field written into objects under `bare/`. Convert to `Date.now()` (integer) where the schema declares `Safe_UInt__Timestamp`.
2. **Pull this debrief into the web team's reference docs** so future contributors don't repeat the mistake.
3. **Smoke test:** after the fix, run `sgit clone <newly-created-token>` against a vault freshly created via the web. The clone should succeed end-to-end — that confirms all wire-format types match.

If you hit a field where the type isn't obvious, ping back — happy to clarify against the schema source.
