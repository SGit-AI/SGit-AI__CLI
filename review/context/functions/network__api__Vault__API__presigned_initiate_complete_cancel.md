# `presigned_initiate`, `presigned_complete`, `presigned_cancel` — sgit_ai/network/api/Vault__API.py

Three request builders for the S3 multipart upload used by `Vault__Batch._upload_large` (sgit_ai/core/actions/push/Vault__Batch.py:L109-L170). Each is URL + `_auth_headers` with the write key + JSON body + `_request('POST', ...)`; none inspects the response. All three are POST → not resent on a stale socket (`_send` L459), retried on 429/5xx (`_request_bytes` L424-L426).

---

## `presigned_initiate` (L301-L313)

**Purpose:** `POST /api/vault/presigned/initiate/{vault_id}` with `{file_id, file_size_bytes, num_parts}`; the docstring (L305) says it returns `{upload_id, part_urls: [{part_number, upload_url}], part_size}`.
**Inputs:** `file_id` (`bare/data/<oid>`), sizes (ints from `len(ciphertext)`), `write_key`. Trusted.
**Outputs:** host dict, unchecked here. The consumer `_upload_large` trusts `upload_id`, `part_size` (default 10 MB, L124), `part_urls[i].part_number` and `upload_url` (L123-L137); only `upload_url` is checked, by `check_presigned_url` (L139). `part_size` and `part_number` from the host decide which slice of the ciphertext goes to which URL (L136-L137): `nothing found` checking that the parts cover the blob exactly; the server's `presigned_complete` / S3's ETag matching is the only reconciliation.
**Failure contract:** the in-memory double raises `RuntimeError('presigned_not_available')` (Vault__API__In_Memory.py:L128-L131); `_upload_large` L126-L128 treats that substring as "fall back to the batch path". A live server with no presigned support must produce an error containing that text for the fallback to trigger; any other error re-raises (L129).

---

## `presigned_complete` (L315-L326)

**Purpose:** `POST /api/vault/presigned/complete/{vault_id}` with `{file_id, upload_id, parts: [{part_number, etag}]}`.
**Inputs:** `parts` are the ETags S3 returned to our PUTs (`_upload_large` L144, L148). Trusted insofar as they come from the presigned host the server named.
**Outputs:** host dict, unchecked (`_upload_large` L162-L164 returns True on no exception). Whether the server verifies that the assembled object hashes to `file_id` is a host property: `nothing found` on the client. Readers verify on download (Verified_Write), so a bad assembly is refused later, not here.

---

## `presigned_cancel` (L328-L337)

**Purpose:** `POST /api/vault/presigned/cancel/{vault_id}` with `{upload_id, file_id}`; best-effort cleanup (`_upload_large` L165-L169 swallows its errors).

**Cross-Function Dependencies (all three):**
- Callers: `Vault__Batch._upload_large` only (L121, L162, L167).
- Tests: `tests/unit/sync/test_Vault__Batch__Coverage.py::Test_Vault__Batch__UploadLarge` (7 tests on the fallback/cancel flow with stubbed responses); `tests/unit/api/test_Vault__API__Presigned.py` (in-memory raises).

**Open Questions:**
- unclear; no live-server test of the multipart path exists in `tests/integration` (grep `presigned` in tests/integration returns nothing).
