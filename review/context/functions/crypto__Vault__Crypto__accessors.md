# `Vault__Crypto` one-line helpers in sgit_ai/crypto/Vault__Crypto.py

Each is a single expression with no branches; grouped here per the slice rules. All are pure.

---

## `derive_read_key` (L138-L140)
`salt = f'{SALT_PREFIX}:{vault_id}'.encode()` → `derive_key_from_passphrase(passphrase.encode(), salt)`. Salt prefix `sg-vault-v1` (L19). Caller: `derive_keys` L206. Vectors: `test_Vault__Crypto.py::test_vector_1__read_key`, `::test_vector_2__read_key`. Assumes `vault_id` already validated (`parse_vault_key`); nothing here re-checks.

## `derive_write_key` (L142-L144)
Same with `WRITE_SALT_PREFIX = 'sg-vault-v1:write'` (L34). Caller: `derive_keys` L207. The write key has no cryptographic role in the client (threat model §1); it is sent as `x-sgraph-vault-write-key` (`Vault__API.py:L95`). Vector: `::test_vector_1__write_key`.

## `derive_file_id` (L146-L148)
`HMAC-SHA256(read_key, domain_string)[:12]` hex. Keyed by the READ key only (docstring at L163-L168 of the cache variants: "never write_key"), so every read-key holder can compute every mutable file's id. Callers: L152, L156, L160, L171, L181, `Step__Clone__Download_Index.py:L145` (`branch:current:<vault_id>` — a domain string not listed among the constants at L35-L39).

## `derive_ref_file_id` (L150-L152)
Domain `sg-vault-v1:file-id:ref:<vault_id>`. Callers: `derive_keys` L208, `import_read_key` L226, `Vault__Cache_Reader.py:L65`, `Step__Clone__Download_Index.py:L123`.

## `derive_branch_index_file_id` (L154-L156)
Domain `sg-vault-v1:file-id:branch-index:<vault_id>`. Callers: L209, L227.

## `derive_branch_ref_file_id` (L158-L160)
Domain `...:branch-ref:<vault_id>:<branch_name>`. `branch_name` is user-chosen and unescaped in the domain string; `:` inside a branch name would make `a:b`/`a` + `b:…` ambiguous only if two different (vault_id, name) pairs concatenated equal — `vault_id` is `[a-z0-9]{4,24}` so cannot contain `:`, leaving the split unambiguous. Caller: `Vault__Sync.py:L76` (`'local'`). Vector `::test_vector_2__branch_ref_file_id`.

## `derive_cache_value_file_id` / `derive_cache_pointer_file_id` (L162-L171, L173-L181)
Domain `...:cache-value:<vault_id>:<path>` / `...:cache-pointer:<vault_id>:<path>`; `path` is the RAW vault-relative path (docstring L165-L167). Caller: `Vault__Cache_Manager.py:L59,L61`. Tests: `tests/unit/crypto/test_Vault__Crypto__Cache_Ids.py`.

## `content_hash` (L307-L308)
`sha256(plaintext)[:12]`. Plaintext hash stored (encrypted) in tree entries (`Vault__Sub_Tree.py:L223`) and used for change detection (`Vault__Sync__Scope.py:L97`, `Vault__Sync__Base.py:L453`). 48-bit truncation; equal first-12 ⇒ "unchanged".

## `hash_data` (L310-L311)
Full sha256 hex. Used by publish/mirror manifests (`Vault__Publish.py:L99,L169,L227`, `Vault__Mirror.py:L159-L187`) and `Vault__Inspector.py:L57`.

## `generate_salt` (L313-L314), `generate_iv` (L316-L317)
`os.urandom(16)` / `os.urandom(12)`. **No production callers** (grep: tests only, `test_Vault__Crypto.py::test_generate_salt__*`, `::test_generate_iv__*`). `encrypt` generates its own IV at L296.
