# `Vault__API__Static` trivial methods — sgit_ai/network/api/Vault__API__Static.py

Fields (L46-L48): `layout : Enum__Published_Layout` (sticky after the first successful read), `record_requests : bool`, `recorded_requests : list`. Inherits `base_url`, `tls_verify`, `debug_log` from `Vault__API`; `access_token` is `None` when built by `Vault__API__Auto._static` (Vault__API__Auto.py:L39) and is never read here (no `_auth_headers` call in this file).

## `setup` (L50-L54)
Raises `ValueError` when `base_url` is empty (L51-L53): a static transport never silently falls back to the default server. Test: `test_setup_requires_base_url`.

## `is_local` (L58-L60)
`base_url` does not start with `http://`/`https://` → local folder (so `file://...` and plain paths are both local; `_root` strips `file://`, L63).

## `_root` (L62-L63)
`base_url` minus `file://`, right-stripped of `/`.

## `_candidate_layouts` (L65-L68)
`[layout]` once sticky, else `[API_PATH, FLAT]` (templates L41-L42: `api/vault/read/{vid}/{fid}` and `{fid}`).

## `_record` (L86-L88)
Appends the location to `recorded_requests` when recording — the I2 evidence mechanism (`test_requests_never_contain_key_material`).

## `_record_absent` (L180-L184)
With a `failures` dict, records `Schema__Fetch_Failure(ABSENT, 'absent on static host (404)')` via `Vault__API._classify_per_file_status(fid, 'not_found', ...)` (Vault__API.py:L207-L236). Note it is also used for the "layout never resolved" case (L175-L177) and for a per-object non-404 status that was swallowed in `batch_read` (L164-L165 → L172-L173), so a 403'd object is recorded as ABSENT there, not FORBIDDEN.

## `_read_only` (L244-L245) and the aliases `write`, `delete`, `batch`, `delete_vault` (L247-L250)
Raise `Vault__Read_Only_Transport_Error` unconditionally — writes are refused structurally (comment L242). Test: `test_writes_raise_read_only_transport_error`. Not aliased: `presigned_initiate/complete/cancel` (inherited from `Vault__API`; they would POST to `base_url` with no token — `Vault__Batch._upload_large` is only reached from push, which fails earlier on `batch`/`write`).

No open questions for these.
