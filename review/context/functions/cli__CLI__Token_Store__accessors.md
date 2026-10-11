# `CLI__Token_Store` helper in sgit_ai/cli/CLI__Token_Store.py

Class has no fields (L12). Constants L6-L9: `token`, `base_url`, `.sg_vault/local`.

---

## `_local_dir` (L121-L122)
`os.path.join(directory, '.sg_vault', 'local')`. Same value as `Vault__Storage.local_dir` (L30-L31) but computed independently. Callers: `save_token`, `load_token`, `save_base_url`, `load_base_url`.
