## `resolve_base_url` in sgit_ai/cli/CLI__Token_Store.py (L23-L30)

```python
# L24-L30
if base_url:
    if directory:
        self.save_base_url(base_url, directory)
    return base_url
if not directory:
    return ''
return self.load_base_url(directory)
```

**Purpose:** Same shape as `resolve_token` for the server URL: an explicit `--base-url` is recorded in `.sg_vault/local/base_url` and used; otherwise the recorded one is loaded. The legacy fallback in `resolve_remote` (L101).

**Inputs & Assumptions:** `base_url` (str or None): argv; `http://` is accepted (TM-R10, `Known_Gaps::test_TM_R10__plain_http_base_url_is_accepted`). `directory`: as above.

**Outputs & Effects:** returns the URL or `''`; side effect `save_base_url` (open+chmod, see that record). Recording the URL is what pins later commands to the server the user chose (TM-F15/F22 context; `tests/security/test_Security__Fixed__Server_Pin.py::test_base_url_flag_still_chooses`).

**Cross-Function Dependencies:** `save_base_url` (L151-L165), `load_base_url` (L167-L180). Callers: `resolve_remote` L70, L101; many CLI commands.

**Open Questions:** none.
