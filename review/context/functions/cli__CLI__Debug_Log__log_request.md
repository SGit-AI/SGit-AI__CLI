## `log_request` in sgit_ai/cli/CLI__Debug_Log.py (L11-L21)

```python
# L12-L21
entry = {'method': method, 'url': url, 'data_size': data_size, 'start': time.monotonic(),
         'status': 0, 'resp_size': 0, 'duration': 0.0, 'error': ''}
self.entries.append(entry)
return entry
```

**Purpose:** Starts a per-request record for `--debug` network tracing. Called from `Vault__API._request` (`sgit_ai/network/api/Vault__API.py:L415`) and the presigned-URL paths (`Vault__API.py:L254`, `Vault__Sync__Clone.py:L336,L422`, `Vault__Batch.py:L142`) — only when `self.debug_log` is set, which `CLI__Main._setup_debug` does when `--debug` or `.sg_vault/local/debug` says `on` (`CLI__Main.py:L1069-L1078`).

**Inputs & Assumptions:**
- `method`, `url` (str): the FULL request URL. Trust: built by the code; for presigned S3 URLs the URL is one the HOST returned (`Vault__API.py:L251`) and carries the signature parameters in its query string.
- `data_size` (int).
- Implicit: `self.entries : list` — Type_Safe gives each instance its own empty list (`Type_Safe__Step__Default_Value.default_value` falls through to `default_value(list)` → `[]`), so CLAUDE.md rule 4 (no mutable default value) is honoured by annotation-only.

**Outputs & Effects:**
- Appends to `self.entries` REGARDLESS of `self.enabled` (the `enabled` check is only in `_print_entry` L34-L36, `print_header` L77, `print_summary` L87). In practice the object exists only when debugging is on (`CLI__Main.py:L1072-L1075`).
- Returns the mutable dict the caller later passes to `log_response`/`log_error`.
- What is retained in memory: method, full URL, sizes, timing. NOT retained: headers (so neither `x-sgraph-access-token` nor `x-sgraph-vault-write-key`, `Vault__API.py:L84-L95`), request bodies, response bodies.

**Cross-Function Dependencies:** `time.monotonic` (stdlib). Callers above. Tests: `tests/unit/cli/test_CLI__Debug_Log.py::test_log_request_creates_entry`.

**Open Questions:** none.
