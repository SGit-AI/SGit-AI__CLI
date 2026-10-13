# `Vault__Transport_Errors` — sgit_ai/network/api/Vault__Transport_Errors.py (L1-L42)

Three exception classes with message-only `__init__`s; defined in the network layer because the static transport raises them and `core` may not be imported from `network` (docstring L3-L5). `core/Vault__Errors` re-exports them.

## `Vault__Read_Only_Transport_Error.__init__` (L20-L21)
Default message `MSG_READ_ONLY_TRANSPORT` (L8-L13). Raised by `Vault__API__Static._read_only` (Vault__API__Static.py:L244-L245), to which `write`, `delete`, `batch`, `delete_vault` are aliased (L247-L250). **Establishes:** a write on a static transport raises rather than no-ops (docstring L17-L18). Test: `test_Vault__API__Static.py::test_writes_raise_read_only_transport_error`.

## `Vault__Static_Transport_Error.__init__` (L30-L31)
A dead static host (refused/reset/timeout/DNS), distinct from an absent object (docstring L25-L28, "tabletop 11, F5"). Raised by `Vault__API__Static._fetch` L134-L138 and `presigned_read_url` L199-L200; propagated unchanged by `_read_manifest` L231-L232. Tests: `test_dead_host_raises_naming_host_not_empty_vault`, `test_resetting_host_raises_transport_error`, `test_dead_host_aborts_batch_read_loudly`.

## `Vault__Static_Object_Error.__init__` (L41-L42)
A non-404 status for one object (e.g. 403) — fails soft in `batch_read` (recorded, skipped) rather than aborting (docstring L35-L39). Raised by `_fetch` L132-L133; caught in `read` L102-L104 (try the other layout) and `batch_read` L153-L154, L164-L165. Test: `test_non_404_status_is_typed_and_fails_soft_in_batch`.

No inputs beyond the message; no state. No open questions.
