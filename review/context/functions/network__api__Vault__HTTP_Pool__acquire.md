## `acquire` in sgit_ai/network/api/Vault__HTTP_Pool.py (L84-L98)

**Purpose:** Hand out a connection for `url`: a reusable idle one for the same key, else a new one. Returns `(key, conn, warm)`; `warm` is the only input `_send` has for deciding whether a transport failure is a stale keep-alive (resend) or a real failure (raise).

**Inputs & Assumptions:**
- `url` (str), `fresh` (bool): `fresh=True` skips the idle bucket (the resend path, Vault__API.py:L445 with `retried=True`).
- Implicit: `idle`, `warm`, `lock`.

**Outputs & Effects:**
- Pops candidates from the bucket under the lock (L90-L94), checks liveness **outside** the lock (L95), discards dead ones (L97), opens a new connection when none is reusable (L98). The returned connection is no longer in `idle` (checked out).
- `warm` for a reused connection: `id(conn) in self.warm` (L96) — set by `release`. For a fresh connection: `False` (L98). Note the check at L96 reads `self.warm` without the lock (a set membership read; `release`/`discard` mutate under the lock).

**Block-by-Block:**
```python
# L88-L97
if not fresh:
    while True:
        with self.lock:
            bucket = self.idle.get(key) or []
            if not bucket: break
            conn, released_at = bucket.pop()
        if self.is_reusable(conn, released_at):
            return key, conn, id(conn) in self.warm
        self.discard(key, conn)
```
- **What:** LIFO reuse; dead or too-old connections are dropped until one passes.
- **Assumes:** `is_reusable` catches a peer-closed socket (FIN readable) and the idle-age cap; the remaining race (peer closes after the check) is what the warm/idempotent resend in `_send` covers (docstring L27-L32). Tests: `test_acquire_release_reuses_and_marks_warm`, `test_idle_connection_closed_by_peer_is_not_handed_to_a_write`, `test_idle_age_cap_forces_a_fresh_socket`, `test_fresh_acquire_bypasses_the_idle_bucket`.
- **Establishes:** `warm=True` ⇔ this socket already carried a request.

```python
# L98
return key, self.open(key), False
```
- **What:** new connection; the `id(conn)` of a freshly opened connection may equal that of a discarded one (CPython id reuse). `discard` removes the id from `warm` (L107) before `close()`, so a recycled id does not inherit the warm mark unless the old object is still alive in `warm` — it was discarded first. Observation.

**Cross-Function Dependencies:**
- Callees `key_for`, `is_reusable`, `discard`, `open` (internal).
- Callers: `Vault__API._send` L445.
- Shared state: `idle`, `warm` with `release`, `discard`, `close`.

**Open Questions:** none.
