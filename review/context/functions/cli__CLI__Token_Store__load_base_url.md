## `load_base_url` in sgit_ai/cli/CLI__Token_Store.py (L167-L180)

Mirror of `load_token` for `.sg_vault/local/base_url` with legacy `.sg_vault/base_url` fallback; returns stripped text or `''`. Follows symlinks on read. A planted or edited file redirects every later network command of that clone (token and write key go with it) — the file is inside `.sg_vault`, which the path guard keeps vault CONTENT from writing (TM-F03), leaving A6. Callers: `resolve_base_url` L30, `CLI__Vault.py:L89`, `CLI__Main.py:L929`. Tests: `test_CLI__Token_Store.py::test_load_base_url_*`.
