## `_format_path` in sgit_ai/cli/CLI__Debug_Log.py (L52-L66)

```python
# L53-L66
path = url
for prefix in ['https://', 'http://']:
    if path.startswith(prefix):
        path = path[len(prefix):]
        slash = path.find('/')
        if slash >= 0: path = path[slash:]
        break
if path.startswith('/api/'): path = path[5:]
path = unquote(path)
if len(path) > 70: path = path[:67] + '...'
return path
```

**Purpose:** Shorten a URL for display: drop scheme and host, drop `/api/`, percent-decode, truncate.

**Inputs & Assumptions:** `url` (str). Trust: code-built or host-returned (presigned). A URL with no `/` after the host keeps `host` as `path` (slash < 0 leaves `path` = host).

**Outputs & Effects:** display string; pure. KEEPS the query string (`?prefix=...` from `Vault__API.py:L354`; AWS auth parameters on presigned URLs), subject to the 70-char cut. `unquote` turns `%2F`-encoded file ids back into slashes (`quote(file_id, safe="")` at `Vault__API.py:L93`). Tests: `test_CLI__Debug_Log.py::test_format_path_strips_base_url`, `::test_format_path_decodes_url_encoding`, `::test_format_path_truncates_long_paths`.

**Cross-Function Dependencies:** `urllib.parse.unquote`. Caller: `_print_entry` L41.

**Open Questions:** none.
