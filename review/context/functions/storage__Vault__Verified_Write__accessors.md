# Small methods in sgit_ai/storage/Vault__Verified_Write.py

## `is_content_addressed` (L25-L27)
`file_id.rsplit('/', 1)[-1].startswith('obj-cas-imm-')`. Pure. Callers: `classify` L60. A `None` `file_id` raises `AttributeError` — only reached via `classify`, whose callers pass str (`save` already stringified through `is_store_path`? No: `is_store_path` stringifies its *own* copy at L34; `classify` receives the original `file_id`. `verify` has no caller in `sgit_ai/`, so in practice `file_id` is always a str from `save`'s callers).

## `verify` (L68-L70)
`classify(...) != REFUSED`. No callers in `sgit_ai/` (grep); exists for tests/external use.

## Class constants `VERIFIED`/`REFUSED` (L40-L41), `STORE_FILE_ID` (L18-L19), field `crypto : Vault__Crypto = None` (L23).
