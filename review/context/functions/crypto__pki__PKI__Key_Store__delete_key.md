## `delete_key` in sgit_ai/crypto/pki/PKI__Key_Store.py (L95-L101)

```python
# L96-L101
key_dir = self._key_dir(fingerprint)
if not os.path.isdir(key_dir): return False
import shutil
shutil.rmtree(key_dir)
return True
```

**Purpose:** `sgit pki delete <fingerprint>`: removes a key directory.

**Inputs & Assumptions:** `fingerprint` from argv (`CLI__PKI.py:L63`), passed through `_key_dir` with only `:`→`_`. Precondition for `rmtree` to stay inside `keys_dir`: the fingerprint has no `/`, `..` or leading `/`. **nothing found** in this slice enforcing it (see `load_key_pair`). `rmtree` on a symlinked directory raises by default (does not follow), and deletes everything under a real directory. Private PEMs are unlinked, not zeroed (contrast `Vault__Storage.secure_unlink`).

**Outputs & Effects:** bool; recursive delete.

**Cross-Function Dependencies:** `_key_dir`; `shutil.rmtree` (stdlib). Caller: `CLI__PKI.cmd_delete` L63. Tests: `test_PKI__Key_Store.py::test_delete_key`, `::test_delete_missing_key`, `tests/qa/crypto/test_CLI__PKI.py::test_delete_existing_key`.

**Open Questions:** as `load_key_pair` (argparse validation of the fingerprint).
