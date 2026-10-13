## `is_reusable` in sgit_ai/network/api/Vault__HTTP_Pool.py (L126-L129)

**Purpose:** Idle-connection gate: not older than `max_idle_seconds` (default 30 s, L54) and not dropped by the peer.

**Inputs & Assumptions:** `conn`, `released_at` (monotonic). `max_idle_seconds == 0` disables the age cap (L127).

**Outputs & Effects:** bool; no state.

**Block-by-Block:** L127-L128 age cap (docstring L18-L22: a NAT that forgot the mapping sends no FIN, so age is the only signal; a push that encrypts for a minute between its ref read and its batch write gets a fresh socket). L129 `not self.is_dropped(conn)`.

**Depended on by:** `acquire` L95. Test: `test_idle_age_cap_forces_a_fresh_socket`.

**Open Questions:** none.
