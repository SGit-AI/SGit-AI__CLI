## `is_dropped` in sgit_ai/network/api/Vault__HTTP_Pool.py (L131-L145)

**Purpose:** True when an idle socket is readable (a FIN, or bytes the client did not ask for) or has pending decrypted TLS bytes — either way not a socket to send a request on (same test urllib3 uses, L134).

**Inputs & Assumptions:** `conn` with `.sock` (None before the first connect → reusable, L136-L137).

**Block-by-Block:**
- L139-L141: `sock.pending()` > 0 → dropped (TLS).
- L142-L143: `select([sock], [], [], 0)` readable → dropped.
- L144-L145: any `OSError`/`ValueError` (closed fd) → dropped.
- **Establishes:** a connection handed out passed a zero-timeout readability probe. It cannot detect a peer that will close *after* the probe; that window is `_send`'s warm resend.

**Depended on by:** `is_reusable` L129 → `acquire`. Tests: `test_idle_connection_closed_by_peer_is_not_handed_to_a_write` (uses `('ok', 200, ..., {'Connection': 'close'})`-style scripts), and the `_Blind_Pool` subclasses in `test_stale_keep_alive_*` override it to model the race.

**Open Questions:** none.
