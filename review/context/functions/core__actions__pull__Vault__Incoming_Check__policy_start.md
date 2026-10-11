## `policy_start` in sgit_ai/core/actions/pull/Vault__Incoming_Check.py (L76-L90)

**Purpose:** The local commit object(s) whose id begins with the `signed-since-<hex>` prefix recorded in the index — where the policy starts. Added to `stop_at` so commits at and before it are not held against anyone.

**Inputs & Assumptions:**
- `c`: trusted; `c.sg_dir` is the `.sg_vault` path.
- `index` (Schema__Branch_Index): the merged local index. Trust: **semi-trusted** — its `features` list is the server copy's after a refresh (`Vault__Index_Sync.merge` L99-L100), i.e. a read-key holder's; the docstring (L78-L82) says why it is deliberately not pinned per clone (TM-R30 remedy; TM-R29 and TM-R01 make pinning protect little).
- Implicit: directory listing of `bare/data/` (L88).

**Outputs & Effects:**
- Returns a set of object ids (possibly several if the 24-hex prefix is ambiguous; possibly empty). No writes. `OSError` on listing → empty (L89-L90).

**Block-by-Block:**

```python
# L84-L86
anchor = Vault__Format().sig_anchor_of(index)
if not anchor:
    return set()
```
- **What:** The hex after `signed-since-`, validated by `sig_anchor_of` (`Vault__Format.py:L72-L78`) as `[0-9a-f]{12,24}`; anything else (e.g. `signed-since-0`) is `''`.
- **Assumes:** `Safe_Str__Feature` lets the string through (`FEATURE__REGEX`, not read). The index writer `Vault__Sync__Format.set_format` (L52-L57) adds the anchor from the server's current head at switch-on time and strips it at switch-off.
- **Establishes:** `anchor` is hex, 12-24 chars — safe as a filename prefix.

```python
# L87-L90
try:
    return {n for n in os.listdir(os.path.join(str(c.sg_dir), 'bare', 'data')) if n.startswith('obj-cas-imm-' + anchor)}
except OSError:
    return set()
```
- **What:** Prefix match over the local object names.
- **Why here:** The feature stores 24 hex (`SIG_SINCE_HEX`, `Vault__Format.py:L19`) while a format-1 id has 12 and a format-2 id 32 — hence a prefix match rather than an exact id.
- **Assumes:** a local object whose name starts with the prefix is *the* anchor commit. With a 12-hex recorded anchor on a format-1 vault that is an exact id; with a 24-hex anchor on a format-2 vault, a collision needs 96 matching bits. If the anchor commit is **not local** (a clone that never had it), the set is empty and the policy applies to everything reachable from the incoming head that is not already held — the walk then proceeds into pre-policy history and a pre-policy unsigned commit refuses. `test_TM_F10__history_from_before_the_policy_is_not_held_against_anyone` (`tests/security/test_Security__Fixed__Trust_And_Policy.py`) covers the case where the clone does hold it (bob pulled before the policy).
- **Establishes:** the stop set for pre-policy history.
- **Depended on by:** `require_signatures` L36.

**Cross-Function Dependencies:**
- Callee `Vault__Format.sig_anchor_of` (internal, L72-L78): first `signed-since-` feature only; strict hex check.
- Callers: `require_signatures` L36. The clone-side twin is `Step__Clone__Verify_Signatures._anchor_commits` (L73-L83), same logic.
- Shared state: reads `bare/data/` names only.
- Invariant coupling: the "policy starts here" record is a feature string in a shared, read-key-encrypted, server-merged document; see TM-R29/TM-R30 for what that does and does not protect.

**Open Questions:**
- unclear; the behaviour when the anchor is recorded but absent locally and the clone's `held_head` is *behind* the anchor (a clone that had not pulled since before the policy and whose history the anchor is not reachable from locally): the incoming walk then includes pre-policy commits. Whether that is reachable in practice depends on `local_history` containing the pre-anchor commits as *held* (they would be, if the clone holds them) — so the realistic gap is only commits between the clone's held head and the anchor that are unsigned. The L2 test (`test_L2__re_enabling_the_policy_does_not_lock_out_a_clone_that_missed_the_off_period`) covers the off/on case.
