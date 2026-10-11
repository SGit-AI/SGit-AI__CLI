# Plan — the next security review of sgit-ai, with skills, and the review graphs it produces

**From:** the sgit-ai CLI agent · **Date:** 2026-10-11 · **Status:** proposed, for Dinis to accept
or redirect before step 0 runs. **Companion docs:** `research__security-review-skills.md`,
`research__threat-modeling-tools.md`, `map__security-work-already-done.md` in this folder.

## 1. One sentence

Run a tool-assisted, data-producing security review of **one slice** of sgit-ai (the code the
zero-knowledge guarantee and the trust boundaries live in), using five skills and three tools
chosen in the research docs, join every output to the existing register and its tests, and
leave behind the first `review/` graphs and per-file security records, so the case study can
say which tool found what.

## 2. Scope: the slice, and why it is this one

The code-review-graphs brief says not to start an existing repository with a full derivation,
and the `secrets.sgit.ai/review/` page starts from what people actually walk. For a security
review, what people walk is the key path: derive a key, encrypt, send to the host, verify what
comes back, write to disk. Everything the register's High-impact rows touch is in these
packages.

| In scope (round 1) | Files · lines | Why |
|---|---|---|
| `sgit_ai/crypto/` | 9 · 793 | every primitive; the KDF cache; the deterministic metadata mode (KI-SEC-02); PKI |
| `sgit_ai/network/api/` | 13 · 1,504 | the host boundary: presigned URLs, CAS, per-op conflicts, timeouts, scheme rules |
| `sgit_ai/storage/` (`Vault__Path_Guard`, `Vault__Storage`, `Vault__Verified_Write`, `Vault__Object_Store`, `Vault__Index_Reader`, `Vault__Ref_Manager`, `Vault__Branch_Manager`) | 7 of 17 | the local boundary and verified writes; where the path, symlink, baseline and index fixes landed |
| `sgit_ai/core/actions/verify/`, `clone/`, `pull/`, `push/`, `commit/`; `sgit_ai/core/Vault__Secret_Guard.py`, `Vault__Ignore.py` | 5 of 28 action groups + 2 | verify-then-accept, the rewind guard, the secret guard and the always-ignored set |
| `sgit_ai/secrets/`, `sgit_ai/cli/CLI__Main.py`, `CLI__Credential_Store.py`, `CLI__Token_Store.py`, `CLI__Debug_Log.py`, `CLI__Vault.py` | 6 files | where keys are stored, pinned, printed and logged (TM-R14 is High) |
| `.github/workflows/*.yml`, `pyproject.toml`, `sgit update` | 3 + 2 | supply chain (TM-R21) |

41 source files, about 11,300 lines (counted with `wc -l`), out of 469 files. **Out of scope for round 1:**
`plugins/`, `workflow/`, `migrations/`, the rest of `cli/`, `core/serve`, `mirror`, `publish`
(round 2 candidate: their code-stage review is owed since 08/19), `objects/`, `safe_types/`,
`schemas/` (covered by the Type_Safe tests and the round-trip invariant).

## 3. The tools, and what each is for

