## `_server_rewound` in sgit_ai/core/actions/push/Vault__Sync__Push.py (L887-L899)

**Purpose:** On the "nothing to push" path, when the server's head differs from the local named head: decide whether the server moved **forward** (a teammate pushed → `behind`) or **backward/sideways** (→ `rewound`, which the CLI reports as tampering-or-force and exits 1, CLI__Vault.py:L1223-L1228). "Nothing to push" used to hide a rewind (d3b8eef).

**Inputs & Assumptions:** `c` (components), `read_key`, `last_seen` (local named head), `server_head` (decrypted from the server's ref by `_server_named_commit_id`).

**Outputs & Effects:**
- Network: `Vault__Sync__Status._fetch_commit_chain` downloads up to 50 missing commit objects from `server_head` down to `last_seen` (Vault__Sync__Status.py:L255-L326) — **verify-before-write** (`writer.save(...) == VERIFIED`, L304), commit objects only.
- Returns False when `last_seen` is an ancestor of `server_head` (behind), else whether `server_head` is an ancestor of `last_seen` (rewound). **Any exception → False** (L898-L899), and a divergent head (neither is an ancestor of the other, e.g. a force-pushed rewrite) also returns False → reported as `behind`, not `rewound`.
- No local ref or baseline change.

**Block-by-Block:**
```python
# L891-L897
Vault__Sync__Status(...)._fetch_commit_chain(c, c.obj_store, read_key, server_head, limit=50, known={last_seen})
guard = Vault__Ref_Guard(crypto=self.crypto)
if guard.is_ancestor(c, read_key, last_seen, server_head, set()): return False
return guard.is_ancestor(c, read_key, server_head, last_seen, set())
```
- **Assumes:** `is_ancestor` walks **local** commits only (`Vault__Ref_Guard.is_ancestor` L23-L48: `obj_store.exists` gate, `LOCAL_WALK_LIMIT`); with the fetch capped at 50, a server head more than 50 commits ahead makes both tests False → `behind` (correct direction). A rewrite (different history) → `behind` (incorrect label, but nothing is written either way).
- Tests: `tests/unit/review/test_Review__d3b8eef__Lower_Priority.py::test_push_on_a_rewound_branch_says_so` (adversary moves the ref back), `test_push_when_a_teammate_pushed_says_behind`.

**Cross-Function Dependencies:** callees `Vault__Sync__Status._fetch_commit_chain` (verified downloads), `Vault__Ref_Guard.is_ancestor`. Caller: `push` L120.

**Open Questions:**
- unclear; whether a divergent (rewritten) server head reported as `behind` is intended — pull's `Vault__Ref_Guard.classify` (L50+) is the authoritative classifier and was not read here.
