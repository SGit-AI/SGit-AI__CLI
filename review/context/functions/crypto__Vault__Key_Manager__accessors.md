# `Vault__Key_Manager` small methods in sgit_ai/crypto/Vault__Key_Manager.py

Class fields (L14-L16): `vault_path : Safe_Str__Vault_Path = None`, `crypto : Vault__Crypto`, `pki : PKI__Crypto`. Instances are built per command with `vault_path=sg_dir` (`Vault__Sync__Base.py:L378`, `Vault__Sync.py:L65`, workspaces).

**Field rule that spans every path method here:** `Safe_Str__Vault_Path` is a REPLACE-mode, non-strict `Safe_Str` (`sgit_ai/safe_types/Safe_Str__Vault_Path.py:L4-L10`; `osbot_utils/.../Safe_Str.py:L18-L20, L77`): assigning a `str` converts it (`Type_Safe__Step__Set_Attr.py:L22-L24`) and any character outside `[a-zA-Z0-9/\\_.\- ]` is replaced by `_`. So `_key_path`, `list_keys` and `key_exists` operate on the SANITISED path. For a vault directory containing e.g. `+`, `@`, `(`, `~` (unexpanded) or non-ASCII, the key manager reads and writes under a different directory than the rest of the code's `os.path.join(directory, ...)` calls. Nothing in the slice checks that the path survived conversion unchanged: **nothing found**. The same rule applies to `PKI__Key_Store.keys_dir`, `PKI__Keyring.keyring_dir`, `Secrets__Store.store_path`.

---

## `generate_branch_key_pair` (L18-L19)
Delegates to `PKI__Crypto.generate_signing_key_pair` (P-256). Callers: `Vault__Branch_Manager.py:L34,L60`, test adversary L121.

## `generate_key_id` (L21-L22)
`secrets.token_hex(8)` → 16 hex chars; callers prepend `key-rnd-imm-` (`Vault__Branch_Manager.py:L32,L58`). 64 bits of randomness; no collision check against existing files (`test_Vault__Key_Manager.py::test_generate_key_id`).

## `key_exists` (L69-L70)
`os.path.isfile(self._key_path(key_id))`. Gate before `load_public_key` in `Vault__Signatures.py:L33-L35`, `Vault__Sync__Tag.py:L202-L204`, `Vault__Key_Fetch.py:L34`, `Vault__Sync__Push.py:L921`. `isfile` follows symlinks.

## `list_keys` (L72-L76)
Sorted names under `bare/keys` starting with `key-rnd-imm-`; `[]` if the directory is missing. **No production callers** (grep: tests only, `test_Vault__Key_Manager.py::test_list_keys*`).

## `_key_path` (L78-L79)
`os.path.join(self.vault_path, 'bare', 'keys', key_id)`. No validation of `key_id`: a value containing `/` or `..`, or an absolute path, would leave `bare/keys` (`os.path.join` discards the prefix on an absolute second argument). Every production caller supplies either a generated id or a `Safe_Str__Key_Id`/regex-checked id (`Vault__Key_Fetch.py:L33` `KEY_ID__REGEX`, `Vault__Sync__Push.py:L920` from `clone_meta.public_key_id`). Callers also use it directly to read/write the raw file: `Vault__Key_Fetch.py:L47`, `Vault__Sync__Push.py:L928`.
