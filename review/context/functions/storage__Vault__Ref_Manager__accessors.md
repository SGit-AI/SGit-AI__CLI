# Remaining methods in sgit_ai/storage/Vault__Ref_Manager.py

## `is_initialized` (L47-L49)
`isdir(<vault_path>/bare/refs) and len(list_refs()) > 0`.

## `list_refs` (L51-L55)
Sorted names in `bare/refs` starting with `ref-pid-` (L9); missing dir → `[]`. A planted file not starting with the prefix is invisible.

## `ref_exists` (L57-L58)
`isfile(_ref_path(ref_id))`.

## `encrypt_ref_value` (L60-L63)
`crypto.encrypt(read_key, json.dumps({'commit_id': commit_id}).encode())` — the bytes pushed to the server for a ref (`Vault__Sync__Push.py:L862`, `Vault__Batch.py:L91`, `Step__Push__Update_Remote_Ref.py:L28`). Same no-AAD property as `write_ref` (TM-R03). Fresh IV, so the pushed bytes differ from the local file's bytes unless the caller also writes them locally — relevant to the CAS below.

## `get_ref_file_hash` (L65-L76)
Base64 of the **raw local ref file bytes**, used as the compare-and-swap expectation for the server (`Vault__Sync__Push.py:L201`). Docstring L67-L71: the server base64-decodes and compares raw content. This is why `Vault__Sync._fetch_branch_for_switch` L207-L210 writes the server's exact bytes rather than re-encrypting: a re-encryption (new IV) would make the local file differ from the server's and the CAS fail. `None` when the file is absent (L72-L73).

## `_ref_path` (L78-L79)
`os.path.join(self.vault_path, 'bare/refs', ref_id)` — `vault_path` is the sanitised `Safe_Str__Vault_Path` (see `storage__Vault__Object_Store__object_path.md`); `ref_id` unvalidated here, schema/HMAC-shaped at every caller found.
