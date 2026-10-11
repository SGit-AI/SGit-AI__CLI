# Security work already in this repository — the map

**From:** the sgit-ai CLI agent · **Date:** 2026-10-11 · **Head:** `bc8016d` (main, 0.21.0).

Everything below exists on disk today. Counts are from the files, not from memory. The last
column says what each piece does *not* cover, which is what the next review is for.

## 1. Threat models and reviews

| Artefact | Where | Size | What it holds | Not covered |
|---|---|---|---|---|
| **Threat model and risk register, v0.21.0** (living, current-state) | `team/explorer/appsec/threat-model/v0.21.0__threat-model.md` | 254 lines, 9 sections | §1 sgit in security terms (the one fact: the read key is symmetric, the write key has no cryptographic role). §2 assets. §3 actors A1 host … A8 other clients. §4 trust boundaries. §5 what each mechanism guarantees and does not. §6 register: **31 fixed rows (TM-F01..F31)**, **5 by design** (TM-R01 forgery by a read-key holder with store access, R08 metadata, R12 no read revocation, R13 bearer write key, R26 other clients), **22 accepted** (R03, R07, R09–R11, R14–R21, R27–R35), **fix soon**: TM-R01 owner-signed membership, the 3e099ee N3–N9 list for 0.21.1, TM-R21 Bandit and pip-audit. §7 coverage map threats → tests. §8 mapping from earlier registers (KI-SEC-01..06, SP-1..15). §9 how it stays current (a row changes only with its test) | No STRIDE classification per row. No DFD. The agent is not an actor. Per-file granularity absent (it is per risk). No tool-assisted pass: four parallel agent reviews by hand, then five review rounds with the sgit.ai agent |
| **AppSec review, static-publishing feature set** (design-stage) | `team/explorer/appsec/reviews/08/19/v0__appsec-review__static-publishing.md` | 841 lines | 15 findings SP-1..SP-15 (High: clone does not verify what it fetches, no freshness anchor, manifest as authority); dedicated freshness and rollback analysis; tier-confusion analysis; recommendations per pack file; accepted-risk candidates; what a real-GitHub tabletop should probe. SP-1 is since fixed (verify-before-write, TM-F01/F02); SP-2/3/5/14 are TM-R19 accepted | `publish`, `serve`, `mirror`, `attach` were not built then; `CLI__Publish`, `CLI__Serve`, `CLI__Mirror` and `core/actions/{publish,mirror}` exist now and have not had a code-stage review |
| **Review: git security features → sgit, a one-way mapping** | `team/humans/dinis_cruz/claude-code-web/10/08/review__git-to-sgit-security-mapping.md` | | Verdict on the research note; the gap the note missed: **no per-writer authorisation** (one write key per vault); what was built from it in 0.21.0 (signed tags, reflog, force-with-lease, `.git` spelling guard); still open (server-side enforcement, push certificates, format 2 by default) | |
| **Security review before 0.21.0** | `…/10/08/security-review__0.21.0-threat-model-and-tests.md` | | What was done (four parallel reviews), fixed groups TM-F01..F08, the test design, why a separate CI job, the "sooner" list, and the 10/09 follow-up closing TM-R02/R04/R05/R06/R25 | |
| **Five review-response notes** (release gate rounds with the sgit.ai agent) | `…/10/09/review-response__00d6fc1.md`, `__d3b8eef.md`; `…/10/10/review-response__0a0707d.md`, `__eed8084.md`, `__3e099ee.md` | | Each: findings by id (K, S, B, N, R, F, L series), status, the test that proves it, suite counts on the new head. Two rounds found regressions introduced by the previous round's fixes (TM-F29 from TM-F25, TM-F30 from TM-F27) | The responses are per-commit; nothing rolls them up by file or by module |
| **Design notes with security content** | `…/10/09/design-analysis__read-write-keys-as-pki.md`, `design__native-pki-vault-mode.md`, `design__sealed-files-layer.md` | | The PKI analysis (phase 1 writer-signed index closes TM-R29/R32 and most of R03; phase 2 wrapped capabilities removes most of TM-R14) | Not built |
| **Briefing pack, March** | `library/sgit-ai/briefing-packs/03/20/04__CRYPTO_DESIGN.md`, `10__KNOWN_ISSUES.md` | | Crypto design as specified; KI-SEC-01..06 (48-bit ids, deterministic tree encryption, read key on disk, classical PKI, Bandit mediums, supply chain) | Older than the register; §8 of the threat model maps each KI-SEC to a TM row |
| **Public security page** | `sgit.ai/security/` | | What the host sees and does not; the primitives; the exposed-vault-key case study and rotation runbook; "the internal security review (twelve findings …) is being prepared" | The 0.21.0 register is not linked from it yet |

## 2. Tests that prove the register

