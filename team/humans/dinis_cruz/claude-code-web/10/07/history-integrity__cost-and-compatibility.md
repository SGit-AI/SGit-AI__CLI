# History integrity: what the three fixes would cost, and how to ship them without a `vault move`

**Date:** 7 Oct 2026 · **Vault measured:** the DC / CRM collaboration vault (`y8pwtjlw`), fresh
full clone this session · **Ask:** "do a set of performance tests to see the implications [of
signature verification, ref monotonicity, 128-bit ids], and can we add those fixes in a
forward-compatible way, supporting existing vaults without a move?"

## 0. The vault today

| | |
|---|---|
| commits reachable from the named head | 674 (626 yesterday) |
| unique trees / tree entries | 8,589 / 107,445 (59,944 blob refs, 47,501 tree refs) |
| objects in the store | 19,780 · 146 MB |
| branches in the index / public keys on disk | 30 / 29 |
| full clone from this sandbox (0.18.0) | 93 s |
| `sgit status`, up to date | 2.5 s (network-bound) |

## 1. Cost of each fix, measured

All local work, this sandbox's CPU. Network is unchanged by any of the three.

| Fix | What it adds per command | Measured | Verdict |
|---|---|---|---|
| **Signature verification** on pull / status / fsck | one ECDSA P-256 verify per *new* commit (pull) or per commit (fsck) | verify 66 µs, sign 23 µs; the whole 674-commit history verifies in **39 ms**; decrypting and parsing the whole history is 155 ms (230 µs/commit) | free |
| **Ref monotonicity** (the new remote head must descend from the last known one) | an ancestry walk from the new head to the last known head, i.e. over the N new commits | status already does this walk since 0.18.0 (0 object reads when up to date, N when N behind); worst case the whole history: **155 ms** | free |
| **128-bit object ids** (32 hex instead of 12) | nothing in compute (sha256 is already computed; the truncation is what goes away); more bytes in trees, commits and listings | +2.18 MB on 34.5 MB of tree+commit objects (**+6.3 %** of those, **+1.5 %** of the 146 MB store); the store listing grows 396 KB; expected clone cost ≈ +1.5 % of bytes, under 2 s | negligible |

And the exposure the third fix removes, on this vault: accidental collision among 19,780 ids at
48 bits ≈ 7×10⁻⁷ (not the problem); a *second-preimage* by someone holding the read key is 2⁴⁸
sha256 ≈ 8 hours at 10¹⁰ hashes/s on a GPU (the problem).

### What signature verification would actually cover today

| commits | |
|---|---|
| signed | 562 of 674 |
| signed and verifiable (the branch index still maps the branch to its public key) | **247** (all verify; 0 bad) |
| signed, but the index no longer lists the branch | 315 |
| unsigned | 112: 10 with no `branch_id` (web UI), 102 from CLI clone branches that had no local signing key |

Two consequences for the design: the commit's reserved `author_key_id` field has to be
populated from now on (the key is in `bare/keys/`, but the only branch→key mapping is the
index, and clone branches leave it), and a "signatures required" policy can only apply from a
checkpoint commit forward, since 427 of the 674 commits here cannot be verified whatever we do.

### A side finding: `sgit check fsck` was quadratic

Full verification is the thing that makes "always detect corruption" practical, and it took
**270 s** on this vault: the walk kept a per-commit set of visited trees, so 8,589 unique trees
were checked 282,202 times and every blob was re-hashed once per commit. One global set for
trees and one for blobs: **12.2 s**, identical findings (42 missing objects; they are the
pre-0.18.0 push bug and are recoverable only from the clones that created them, via
`sgit check upload-objects`). Fixed on the branch; 32 fsck tests pass, full suite green.

## 2. Compatibility: what exists, what does not

**Today there is no vault-level "minimum client version".**

- Objects carry a `schema` tag (`commit_v1`, `tree_v1`, `branch_index_v1`). Nothing reads it
  except `vault move`.
- The migration ledger (`sgit migrate`) is **local** (`.sg_vault/local/migrations.json`); the
  vault itself does not say which migrations it has had.
- Old clients drop unknown fields silently (`Schema__Branch_Index.from_json` with a `format`
  or `min_client` key just loses them), so a flag written today is invisible to 0.18.0 and
  older. They fail only when they meet data they cannot parse: a 32-hex id raises
  `ValueError … exceeds maximum length of 24` and the CLI prints `incompatible vault data …
  hint: re-clone the vault with the current CLI`, which is the wrong remedy for that case.

So: forward-incompatible vaults are *possible* today only by accident, and the failure mode
for an old client is a confusing error, not a "please upgrade".

## 3. Proposal: a format gate, then each fix on top of it

### 3.1 The gate (no format change; ships first)

Add to `Schema__Branch_Index` (encrypted, written by init/push, loaded first by every command):

```
format     : Safe_UInt           = 1        # absent == 1: every existing vault
min_client : Safe_Str__Semver    = None     # refuse below this, naming it
features   : list[Safe_Str__Feature]        # e.g. 'ids-128', 'signatures-required'
```

- A client at or above the release that ships the gate refuses a vault whose `min_client` is
  newer than itself: `this vault needs sgit-ai ≥ 0.20.0 (you have 0.19.1): sgit update`.
- Existing vaults carry no field, read as format 1, and behave exactly as now. **No move.**
- Clients older than the gate cannot be taught anything retroactively; the one thing we can do
  for them now is fix the hint on the pattern error to say `sgit update` first.
- Raising `min_client` on a vault is a deliberate owner action (`sgit vault format --min-client
  0.20.0`), recorded in the index, so a team is never surprised by a vault that stops working
  for their older agents.

### 3.2 Each fix against the gate

| Fix | Format change? | Needs `vault move`? | Old clients on an upgraded vault | Notes |
|---|---|---|---|---|
| Verify signatures (pull, status, fsck) and populate `author_key_id` | none; both fields already exist in `commit_v1` (`author_key_id` reserved) | no | unaffected: they ignore signatures as they do now | policy per vault in `features`: `signatures: warn` → `required` from a checkpoint commit; the web UI must sign before `required` |
| Ref monotonicity | none | no | unaffected | client rule; `push --force` records the intent so the next pull can tell a rewind from an attack; a signed ref log is a later, format-2 addition |
| 128-bit ids | **format 2**: new objects get 32-hex ids, old objects keep theirs, references mix | **no**: mixed-id vault; `vault move` (which already rewrites every id) is the optional "rewrite everything" path | **break at the first long id** → this is what `min_client` is for | prerequisites outside the CLI: the server must accept the longer `file_id` (unverified from here), the web UI must read and write both lengths (interop requirement) |

### 3.3 Order

1. **0.19**: the gate, the hint fix, `author_key_id` on every new commit, fsck dedupe. No
   vault changes behaviour; every client keeps working on every vault.
2. **0.20**: signature verification (`warn` default, `required` opt-in per vault), ref
   monotonicity. Still format 1.
3. **format 2**: 128-bit ids for new vaults and opted-in vaults, once the server and web UI
   accept both lengths. Existing vaults stay format 1 until their owner raises them; raising
   never requires a move.

The measurements say none of this is a performance decision: the costs are milliseconds and a
few percent of bytes on a vault that was impractical to clone a week ago and now clones in 93 s.
