## `list_keys` in sgit_ai/crypto/pki/PKI__Key_Store.py (L42-L52)

```python
# L43-L52
keys_dir = str(self.keys_dir) if self.keys_dir else ''
if not keys_dir or not os.path.isdir(keys_dir): return []
result = []
for entry in sorted(os.listdir(keys_dir)):
    meta_path = os.path.join(keys_dir, entry, 'metadata.json')
    if os.path.isfile(meta_path):
        with open(meta_path, 'r') as f:
            result.append(json.load(f))
return result
```

**Purpose:** Enumerates own key pairs by their `metadata.json`; used by `sgit pki list` and by `PKI__Known_Keys` to match fingerprints.

**Inputs & Assumptions:** `self.keys_dir` (sanitised path). Every `metadata.json` under it is parsed as JSON and returned as-is; `json.load` errors propagate. Entries without metadata (partial keygen) are skipped silently.

**Outputs & Effects:** list of dicts in sorted directory order. Pure read.

**Cross-Function Dependencies:** Callers: `CLI__PKI.cmd_list` L48, `PKI__Known_Keys.lookup_by_fingerprint` L22 and `lookup_by_signing_fingerprint` L31. Tests: `test_PKI__Key_Store.py::test_list_keys_*`.

**Open Questions:** none.
