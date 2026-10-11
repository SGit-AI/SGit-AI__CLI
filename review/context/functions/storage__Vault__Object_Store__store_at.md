## `store_at` in sgit_ai/storage/Vault__Object_Store.py (L74-L82)

```python
# L75-L82
# WHY: deliberately breaks the CAS invariant — used by vault move to re-encrypt in-place under a new key
path = self.object_path(object_id)
if not force and os.path.isfile(path):
    return object_id
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'wb') as f: f.write(ciphertext)
return object_id
```

**Purpose:** Write arbitrary bytes under an arbitrary id; with `force=True` overwrite. The comment (L75) names the one intended user, `vault move`.

**Inputs & Assumptions:** `object_id`, `ciphertext`, `force` — no validation of any. **No callers in `sgit_ai/`** (grep over `sgit_ai` and `tests` finds only `tests/unit/storage/test_Vault__Object_Store__Store_At.py`). The `vault move` workflow (`sgit_ai/workflow/move/`) does not call it in this checkout — `Vault__Verified_Write.classify`'s docstring (L53) says move "now rewrites the ids", consistent with this being a leftover.

**Outputs & Effects:** Writes/overwrites `bare/data/<object_id>`. `tests/unit/storage/test_Vault__Object_Store__Store_At.py::test_store_at_does_not_validate_hash` pins that it does not verify.

**Cross-Function Dependencies:** Callee `object_path` L96. No callers.

**Open Questions:** whether this is intended to remain in the public surface of `Vault__Object_Store` given no caller.
