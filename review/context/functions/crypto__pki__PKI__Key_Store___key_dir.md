## `_key_dir` in sgit_ai/crypto/pki/PKI__Key_Store.py (L103-L105)

```python
# L104-L105
safe_name = fingerprint.replace(':', '_')
return os.path.join(str(self.keys_dir), safe_name)
```

**Purpose:** Maps a fingerprint (`sha256:<16hex>`) to its directory name (`sha256_<16hex>`).

**Inputs & Assumptions:** `fingerprint` (str): computed by `compute_fingerprint` on the keygen path (trusted shape); user argv on `load_key_pair`, `export_public_bundle`, `delete_key` (untrusted). The ONLY transformation is `:`→`_` (the variable name `safe_name` refers to that). Path separators, `..` and absolute paths pass through; `os.path.join` with an absolute `safe_name` returns `safe_name` alone. **nothing found** here.

**Outputs & Effects:** a path string; pure.

**Cross-Function Dependencies:** `str(self.keys_dir)` — sanitised `Safe_Str__Vault_Path`. Callers: L20, L55, L77, L96. `PKI__Keyring._contact_path` (L56-L58) is the same construction with a `.json` suffix.

**Open Questions:** none beyond the argparse question in `load_key_pair`.
