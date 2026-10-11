## `_api_error` in sgit_ai/network/api/Vault__API.py (L470-L510)

**Purpose:** Builds the `RuntimeError` every HTTP failure becomes: `API Error: HTTP <code> <reason>`, the request line, headers with token/key values masked, payload size, the server's response body, and hints for redirects and the API-key gate. Several callers **parse this text** to classify failures, so its shape is a contract.

**Inputs & Assumptions:**
- `error` (HTTPError): from `_send`. `error.read()` yields the body (L472-L475; failures ignored).
- `headers` (dict): the request headers.

**Outputs & Effects:**
- Returns (does not raise) a `RuntimeError`.
- Masking rule L478-L482: any header name containing `token` or `key` (case-insensitive) is replaced by `***...(N chars)`. Covers `x-sgraph-access-token`, `X-API-Key`, `x-sgraph-vault-write-key`. Tests: `test_Vault__API.py::test_api_error_masks_access_token`, `test_api_error_masks_write_key`, `test_api_error_non_sensitive_header_not_masked`; `test_Vault__HTTP_Pool.py::test_http_error_shape_and_body_preserved` (`'tok-123' not in msg`).
- The URL (vault id, file id) and the host's response body are included verbatim (L485, L490). The body is host-controlled text that reaches the terminal and the strings other code matches on (`Vault__API__Auto._resolve_from_error` L191-L194 matches `BATCH_PATH` and `HTTP 404/405/501` anywhere in the message; `_batch_read_chunk_with_fallback` L173, L183; `Vault__Index_Sync.upload` L190; `_classify_exception` L282-L283; `Vault__Index_Sync._is_no_write_access` L145-L147). A body containing those tokens can steer those branches: `nothing found` separating the status line from the body in the matchers.
- L496-L504: for 3xx adds the `Location` header to the message and says redirects are not followed (test `test_redirect_error_carries_a_hint`).
- L505-L507: 401 with `Client API key is missing` → token hint.

**Cross-Function Dependencies:**
- Callers: `_request_bytes` L427, L428.
- Consumers of the text: listed above.

**Open Questions:** none.
