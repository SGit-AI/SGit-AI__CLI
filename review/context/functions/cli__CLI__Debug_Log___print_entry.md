## `_print_entry` in sgit_ai/cli/CLI__Debug_Log.py (L35-L50)

```python
# L36-L50
if not self.enabled: return
duration_ms = entry['duration'] * 1000; status = entry['status']; method = entry['method']
path  = self._format_path(entry['url'])
sent  = self._format_size(entry['data_size']); recv = self._format_size(entry['resp_size'])
error = entry.get('error', '')
status_str = f'{status}' if status else '???'
line = f'    [{method:<6}] {status_str:>3}  {duration_ms:>6.0f}ms  {sent:>6}  {recv:>6}  {path}'
if error: line += f'  ERR: {error[:60]}'
print(line, file=sys.stderr, flush=True)
```

**Purpose:** One stderr line per completed request.

**Inputs & Assumptions:** `entry` dict from `log_request`; `self.enabled`.

**Outputs & Effects:** writes to stderr. What reaches the terminal / any log that captures stderr: method, status, timing, sizes, and the request PATH + QUERY (`_format_path`, truncated to 70 chars), and up to 60 chars of the HTTP reason phrase on error. Vault ids and file ids appear in the path (`/vault/read/<vault_id>/<file_id>`, `Vault__API.py:L99`), which is metadata the host already sees (threat model A1 "ids"). Headers never reach here. For a presigned S3 URL the printed 67 chars begin with the S3 path and the start of the query string; whether the `X-Amz-Signature` value itself fits inside 67 characters depends on the URL — **nothing found** that strips the query string before printing.

**Cross-Function Dependencies:** `_format_path` (L52-L66), `_format_size` (L68-L75). Callers: `log_response` L27, `log_error` L33. Tests: `test_CLI__Debug_Log.py::test_print_entry_format`, `::test_print_entry_with_error_appends_err_line_49`.

**Open Questions:**
- unclear; need the exact presigned URL shape the server returns (`Vault__API.presigned_read_url`, L344) to say whether a signature value is ever within the first 67 characters of path+query.