| Suite | Where | Count | Role |
|---|---|---|---|
| **Security and adversarial** (hermetic; own CI job "Run Security & Adversarial Tests", gates release) | `tests/security/` | 10 files; 157 tests on the 3e099ee head (from `10/10/review-response__3e099ee.md`) | `test_Security__Known_Gaps.py` performs each accepted attack and asserts it **works** (TM-R01, R03, R07, R08, R09, R10, R11, R27). `test_Security__Fixed__*` (Baselines, Host_Substitution, Hostile_Paths, Index_Overwrite, Secrets_In_Commits, Server_Pin, Symlinks_And_Local, Trust_And_Policy, Verify_Then_Accept) replays each fixed attack and asserts it fails; each checked against the pre-fix code |
| **Server boundary, real server** | `tests/integration/test_Security__Server_Boundary__Integration.py` | | A reader without the write key gets 403 on every way to move a ref, delete or add objects; positive control with the owner's key |
| **The adversary as a fixture** | `tests/_helpers/vault_adversary.py` | | Holds the read key only, writes straight into the host's store: forge commits, move branches, substitute bytes |
| **Hermetic guard** | `tests/unit/conftest.py`, `tests/security/conftest.py`, `tests/_helpers/hermetic_network.py` | | Any unit or security test that opens a non-loopback connection fails |
| **Review-round tests** | `tests/unit/review/test_Review__*.py`, `test_Push__Concurrent_CAS.py`, `test_Format_Gate_And_Integrity.py` | | One file per review round, named by the commit reviewed |
| **Mutation tests** | CI job "Run Mutation Tests" | | Surviving mutants reported as an artefact |
| **Whole suite on the 0.21.0 head** | | unit 4,168 · security 157 · integration 74 · QA 122 (20 skipped) | |

## 3. Security mechanisms in code (the slice the next review will read)

| Mechanism | Where | Register rows it serves |
|---|---|---|
| Key derivation, AES-GCM, object ids, deterministic metadata encryption, KDF cache | `sgit_ai/crypto/Vault__Crypto.py` (module-level `_pbkdf2_cached`, then the class), `Vault__Key_Manager.py`, `Vault__Secret_File.py` | TM-R08, R11, R16, SP-13, KI-SEC-02 |
| PKI: ECDSA P-256 signing, RSA-OAEP envelope, passphrase-protected private keys | `sgit_ai/crypto/PKI__Crypto.py`, `sgit_ai/crypto/pki/` | TM-R01, R17, R20 |
| Signature verification, key fetch, verify-then-accept | `sgit_ai/core/actions/verify/` (`Vault__Signatures`, `Vault__Key_Fetch`); `sgit_ai/core/actions/pull/Vault__Incoming_Check.py` | TM-R04, R25, F13, F14, F19 |
| Verified writes (content address checked before anything is written) | `sgit_ai/storage/Vault__Verified_Write.py`, `Vault__Object_Store.py` | TM-F01, F02, F07 |
| Path guard (`.git` spellings, NTFS streams, Unicode, `.sg_vault`), `safe_join`, no-follow reads | `sgit_ai/storage/Vault__Path_Guard.py`, `Vault__Storage.py` (`write_private`, `read_regular`) | TM-F03, F04, F11, F20, F27, F30 |
| Index reading that carries what it cannot parse | `sgit_ai/storage/Vault__Index_Reader.py` | TM-F25, F29 |
| Baselines and rewind guard | `sgit_ai/core/actions/pull/Vault__Ref_Guard.py`, `Vault__Sync__Pull.py`; `sgit_ai/storage/Vault__Ref_Manager.py`, `Vault__Branch_Manager.py`, `Vault__Reflog.py` | TM-F12, F23, R05 |
| Secret guard on commit (zips with keys, hard links, `.pem`) | `sgit_ai/core/Vault__Secret_Guard.py`, called from `sgit_ai/core/actions/commit/Vault__Sync__Commit.py`; `sgit_ai/core/Vault__Ignore.py` (always-ignored set: `.env*` except templates, `.netrc`, `id_rsa` and the other SSH private keys) | TM-F18, F27, F31, R09, R34 |
| Host boundary: API client, backends, HTTP pool, presigned URL rules, CAS and per-op conflicts | `sgit_ai/network/api/` (`Vault__API`, `Vault__Backend__API`, `Vault__HTTP_Pool`, `Vault__Transport_Errors`) | TM-F07, F08, F21, R10, R33 |
| Server pin per command, `SGIT_DEFAULT_BASE_URL` refusal | `sgit_ai/cli/CLI__Main.py` | TM-F15, F22 |
| Credential and token stores; key printing | `sgit_ai/secrets/Secrets__Store.py`, `sgit_ai/cli/CLI__Credential_Store.py`, `CLI__Token_Store.py`, `CLI__Vault.py` (`vault info`), `CLI__Debug_Log.py` | TM-R11, R14, R15, F05 |
| Supply chain | `.github/workflows/ci-pipeline*.yml` (release actions SHA-pinned), `sgit update` (`python -I -m pip`, unpinned target) | TM-R21, F06, SP-10 |

## 4. What has not been done

- **No tool-assisted pass at all.** Every review so far was an agent reading code and writing
  prose; no Semgrep, Bandit, pip-audit, CodeQL, or STRIDE GPT run exists in the repository. TM-R21
  has asked for Bandit and pip-audit with a baseline since 10/08.
- **No STRIDE or DFD view** of the register. Rows have actor, likelihood and impact, not a
  STRIDE class; no diagram of the boundaries exists as data.
- **The agent is not an actor** in §3, although agents are the primary operators.
- **No per-file security record** (`.security.json`) for any file, and no `review/` folder: the
  register is per risk, the tests per attack, the responses per commit; nothing joins them by
  file or by method.
- **`publish`, `serve`, `mirror` have had a design-stage review (08/19) only**, not a code-stage one.
- **No independent review** by a person or a team outside the two agents (this one and the
  sgit.ai agent). The sgit.ai security page's "being prepared" internal review is the 0.21.0
  register; it is not yet published there.
- **`plugins/` (32 files) and `workflow/` (82 files)** have never been in scope of a security
  review by name.
