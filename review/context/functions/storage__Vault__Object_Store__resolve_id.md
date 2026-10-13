## `resolve_id` in sgit_ai/storage/Vault__Object_Store.py (L99-L119)

```python
# L106-L119
raw = str(text or '').strip()
if not raw or self.exists(raw):
    return raw
hex_part = raw[len(OBJ_CAS_IMM_PREFIX):] if raw.startswith(OBJ_CAS_IMM_PREFIX) else raw
if not re.fullmatch(r'[0-9a-f]{4,32}', hex_part.lower()):
    return raw
prefix  = OBJ_CAS_IMM_PREFIX + hex_part.lower()
matches = [oid for oid in self.all_object_ids() if oid.startswith(prefix)]
if len(matches) == 1: return matches[0]
if len(matches) > 1: raise ValueError(...)
return raw
```

**Purpose:** Accept what `sgit history log` prints — full id, bare hex, or a unique hex prefix ≥ 4 — and return the full local id; anything else unchanged so the caller reports it (docstring L100-L104).

**Inputs & Assumptions:** `text` from the CLI (user). The early `self.exists(raw)` (L108) calls `object_path(raw)` → `isfile(<vault_path>/bare/data/<raw>)` with the user's string unvalidated — a user can pass `../refs/ref-pid-...` and `exists` says True, returning that string as an "object id", which the caller then passes to `load`. The user is already the local operator here (trust: trusted), so this is a usability observation, not a boundary.

**Outputs & Effects:** Pure (reads the data dir listing); `ValueError` on ambiguity (L116-L118).

**Cross-Function Dependencies:** Callees `exists` L93, `all_object_ids` L121. Callers: history/log/reset commands (not in slice; not read).

**Open Questions:** none.
