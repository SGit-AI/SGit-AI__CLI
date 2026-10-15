# `PKI__Keyring` small methods in sgit_ai/crypto/pki/PKI__Keyring.py

Field: `keyring_dir : Safe_Str__Vault_Path = None` (L8) — sanitised path, see the Key_Manager accessors record. Set by `CLI__PKI.setup` L25.

---

## `get_contact` (L23-L28)
`_contact_path(fingerprint)`; `None` if not a file; else `json.load`. `fingerprint` is user argv on the `sgit pki encrypt --recipient` path (`CLI__PKI.py:L163` → `PKI__Known_Keys.lookup_by_fingerprint` L19 → here). Same unvalidated-shape rule as `PKI__Key_Store._key_dir`: only `:`→`_`; a `../x` or absolute value reads a JSON elsewhere on disk and treats it as a contact. **nothing found** here. Read only.

## `remove_contact` (L30-L35)
`os.remove` if the file exists. **No production caller** (grep: tests only).

## `list_contacts` (L37-L47)
Every `*.json` in `keyring_dir`, sorted, parsed. Errors propagate. Callers: `CLI__PKI.cmd_contacts` L98, `lookup_by_signing_fingerprint` L50.

## `lookup_by_signing_fingerprint` (L49-L53)
Linear scan of `list_contacts()`; FIRST contact whose `signing_fingerprint` equals the argument wins. Two contact files can carry the same signing fingerprint (files are named by ENCRYPTION fingerprint), in which case sorted-filename order decides who is reported as `signer`. **nothing found** that detects duplicates. Callers: `hybrid_decrypt` (`PKI__Crypto.py:L145`), `PKI__Known_Keys.lookup_by_signing_fingerprint` L28. Tests: `test_PKI__Keyring.py::test_lookup_by_signing_fingerprint*`.

## `_contact_path` (L55-L58)
`os.path.join(str(self.keyring_dir), f'{fingerprint.replace(":", "_")}.json')`. Same construction and caveat as `PKI__Key_Store._key_dir`.
