# `Vault__Backend__Local` file operations — sgit_ai/network/api/Vault__Backend__Local.py

A folder as a vault store: `root_path : Safe_Str__Vault_Path`. **No callers in `sgit_ai/`** (see `Vault__Backend__accessors`); exercised only by `tests/unit/api/test_Vault__Backend__Local.py`. Recorded because, if wired, `file_id` names a disk path.

---

## `read` (L14-L19)
`path = os.path.join(root, file_id)` (L15); `FileNotFoundError` if not a regular file (L16-L17); returns bytes. **Assumes** `file_id` stays under `root_path`: `os.path.join` with a `file_id` containing `..` or an absolute path leaves the root. Nothing here checks it: `nothing found`. (Contrast: `Vault__API__Static._location` L73-L81 refuses a resolved path outside the served folder; `Vault__Verified_Write.is_store_path` L29-L37 refuses non-store ids on the download side.)

## `write` (L21-L26)
Same join (L22), `os.makedirs(dirname)`, writes bytes, returns `{'status': 'ok', 'file_id': ...}`. Same containment assumption: `nothing found`. Mode: default umask (not `Vault__Secret_File`); the data is ciphertext.

## `delete` (L28-L32)
Same join; `os.remove` if a regular file; always `ok`. Same containment assumption.

## `exists` (L52-L54)
`os.path.isfile(join(root, file_id))`. Overrides `Vault__Backend.exists`.

See `network__api__Vault__Backend__Local__list_files.md` for the walk. No open questions beyond "is this class live?".
