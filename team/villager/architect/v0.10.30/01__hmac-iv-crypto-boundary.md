# Finding 01 — HMAC-IV change: boundary respected, test coverage absent

**Verdict:** `BOUNDARY OK` for the crypto change itself.
**Verdict:** `SEND-BACK-TO-EXPLORER` not required, but **test debt is a hard finding** — the change shipped with **zero new unit tests**, contradicting debrief 07 ("3 determinism assertions").
**Owners:** Architect (this finding) + AppSec (cryptanalytic risk of HMAC-IV — covered separately).

---

## 1. What changed

Commit `4d53f79`:

- `Vault__Crypto`: two new methods, `encrypt_deterministic(key, plaintext)` and
  `encrypt_metadata_deterministic(key, plaintext)`. Both compute
  `iv = hmac(key, plaintext, sha256).digest()[:12]` and feed it to the existing
  `encrypt(key, plaintext, iv=iv)`.
- `Vault__Sub_Tree`: 7 call-sites flipped from `encrypt_metadata` (random IV) to
  `encrypt_metadata_deterministic`, plus `_store_tree` flipped from `encrypt`
  to `encrypt_deterministic`.

No primitive signature changed — `encrypt(key, plaintext, iv=None)` already
accepted a custom IV. `decrypt()` is unchanged because the IV is always read
from the first 12 bytes of the ciphertext.

## 2. Boundary verdict

The change stayed inside `Vault__Crypto` (new public methods) and
`Vault__Sub_Tree` (call-site swap). I traced every other caller of the
non-deterministic primitives:

| Caller | Method | Domain | Still random IV? | Verdict |
|---|---|---|---|---|
| `Vault__Sub_Tree` (build/build_from_flat) | `encrypt_metadata_deterministic` | tree-entry metadata | NO (deterministic) | correct |
| `Vault__Sub_Tree._store_tree` | `encrypt_deterministic` | tree object | NO | correct |
| `Vault__Commit.create_commit` (msg) | `encrypt_metadata` | commit message | YES | correct — commit IDs must remain unique per parent set anyway |
| `Vault__Commit.create_commit` (body) | `encrypt` | commit body | YES | correct — commit object identity is parent+tree+ts, not metadata |
| `Vault__Ref_Manager` | `encrypt` | ref payload | YES | correct — refs are mutable, IV uniqueness needed |
| `Vault__Key_Manager`, `Vault__Branch_Manager` | `encrypt` | key/branch metadata | YES | correct — these objects are not CAS-deduplicated |
| `Vault__Sync.write_file` blob path | `encrypt` | blob content | YES | correct — blobs MUST stay non-deterministic per debrief |
| `Vault__Change_Pack`, `Vault__Archive`, `Vault__Transfer` | `encrypt` | various payloads | YES | correct |
| `Secrets__Store` | `encrypt` | secret payload | YES | correct |

**No caller assumes the IV is random for security.** No call-site of
`encrypt_metadata` was missed by the conversion in tree-building. No call-site
outside tree-building was wrongly converted.

## 3. Backward compatibility

Confirmed safe. `decrypt()` reads the IV from `data[:12]` regardless of how it
was derived. Old vault objects (random-IV) and new ones (HMAC-IV) live side by
side in the same store; both decrypt with the same code path.

The old tree IDs that already exist on a server (~1019/commit per debrief 07's
example) **stay where they are** — they just stop accumulating. Pull will keep
walking them through their commit pointers. **No data loss, no migration.**

A second-order risk: a long-lived vault now has TWO classes of tree object
co-existing (random-IV tree IDs from before upgrade, deterministic-IV tree IDs
after). Tools that compute "expected vs actual tree ID for this flat map"
(e.g. a future fsck-style check) must accept both. Not a bug today, but worth
flagging so a future Explorer doesn't assume "tree_id == hmac-derived" as an
invariant.

## 4. Test coverage gap (HARD FINDING)

`git show 4d53f79 --stat` reports:

```
sgit_ai/crypto/Vault__Crypto.py | 16 ++++++++++++++++
sgit_ai/sync/Vault__Sub_Tree.py | 24 ++++++++++++------------
2 files changed, 28 insertions(+), 12 deletions(-)
```

**No test file was added or modified in `4d53f79`.** The follow-up commit
`c249f91` adds 2 lines to one existing test (`test_Vault__Sync__Simple_Token`)
just to fix a regression the change introduced.

`grep -rn "encrypt_deterministic\|encrypt_metadata_deterministic" tests/`
returns **zero hits**. The debrief claims:

> HMAC IV: 3 determinism assertions (same-map → same-ID, round-trip,
> different-maps → different-IDs)

These assertions do not exist in the test suite. The crypto invariant the
sprint advertises as the headline result of the work is **not under test**.

Recommended assertions to add (by Dev or QA, not by me):

1. `encrypt_deterministic(k, p) == encrypt_deterministic(k, p)` — pure
   determinism, single-round.
2. `decrypt(k, encrypt_deterministic(k, p)) == p` — round-trip survives the
   custom IV.
3. `Vault__Sub_Tree.build_from_flat(F, k)` returns the same root tree ID for
   two calls with the same `F` and `k` — the headline architectural claim.
4. `Vault__Sub_Tree.build_from_flat(F1, k) != Vault__Sub_Tree.build_from_flat(F2, k)`
   when `F1 != F2` — non-collision.
5. `encrypt_deterministic(k, p) != encrypt_deterministic(k', p)` for `k != k'`
   — IV depends on key, not just plaintext (this is the IND-CPA-preserving
   property; AppSec also wants this asserted).

Item 5 is the one AppSec will want to see.

## 5. Hand-off

- **AppSec:** owns the cryptanalytic question (does HMAC-IV with this key
  domain leak more than the debrief claims). I have no concern with the
  primitive itself — the question is "is the leakage envelope acceptable",
  which is a threat-model decision, not a boundary decision.
- **Dev:** owns the missing-tests work. The 5 assertions above are the minimum.
- **QA:** confirm via the in-memory server that two unchanged commits really
  do produce identical tree IDs (this is the deduplication claim).
