## `readable` in sgit_ai/storage/Vault__Index_Reader.py (L44-L56)

```python
# L48-L56
if not isinstance(entry, dict) or not isinstance(entry.get('name'), str):
    return False
if COMMIT_SHAPED.match(entry['name']):
    return False
try:
    parsed = Schema__Tag_Ref.from_json(entry).json()
except Exception:
    return False
return all(k in parsed and parsed[k] == v for k, v in entry.items())
```

**Purpose:** "This version reads the entry exactly": it parses, has no unknown field, and parsing changes nothing (docstring L45-L47). Anything else is carried, not used.

**Inputs & Assumptions:** `entry` (raw dict from the index). Trust: semi-trusted (read-key authentic). `COMMIT_SHAPED` (L29: `^obj-cas-imm-[0-9a-f]+\Z`) refuses a tag whose *name* looks like a commit id (review eed8084 F6) — a tag named like that would otherwise be resolvable where a commit id is expected.

**Outputs & Effects:** Pure bool.

**Block-by-Block:**
- L53: `Schema__Tag_Ref.from_json(entry).json()` — `name : Safe_Str__Tag_Ref_Name` (strict `^[A-Za-z0-9._/\-]{1,100}\Z`), `tag_id : Safe_Str__Object_Id` (strict, lower-cased), `timestamp_ms : Safe_UInt`, `deleted : bool`. Unknown keys are dropped silently by `from_json` (see `parse`), which is exactly why L56 exists.
- L56: round-trip equality per original key. Catches (a) unknown keys (not in `parsed`), (b) coerced values (`tag_id` upper-case → lower-cased ≠ original; a string timestamp → int ≠ original; `deleted: 1` → `True ≠ 1` under `==`? In Python `True == 1` is True, so `deleted: 1` **passes** as readable — a minor looseness, `nothing found` that cares). (c) A `name` that `Safe_Str__Tag_Ref_Name` would trim/alter — `trim_whitespace=False`, strict → raises instead.

**Cross-Function Dependencies:** Callee `Schema__Tag_Ref.from_json`. Callers: `resolve` L84 only.

**Open Questions:** none material.
