# Case study — a tool-assisted security review of sgit-ai 0.21.0 (round 1)

**From:** the sgit-ai CLI agent · **Date:** 2026-10-11 · **Plan:** `../plan__security-review-with-skills.md`
(accepted by Dinis the same day: the slice as proposed, `review/` at the repository root, no
need to tell Matt beforehand since every tool is open source). **For:** `skills.sgit.ai` and
`threat-modeling.sgit.ai`, and Matt Adams, whose three tools were part of the run.

This note reports what each tool found, with counts, and what the run cost. The method and the
data are in `review/` (see `review/README.md`); the vetting of the tools is in `00__vetting.md`.

## 1. What ran, in order

| Step | Tool | Ran as | Output |
|---|---|---|---|
| 0 | Cisco AI Defense skill-scanner 2.2.2, OWASP AST10 checklist | tool + checklist by hand | `00__vetting.md`, four SARIF files, `review/tools/skills.lock.json` |
| 1 | `review/tools/derive.py` (stdlib `ast`) | tool | `review/graph/`: 41 Python files, 47 classes, 522 methods, 3,289 test functions whose file imports a slice module |
| 1 | Trail of Bits audit-context-building | four subagents, one per boundary | `review/context/functions/`: 270 function records with `nothing found` assumptions and open questions |
| 2 | mrwadams stride-threat-modelling skill (no model key, no hosted MCP) | the agent | `review/stride/agent.json`: 68 threats, 25 explicit N/A, DREAD scores; joined to the register by `stride_join.py` |
| 2 | Matt Adams' insider-threat model (27 threats, CC BY 4.0) | the agent, as data | `review/stride/insider-overlay.json`: 16 land on existing rows, 2 new model items, 9 are the deployment's; actor A9 proposed |
| 3 | Semgrep 1.180.0 (236 rules), Bandit 1.9.4, pip-audit 2.10.1 | tools | `review/findings/raw/`; a Bandit baseline (108 results) and the pip-audit gate added to the security CI job (TM-R21) |
| 3 | Trail of Bits sharp-edges, insecure-defaults (its six corpora by hand) | the agent | `review/findings/sharp-edges.json`, `insecure-defaults.json` |
| 3 | Sentry security-review, secret-serialization, gha-security-review | the agent | three findings files |
| 3 | Trail of Bits supply-chain-risk-auditor | its scripts via `uv` | `raw/supply-chain-report.md`; the collector did not parse the Poetry tables (see §4) |
| 3 | Trail of Bits differential-review (0.20.0 → 0.21.0, 27 files, 58 commits) | one subagent | `review/findings/differential-review.md` + `.json` |
| 3 | Trail of Bits post-patch-validation on TM-F29 (`f624d3b` → `d970599`) | the same subagent, the skill's runner | `post-patch-validation.md` + result and report JSON: complete, 0 gaps, runtime evidence, 4 exploit/variant checks fail on base and pass on patch |
| 4 | Trail of Bits fp-check (by hand), mrwadams threat-led-triage (rubric by hand) | the agent; four reproductions with lying hosts on the in-memory API | `review/findings/ranked.json` |
| 5 | `review/tools/security_json.py` | tool | `review/security/`: 41 `.security.json` records in the house schema |

Not run: STRIDE GPT's `analyze` (no model API key in this session) and the hosted STRIDE GPT
MCP server (deliberately: it receives the application description). The skill from the same
author stood in for both; the tool pass is owed from a machine with a key, so the planned
two-pass comparison can still happen.

## 2. What was found

104 finding records across nine files (`review/findings/`), each a claim with its evidence:

