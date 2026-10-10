# Security review before 0.21.0 — fixes, threat model, adversarial test suite

**Date:** 2026-10-08 · **Branch:** `claude/charming-babbage-5hzcxq` → `dev` (PR SGit-AI/SGit-AI__CLI#10)

The full threat model and risk register:
`team/explorer/appsec/threat-model/v0.21.0__threat-model.md`.

## What was done

1. **A full review** of the code base (four parallel reviews: host as attacker, hostile
   vault author, local machine, crypto/trust model), each finding checked against the
   code and, where it mattered, reproduced.
2. **Fixed everything cheap with low side effects** (8 groups, TM-F01..F08 in the doc).
   The most important:
   - **Clone with a withheld or substituted HEAD blob** used to warn and carry on. The
     missing file then read as *deleted*, and the newcomer's next commit deleted it from the
     vault for everyone. Clone now refuses, as pull already did. Found while writing the
     gap tests.
   - **Concurrent push lost update**: a push that lost the race reported success
     (the live server returns a CAS miss as HTTP 200 with a per-op `conflict`).
   - **Unverified writes** in `fsck --repair`, `vault move` auto-repair (it laundered a
     substitution into the new vault), sparse fetch/cat and the cache pointer.
   - **Unguarded write loops**: revert, branch switch, stash pop, sparse fetch and restore
     could write `.git/hooks/*` or outside the tree from vault data.
   - **Symlinks**: a link to `~/.ssh/id_rsa` in the tree was committed with the key's content.
   - **Key files world-readable** (bare checkout key, backup zip with plaintext key, secrets
     store), `sgit update` importing a `pip.py` from the cwd, and presigned URLs followed on
     any scheme.
3. **Tests that prove it**, without slowing the unit suite (still 4050 tests, ~45 s):
   - `tests/security/` (41 tests, ~1.3 s, hermetic). `test_Security__Fixed__*` replays each
     fixed attack: against the pre-fix code 27 of its 29 tests fail (the other 2 are controls
     that legitimate use still works). `test_Security__Known_Gaps.py` **performs each
     accepted attack and asserts it still works**, tagged with its risk-register id.
   - `tests/integration/test_Security__Server_Boundary__Integration.py` (real server):
     a reader without the write key gets HTTP 403 on every way of moving a ref, deleting
     or adding objects (with a positive control: the same batch succeeds with the owner's key).
   - `tests/_helpers/vault_adversary.py`: the attacker as a fixture (read key only, writes
     straight into the host's store).

## Is a separate CI pipeline for security tests worth it?

Yes, and it is added: **"Run Security & Adversarial Tests"**, a job after the unit tests,
in parallel with integration / QA / mutation, so it adds no wall time. Release
(`increment-tag`) now needs it too. A separate job is worth it for three reasons:
- the known-gap tests behave differently from unit tests: a failure there is news (a gap
  closed or moved), and it shows under its own name;
- it is the place to add adversarial tests without arguing about unit-suite time;
- static analysis (Bandit) and a dependency audit (pip-audit) belong next to it. Those
  are **not** added yet: both would likely go red on day one (KI-SEC-06: ~23 Bandit
  mediums), so they need a baseline first. Recommended as a follow-up.

The real-server security test runs in the existing integration job (it needs the
3.12 server environment and adds about 2 s).

## The list to look at: what we accept today, and what we may want to fix sooner

**By design (architecture):**
- **TM-R01: anyone with the READ key who can write to the store can forge history that
  verifies.** The write key is only a bearer header the host checks, and a signing key is
  trusted because its file decrypts under the read key. A test proves it, including that
  `signatures-required` stops an unsigned forgery but not a self-signed one. Today the
  only thing in the way is an honest host (proven on the real server). Every read-only
  share is a read-key holder.
- TM-R08 metadata to the host (exact file sizes, change patterns, team size).
- TM-R12 no read revocation; TM-R13 the write key can delete everything; TM-R26 other
  clients ignore client-side policy.

**Accepted short-term:** ref/key files not bound to their ids (TM-R03), read-only clones
follow a rollback (R05), tag timestamps chosen by the writer and unverified tag resolve (R06),
48-bit ids on format 1 (R07), tracked `.env` stays tracked (R09), `http://` allowed (R10),
one global salt in the credential store (R11), keys in argv / `vault info` (R14), read key on
disk for read-only clones (R15), passphrase strength (R16), signer not bound to branch (R17),
tree-shape DoS (R18), static-hosting SP-2/3/5/14 (R19), classical PKI (R20), supply chain and
no Bandit/pip-audit gate (R21).

**My recommendation for "sooner rather than later", in order:**
1. **TM-R04: clone should enforce `signatures-required`** (small): run pull's verify over
   the cloned history. Today a newcomer clones an unsigned head silently.
2. **TM-R02: stop storing the named branch's private key under the read key** (medium):
   every read-only share can sign as the named branch.
3. **TM-R05 + TM-R25** (small): rewind guard for read-only clones; fail closed when the
   index can't be read during signature enforcement.
4. **TM-R06** (small): clamp tag timestamps on merge, verify signature on `resolve`.
5. **TM-R01** (large, the one that matters most): owner-signed membership. The owner signs
   the set of trusted signer keys, clones pin it, and `signatures-required` checks
   membership rather than "decrypts". Pairs with decision 16 (signed branch head) and
   closes most of R03/R05 too.
6. CI: Bandit + pip-audit with a baseline (R21).

Each of 1–4 is a day or less with the test already written (invert the `Known_Gaps` test).

---

## Follow-up 2026-10-09 — the "sooner rather than later" fixes, done

**Your question first.** Yes: the read key is symmetric (AES-256-GCM), so whoever can
decrypt can encrypt, and a read-key holder can produce objects, refs, index entries
and key files every client accepts. The write key can't be derived from the read key
(separate PBKDF2 salts; read-only shares never see the passphrase), but it is only a
header the server compares: no client checks anything against it. So the write key is
the server's authorisation check, not a cryptographic guarantee. That is TM-R01, and
it is now stated in §1 of the threat model.

**Fixed (each closed gap's proof moved from `Known_Gaps` to
`test_Security__Fixed__Trust_And_Policy.py`, inverted; 9 of its 11 tests fail on the
code before the fix, 2 are controls):**
- **TM-R02**: new named branches store no private key; `vault move` sentinels are
  signed by the moving clone's key; `vault move` drops a legacy key (the remediation
  for existing vaults: until moved, their key stays readable, TM-R27).
- **TM-R04**: clone enforces `signatures-required` (new step `verify-signatures`,
  before anything is written or registered).
- **TM-R05**: read-only clones refuse a rollback (`--accept-rewind` to follow).
- **TM-R06**: far-future tag entries lose to honest ones; tag names used as revisions
  must verify.
- **TM-R25**: the pull policy check fails closed.

**Two real bugs found while doing it:**
- **TM-F09**: after `sgit vault move`, the clone lost its signing key, so every
  later commit was unsigned. Teammates under `signatures-required` would refuse them.
- **TM-F10**: in a vault with older unsigned commits, switching `signatures-required`
  on made the next push fail. Pull walked past what the clone already held. Fixed by
  recording where the policy starts (`signed-since-<head>` in the features list,
  ignored by older clients) and checking only commits after it, on pull and clone.
  A vault that switched the policy on before this release has no recorded start, so
  clone checks its head only.

**What remains** is TM-R01 itself (owner-signed membership, the large design item)
and Bandit + pip-audit in CI (TM-R21).
