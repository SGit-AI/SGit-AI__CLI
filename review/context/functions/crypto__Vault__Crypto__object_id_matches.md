## `object_id_matches` in sgit_ai/crypto/Vault__Crypto.py (L200-L203)

```python
# L202-L203
n = self.object_id_hex_len(object_id)
return bool(n) and self.compute_object_id(ciphertext, n) == str(object_id).rsplit('/', 1)[-1]
```

**Purpose:** The verify-before-write predicate: true only when the bytes hash to the id at the id's own width. Threat model §5 row 2 says this now sits on every download path; the call sites are `Vault__Verified_Write.py:L64`, `Vault__Object_Store.py:L140`, `Vault__Cache_Reader.py:L136`, `Vault__Sync__Tag.py:L191`, `Vault__Mirror.py:L156`.

**Inputs & Assumptions:**
- `object_id` (str): Trust: **untrusted** (from host-served index/refs/trees).
- `ciphertext` (bytes): Trust: **untrusted** (host-served).
- Precondition: none.

**Outputs & Effects:** bool; pure. A malformed id (width 0) is `False`, never an exception. The comparison is ordinary string equality (L203).

**Cross-Function Dependencies:**
- Callees `object_id_hex_len`, `compute_object_id` (internal).
- Callers (above) treat `True` as "the host did not substitute this object". What `True` does NOT establish: that this object belongs at this id's *role* (a valid object served under another object's name still matches only if the hash matches, so substitution is bounded to collisions, TM-R07) and nothing about mutable files (refs/index/keys have no content address: threat model §4).

**Open Questions:** none.
