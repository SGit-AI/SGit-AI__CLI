## `object_id_hex_len` in sgit_ai/crypto/Vault__Crypto.py (L192-L198)

```python
# L194-L198
name = str(object_id or '').rsplit('/', 1)[-1]
if not name.startswith('obj-cas-imm-'):
    return 0
n = len(name) - len('obj-cas-imm-')
return n if n in (12, 32) else 0
```

**Purpose:** Reads the width (12 or 32) off an object id, accepting a path-qualified id (`bare/data/obj-cas-imm-…`) by taking the last path segment. Returns 0 for anything else, which `object_id_matches` turns into `False`.

**Inputs & Assumptions:** `object_id` (anything str-able, possibly None): Trust: **untrusted** (ids come from the host's index, refs and trees).

**Outputs & Effects:** 12, 32 or 0. Pure. Does NOT check that the tail is hex — only the length. `compute_object_id` + `==` in `object_id_matches` makes a non-hex tail fail the match anyway.

**Cross-Function Dependencies:** Callers: `object_id_matches` L202, `Vault__Inspector.py:L58`, `Vault__Publish.py:L205`.

**Open Questions:** none.
