## `classify` in sgit_ai/core/actions/pull/Vault__Ref_Guard.py (L50-L62)

**Purpose:** Decides FORWARD / REWOUND / UNKNOWN for a new remote head against the last head this clone accepted, given the outcome of the fetch walk. Pull refuses REWOUND unless `--accept-rewind` (`Step__Pull__Fetch_Remote_Ref._guard_rewind` L50-L56).

**Inputs & Assumptions:**
- `remote_head` (str): semi-trusted (server's decrypted ref).
- `last_known` (str): trusted — the per-branch baseline from `remote_heads.json` (`Vault__Sync__Base._accepted_head` L227-L237), or `''`.
- `connected` (bool): from `_fetch_commit_chain` — every commit reachable from `remote_head` is now local (not truncated by the limit, not absent on the host).
- `reached_known` (bool): from `_fetch_commit_chain._chain_reached_known` — the walk from `remote_head` met one of the `known` set (`{last_known, clone_commit_id, local named ref}`, `Step__Pull__Fetch_Remote_Ref` L39-L40).
- `boundaries`: forwarded to `is_ancestor`.

**Outputs & Effects:** one of three strings; no effects.

**Block-by-Block:**

```python
# L54-L55
if not last_known or not remote_head or remote_head == last_known:
    return FORWARD
```
- **What:** No baseline (fresh clone, or a branch never accepted) ⇒ FORWARD. Same head ⇒ FORWARD.
- **Assumes:** "no baseline" is a legitimate first contact. Threat model §5 Rewind-guard row: "a fresh clone has nothing to compare with". `_accepted_head` raises rather than returning `''` when the record file is damaged or missing-after-recorded (`_remote_baselines` L170-L186), so `''` here means genuinely never accepted — unless `accept_rewind` was given (`_accepted_head` L234-L237 returns `''` then).
- **Depended on by:** everything below only runs with a real baseline.

```python
# L56-L57
if reached_known:
    return FORWARD
```
- **What:** The new head's history joins what we have ⇒ forward move (or a merge that includes our head).
- **Assumes:** `_fetch_commit_chain` set `_chain_reached_known` correctly: it is set when the head itself, a queued commit, or a *parent* of an expanded commit is in `known` (`Vault__Sync__Status.py:L284, L289-L290, L321-L322`). `known` includes the clone's own head and the *local named ref*, not only `last_known` — so a remote head that descends from the clone's unpushed head (the server took our push) is FORWARD even if it does not descend from `last_known`. **Observation:** `known` is pre-filtered to ids whose objects exist locally (L279); a `last_known` whose object is gone from the store drops out of `known`, so `reached_known` cannot fire for it and the decision falls to `is_ancestor`/`connected`.
- **Depended on by:** L58-L62.

```python
# L58-L62
if self.is_ancestor(c, read_key, remote_head, last_known, boundaries):
    return REWOUND                                       # a rollback: the new head is in our past
if connected:
    return REWOUND                                       # a complete, unrelated lineage: rewritten history
return UNKNOWN
```
- **What:** New head in our past ⇒ rollback. Otherwise, if we fetched the whole lineage and it never met our history ⇒ rewritten. Else undecidable.
- **Assumes:** `is_ancestor` False means "not found locally", not "not an ancestor" (see its record). `connected` True with `reached_known` False means the full graph under `remote_head` is local and contains none of `known` — a disjoint history. UNKNOWN arises offline or past the fetch limit (`commit_fetch_limit`, default 50, `Step__Pull__Fetch_Remote_Ref` L37).
- **Establishes:** REWOUND ⇒ refusal unless accepted; UNKNOWN ⇒ `_guard_rewind` treats it as *not* REWOUND (L50-L51: `if verdict != REWOUND: return`) — **an UNKNOWN verdict proceeds**. The docstring in `_guard_rewind` says "cannot decide: refuse rather than accept blind (review K2)" but that `except` (L44-L49) covers *exceptions*, not the UNKNOWN verdict. Nothing found that refuses on UNKNOWN.
- **Depended on by:** `_guard_rewind` L41-L56.

**Cross-Function Dependencies:**
- Callee `is_ancestor` (internal): see record.
- Callers: `Step__Pull__Fetch_Remote_Ref._guard_rewind` L41-L43 (writable pull), and the same method invoked from `Step__Pull__RO__Load_Named_Head` L97-L98 (read-only pull, TM-R05).
- Shared state: none.
- Invariant coupling: the rewind guard's guarantee (threat model §5) is "refuse a host that moves a branch backwards"; by this code that holds when the backwards move is detectable from local objects or the lineage is fully fetched within the limit. Tests: `tests/security/test_Security__Fixed__Trust_And_Policy.py::test_TM_R05__read_only_clone_refuses_a_rollback`, `tests/security/test_Security__Fixed__Baselines.py::test_B3__a_switch_round_trip_does_not_launder_a_rewind`, `::test_a_damaged_record_refuses_the_rewind`.

**Open Questions:**
- unclear; whether UNKNOWN proceeding to accept is intended (offline tolerance) or an oversight relative to the K2 comment. A host that serves a rewritten lineage longer than `commit_fetch_limit` (50) commits, none of which join ours, yields `connected=False`, `reached_known=False`, `is_ancestor` False ⇒ UNKNOWN ⇒ accepted by `_guard_rewind`. Then `Step__Pull__Fetch_Missing` fetches the rest (limit 10,000 in the policy check; unbounded in `_fetch_missing_objects`) and `Step__Pull__Merge` computes an LCA; with no LCA it does a three-way merge with empty base (L69-L70, L109-L112 of Step__Pull__Merge: `lca_id = None`, `base_map = {}`). Recorded as a path to trace in the hunting phase, not a verdict.