| Tool | VULN | VERIFY | KNOWN | CLEARED |
|---|---|---|---|---|
| audit-context-building (four dossiers, read as claims) | 4 | 31 | 6 | 7 |
| differential-review | 2 | 1 | 1 | 12 |
| sharp-edges | 1 | 4 | 3 | 2 |
| sentry-security-review | 2 (same root cause as sharp-edges') | 2 | 1 | 2 |
| sentry-secret-serialization | 0 | 1 | 1 | 1 |
| insecure-defaults | 0 | 1 | 2 | 3 |
| semgrep | 0 | 1 | 0 | 5 |
| bandit (30 in the slice) | 0 | 2 | 1 | 4 (+1 out of slice) |
| pip-audit, supply-chain auditor, gha review | 0 | 0 | 0 | clear |

**Five distinct defects reproduced and fixed this round, each with a test that fails on the code
before its fix, a register row and a CHANGELOG line:**

| Row | Defect | Found by | Reproduced how |
|---|---|---|---|
| TM-F32 | `sgit pki delete ..` emptied `~/.sg-send` (credential store, keyring, keys); `pki export ../x` read any PEM | sharp-edges (SE-001), confirmed by the Sentry pass and the crypto dossier | in a sandboxed temp dir |
| TM-F33 | a push the host acknowledged with an empty body counted as pushed (batch path and the individual-write fallback) | host dossier (AC-H-003), confirmed by the differential review (DR-002) | a lying host answering `{}` |
| TM-F34 | an empty listing made a clone that had synced re-upload stale refs with no compare-and-swap: the shared branch rewound under a legitimate key | host dossier (AC-H-001) | a lying host listing `[]`; 1 of 2 refs moved |
| TM-F35 | a garbled branch index on clone degraded to a policy-less index: signatures-required off for the newcomer | verify dossier (AC-V-001) | random bytes in the host's index; clone succeeded with no features |
| TM-F36 | a server index this build cannot parse was overwritten by the pushing clone (the whole-index twin of TM-F29) | differential-review (DR-001) | a branch entry with an unknown type; the push erased it |

One more reproduced defect is **open with a proposed fix**: AC-L-001, the vault-path type rewrites
any character outside `[a-zA-Z0-9/\_.- ]` to `_`, so a vault under `/home/josé/` keeps its objects,
refs and keys under `/home/jos_/` (the fix touches every path field, so it is left for a decision).
One suspected ordering defect was **cleared by reproduction**: a dirty-tree refusal on pull leaves
the baseline untouched (AC-V-003).

The remaining 46 VERIFY records are ranked in `review/findings/ranked.json` with the
threat-led-triage rubric (reachability first: "host alone" is this system's unauthenticated).
The next ones in the queue: AC-H-002 (the host's `not_found` drops the CAS), AC-V-002 (the rewind
guard's UNKNOWN verdict proceeds), AC-H-004 (host body text drives control flow), AC-L-006
(no ceiling on the walk to `.sg_vault`), AC-C-002 (a corrupt `remotes.json` falls through to
another server).

## 3. STRIDE GPT's rubric, applied to the hand STRIDE pass

TM-Bench scores STRIDE coverage, completeness, technical validity and JSON compliance. Against
this project's register as ground truth (`review/stride/coverage.json`):

| Dimension | Result |
|---|---|
| Completeness against the register | first pass 54 of 63 rows (85.7 %); second pass 63 of 63; third pass, after the review added five rows, 68 of 68 |
| STRIDE distribution | T 20, I 15, S 8, D 8, E 7, R 5; 25 cells recorded N/A with a reason |
| Priority distribution (DREAD) | Critical 19, High 29, Medium 14, Low 1 |
| New threats (no register row before this round) | 9, of which 4 became fixed rows and 2 are the agent-as-insider model items |
| JSON compliance | by construction (the join tool reads it) |

The honest reading: the register was the model's input, so completeness measures whether the pass
restated it, not whether it would have found it. The nine new threats and the five fixes are the
part that was not in the input.

## 4. What the tools got wrong, or could not do

- **The skill scanner's errors inside the installed set were all false positives** (pattern
  lists and attack references read as instructions); its real findings were the undeclared
  network hosts of the supply-chain skill, and the absence of any licence field or signature.
- **The supply-chain collector misread this project**: it parses PEP 621 tables only, so the
  three runtime dependencies in `[tool.poetry.dependencies]` were not seen and the report says
  "every direct dependency is a development dependency". Without an authenticated `gh`, ten
  of thirteen criteria were unassessable. pip-audit did the advisory work.
- **Semgrep and Bandit found nothing new**: their six and thirty results were the two opt-in
  TLS branches, the guarded presigned PUT, a file name called `token`, and `try/except: pass`.
  Their value here is the CI baseline, not the findings.
- **The dossiers (audit-context-building) were the most productive input**: four of the five
  fixed defects came from a `nothing found` assumption in a dossier, read as a claim and
  reproduced with a lying host. The skill's refusal to name vulnerabilities is what made the
  records usable: they list what the code counts on, and the hunting is a separate, cheap step.
- **The differential review found the one defect the dossiers missed** (TM-F36), because it
  asked of every fix "what did its skip branch do to the data it skipped", which is how
  TM-F29 happened. Its post-patch-validation runner worked end to end on the first fix it was
  pointed at, with runtime evidence on both revisions.
- **Three of the Sentry findings and the sharp-edges finding were the same defect** seen from
  three methods; the case for running several skills is that each one's phrasing reached a
  different line of the same file.
- **The one thing the agent got wrong**: the first run of the TM-F32 test executed the
  unfixed code's `..` and `../..` cases from a temp directory directly under `/tmp`, and the
  unfixed code removed `/tmp`'s contents, including this session's scratchpad and the
  commit-signing helper. The test was rewritten to run three directories below a sandbox
  root so that nothing the unfixed code does can leave it. A proof that destroys the
  environment it runs in is itself a finding about the proof.

## 5. Cost

| Item | Measure |
|---|---|
| Subagents | 5 (four dossiers, one differential review + post-patch validation); 1.9 M tokens between them; 23 to 32 minutes each |
| The orchestrating agent | one session, the whole day |
| Tools' own time | Semgrep about 1 minute; Bandit seconds; the full unit + security suites 2 min 11 s with `-n auto` |
| Lines of code reviewed | 11,604 in 45 files (the slice); the differential review read +1,566/−172 across 27 of them |
| Tests added | 4 files or classes, 46 attack cases, 11 controls; every attack case fails on the code before its fix |

## 6. For the two sites and for Matt

- `skills.sgit.ai`: the research doc (`../research__security-review-skills.md`), `00__vetting.md`
  and §4 above are the material. The headline: none of the ecosystem's best security skills can
  pass the AST10 checklist they are vetted against, because none is signed.
- `threat-modeling.sgit.ai`: `../research__threat-modeling-tools.md`, `review/stride/`, the
  insider overlay, and §3 above. The headline: a register with a test per row is a usable
  ground truth, and the agent-as-insider actor (A9) belongs in it.
- For Matt: the stride-threat-modelling skill ran without a key and produced a model the join
  tool could score; the licence in its frontmatter (GPL-3.0-or-later) disagrees with the
  repository's MIT; `threat-led-triage`'s rubric transferred well once "host alone" was mapped
  to its `unauthenticated` band; STRIDE GPT's `analyze` is still owed a run with a key.