| Step | Tool | Chosen because | Not chosen |
|---|---|---|---|
| 0 | OWASP AST10 checklist; `cisco-ai-defense/skill-scanner` | the only published rubric for installing third-party instruction files into a key-custody repository | SkillLedger and skillsign: nothing on our list is signed, so there is nothing to verify |
| 1 | Trail of Bits **audit-context-building** | a per-function dossier with a line for every claim and "nothing found" for unestablished assumptions; no verdicts, so it cannot anchor the later steps | Sentry's "research the code base first" is a paragraph, not an artefact |
| 1 | a parser (Python `ast`) | the code-review-graphs brief: derived structure comes from parsers, never a model | STRIDE GPT's repository stage: it is a model reading code, so its output goes in the intent/explanation layer, not `graph/` |
| 2 | **STRIDE GPT** CLI (`analyze`, JSON, Anthropic via LiteLLM) and the **`stride-threat-modelling` skill** copy | two independent STRIDE passes with the same rubric: one by the tool, one by this agent; stable threat ids; evidence required per threat | the hosted `mcp.stridegpt.ai` endpoint (sends the description off-machine); pytm and Threagile (their libraries are web- and infrastructure-shaped; a pytm model file is a round 2 artefact once the DFD exists as data) |
| 2 | Matt Adams' **insider-threat model** (27 threats) | the agent as actor; thirteen threats already map to register rows after one reading | |
| 3 | Sentry **security-review** (cryptography, file-security, supply-chain, logging guides) and **secret-serialization**; Trail of Bits **insecure-defaults**, **sharp-edges**, **differential-review** (0.20.0 → 0.21.0), **post-patch-validation** (the 0.21 fixes) | method, not pattern list; the diff of 0.21.0 is the largest security diff the project has had and two of its fixes regressed | Project CodeGuard: read its crypto and supply-chain rules once, cite where relevant, do not install; the "Anthropic Cybersecurity Skills" library (not Anthropic's, no code-review domain); Varlock (keep the rule, not the skill); squirrelscan (nothing to audit in a CLI) |
| 3 | **Semgrep** (`p/python`, `python.cryptography.*`, Trail of Bits rules), **Bandit**, **pip-audit**; Sentry **gha-security-review** on the workflows | deterministic, SARIF, and the CI baseline TM-R21 has wanted since 10/08 | CodeQL: worth adding at the CI step if the Semgrep pass leaves gaps; not first |
| 3 | Anthropic **`/security-review`** | already here; diff-scoped; a second opinion on the pending changes of each fix commit | as the whole-slice review: its filter drops DoS-shaped findings by design, and three accepted rows are DoS-shaped |
| 4 | Trail of Bits **fp-check**; Matt Adams' **threat-led-triage** over all findings with the STRIDE GPT model | every finding is a claim to verify; ranking by reachability across *our* boundaries is how the list stays short | CVSS-style scoring |
| 5 | the house `.security.json` schema; the `review/` layout from the code-review-graphs brief | so the output is data the sites can join and the next review can diff | a prose report alone |
| 6 | the TM-Bench rubric (four dimensions) with the register as ground truth | the measurable part of the case study | running TM-Bench itself (no public harness) |

## 4. The steps

Each step names its output. Outputs that are data go under `review/` (new, at the repository
root, per the brief); prose goes under this folder's date; threat-model changes go in the
register with their tests, as §9 of the threat model requires.

### Step 0 — Vet, pin, canary (half a day)

1. Clone each skill source at a commit SHA; record SHA and `sha256` of every SKILL.md.
2. Run `skill-scanner scan-all --format sarif` over the lot; HIGH blocks install. Keep the SARIF.
3. Fill the AST10 table from `research__security-review-skills.md` §2 for each skill.
4. Install into this cloud session only (no vault key, no token, no `.env` on disk here):
   Trail of Bits plugins (`audit-context-building`, `insecure-defaults`, `sharp-edges`,
   `differential-review`, `post-patch-validation`, `fp-check`, `static-analysis`,
   `supply-chain-risk-auditor`); Sentry `security-review`, `secret-serialization`,
   `gha-security-review`; `stride-threat-modelling` skill copy; `threat-led-triage` skill;
   `pip install stride-gpt==<pinned>` with hashes; Semgrep, Bandit, pip-audit pinned.
5. Rule for every run: the agent never reads `.sg_vault/local/*`, never prints a key, never
   runs a skill's "fix" mode. Written at the top of the session prompt.

**Output:** `…/10/11/case-study/00__vetting.md` with the table and SARIF.

### Step 1 — Context and the first derived graph (one day)

1. `audit-context-building` over the slice → `audit-context/DOSSIER.md` and one file per function.
   Read the "nothing found" assumptions first; they are the candidate threats.
2. A small `ast`-based deriver (classes, methods, calls within the slice, tests that import each
   module) → `review/graph/{files,classes,methods,tests}.json`, each node with path, lines and
   tree hash, per the brief's grammar. Freshness checked by tree hash. **Parsers only.**
3. Intent for the slice, written from the threat model's §2 assets, §4 boundaries and §5
   mechanisms, each node citing its section → `review/intent/boundaries.json`,
   `mechanisms.json`. This is the top-down half, and it is small because the register already is
   the intent.

**Output:** the dossier; `review/graph/` and `review/intent/` seeds; `review/README.md` with
counts written by the deriver, not by hand.

### Step 2 — Threat model, two ways, plus the insider overlay (one day)

1. `stride-gpt analyze <slice> -f json -o review/stride/stride-gpt.json` with the cost estimate
   recorded first. Also `-f sarif` for the triage step.
2. This agent runs the `stride-threat-modelling` skill over the same slice and the dossier →
   `review/stride/agent.json`, same schema (id, STRIDE class, component, description, evidence
   line, mitigation).
3. Reconcile → `review/stride/join.json`: each threat id ↔ TM-R/TM-F row ↔ test file, or `new`,
   or `out-of-scope-by-model` (the host-and-harness threats). Disagreements between the two
   passes are kept, not averaged (the house two-modes rule).
4. Insider overlay: confirm the thirteen mappings in the threat-modeling doc §1.1 against code;
   add actor **A9** (the agent holding the key) to the register §3, and a column to §6 naming the
   insider threat ids each row answers. Where a mapping proves an *open* gap, write its
   `Known_Gaps` test in the same commit.

**Output:** `review/stride/` (three files); a register change with tests; the first number for
the case study (STRIDE GPT's completeness and coverage against the register).

### Step 3 — Code review (two days)

Run in this order, each writing findings as `VULN-###` / `VERIFY-###` with file, line, evidence:

1. Semgrep, Bandit, pip-audit → `review/findings/semgrep.sarif`, `bandit.json`, `pip-audit.json`.
   These three also become the CI baseline: a new job step in "Run Security & Adversarial Tests"
   that fails on *new* findings only (closes TM-R21's open half).
2. `insecure-defaults` and `sharp-edges` on `crypto/` and `storage/`.
3. Sentry `security-review` on the slice with the cryptography, file-security, supply-chain and
   logging guides; `secret-serialization` on `crypto/Vault__Secret_File.py`, `secrets/`,
   `cli/CLI__Debug_Log.py`, `cli/CLI__Vault.py`, `cli/CLI__Credential_Store.py`.
4. `differential-review` on `git diff 0.20.0..0.21.0 -- <slice>`; `post-patch-validation` on
   the TM-F25→F29 and TM-F27→F30 pairs specifically (the two fixes that regressed).
5. `gha-security-review` on the three workflows; `supply-chain-risk-auditor` on `osbot-utils`
   and `cryptography`.
6. `/security-review` on each fix commit as it is made (step 4), as the PR gate.

**Output:** `review/findings/<tool>.json` per tool, same record shape, each with `tool`,
`confidence`, `file`, `line`, `evidence`.

### Step 4 — Triage and fix (one day, plus the fixes)

1. `fp-check` over every finding; a finding without a reproducing path is `VERIFY`, not `VULN`.
2. `threat-led-triage rank review/findings/*.json against review/stride/stride-gpt.json` →
   `review/findings/ranked.json`, with the "could not determine" list kept.
3. House rule applies to anything real: a `Fixed` test that fails on the current code, the fix,
   the register row, the CHANGELOG line, in one commit. Anything accepted gets a `Known_Gaps`
   test and a `risk_decision` with owner and rationale.

**Output:** fixes with tests; register updated; the per-tool true/false-positive counts for the
case study.

### Step 5 — Per-file records and the skill rule (half a day)

1. One `.security.json` per file in the slice (house schema: `attack_surface`,
   `vulnerabilities` with `risk_decision`, `secrets_exposure`, `dependencies` with
   `trust_boundary_crossings`, `redundant_code`), written from the dossier and the findings,
   every claim with a line → `review/security/<path>.security.json`. The slice is 41 files;
   that is the whole point of the slice.
2. Add to `library/skills/sg-send-cli__SKILL.md` (and the sgit skill on `skills.sgit.ai`) the
   rule Varlock states and the insider model's I4 needs: never print, echo or log a vault key,
   read key, write key or token; read keys from the store, not from argv; prefer the key prompt.
   This is the one thing from the screenshot list that becomes a line in our own skill.

**Output:** `review/security/`; the skill change.

### Step 6 — Publish (half a day)

1. The two research docs → `skills.sgit.ai` and `threat-modeling.sgit.ai` Documents, as they are.
2. The case study: which tool found what (true positives, false positives, time, cost per
   tool), STRIDE GPT scored on the four TM-Bench dimensions against the register, the insider
   overlay result, the vetting table and the signature gap → both sites, and to Matt Adams.
3. Link the 0.21.0 register and the case study from `sgit.ai/security/` (closes "being
   prepared").

## 5. Acceptance

- Every file in `review/graph/` is regenerated byte-identically by the deriver from the tree
  hash it names; a stale file fails the check.
- Every STRIDE threat in `review/stride/join.json` resolves to a register row with a test, or is
  marked `new` with a `VERIFY`, or `out-of-scope-by-model` with the reason.
- Every `VULN` has a test that fails on the code before its fix; every accepted gap has a
  `Known_Gaps` test and a `risk_decision`.
- The security CI job runs Semgrep, Bandit and pip-audit against a committed baseline and is
  green on the head that adds it.
- Suites on the final head: unit, security, integration, QA all pass, with counts in the note.
- The case study reports per-tool counts, not impressions.

## 6. Risks of the plan itself

| Risk | Handling |
|---|---|
| A skill is a supply-chain vector into a key-custody repository (AST01/02) | step 0; cloud session with no keys; pinned SHAs; no fix modes |
| Prompt injection from repository content into a review skill: `tests/security/` and the review-round tests contain adversarial strings by design (hostile paths, `(ſ[a-z]+)+$`, forged objects) | review skills read `sgit_ai/`, not `tests/`; findings cite `sgit_ai/` lines only; the agent treats skill output as claims |
| STRIDE GPT sends the slice to the model provider | the code is Apache-2.0 and public; never run it over a checkout holding `.sg_vault/local`; record the cost estimate first |
| Finding flood: 23 Bandit mediums were counted in March | step 4's ranking and the baseline; only ranked-reachable findings get a test |
| The derived graph becomes hand-maintained | `review/graph/` is written by the deriver only; the freshness check is in the acceptance list |
| Scope creep into `plugins/`, `workflow/`, `serve`/`mirror`/`publish` | named out of scope; round 2 is a separate plan with its own note |

## 7. Decisions needed from Dinis

1. Accept the slice, or swap one package in or out (the obvious candidate to add is
   `core/actions/publish` + `mirror`, owed since 08/19; it would make round 1 about 60 files).
2. Whether `review/` goes at the repository root now (the brief's layout) or under
   `team/explorer/appsec/review/` until the deriver is trusted. The plan assumes the root.
3. Whether to tell Matt before or after the run that his three tools are being test-driven on a
   published register with tests, so he can say what he would like measured.
