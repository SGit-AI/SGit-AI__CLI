## `message` in sgit_ai/core/actions/pull/Vault__Ref_Guard.py (L64-L68)

**Purpose:** The user-facing text for a refused rewind, naming `last_known` and `remote_head` and the two remedies (`sgit pull --accept-rewind`, or treat as tampering).

**Inputs & Assumptions:** two commit ids (strings) interpolated into an f-string; no key material.

**Outputs & Effects:** returns str. Raised as `Vault__Ref_Rewind_Error` by `_guard_rewind` L56 and printed by `CLI__Main._print_friendly_error` L1035 as `error: {message}`.

**Cross-Function Dependencies:** caller `_guard_rewind` L56.

**Open Questions:** none.
