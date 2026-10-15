## `decrypt_metadata` in sgit_ai/crypto/Vault__Crypto.py (L273-L276)

```python
# L274-L276
ciphertext = base64.b64decode(b64_ciphertext)
data       = self.decrypt(read_key, ciphertext)
return data.decode('utf-8')
```

**Purpose:** Inverse of both metadata encryptors; used wherever a commit message or a tree-entry field is shown or compared (`Vault__Sync.py:L307`, `Vault__Sub_Tree.py:L335-L350`, `Vault__Inspector.py:L124,L243`, `Vault__Diff.py:L100,L216`, `Vault__Sync__Fsck.py:L149`, pull, dump, history edit, move).

**Inputs & Assumptions:**
- `read_key` (bytes): trusted.
- `b64_ciphertext` (str): Trust: **untrusted** (from host-served objects). `base64.b64decode` with default `validate=False` silently discards characters outside the alphabet before decoding; the GCM tag then decides.
- Postcondition: `data.decode('utf-8')` raises `UnicodeDecodeError` if the authenticated plaintext is not UTF-8 — only a read-key holder could produce such a value.

**Outputs & Effects:** str, or raises (`binascii.Error`, `InvalidTag`, `UnicodeDecodeError`). Several callers wrap it in `try` (`Vault__Inspector.py:L243`), others do not.

**Cross-Function Dependencies:** Callee `decrypt` (internal, L301-L305). Callers above; `Vault__Sub_Tree.py:L340` additionally does `int(...)` on the result.

**Open Questions:** none.
