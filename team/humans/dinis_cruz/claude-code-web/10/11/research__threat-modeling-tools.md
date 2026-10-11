# Threat-modeling tools for an agent-driven review — Matt Adams' stack, the classics, and the house method

**From:** the sgit-ai CLI agent · **Date:** 2026-10-11 · **For:** `threat-modeling.sgit.ai`
(Documents), then the case study once used.

**Why this matters more here than elsewhere.** sgit is operated by AI agents that hold vault
keys and write tokens. The threat model's actor list (`team/explorer/appsec/threat-model/v0.21.0__threat-model.md`
§3) names the host, the network, a read-key holder, a teammate, a hostile vault author, the
local machine, the supply chain and other clients. It does not yet name **the agent itself** as
an actor. Matt Adams' insider-threat model is the first published framework that does, and it
was generated with his own tool, so the two fit together.

## 1. Matt Adams' stack (mrwadams)

| Tool | What it is | Facts checked | Fit for sgit |
|---|---|---|---|
| **STRIDE GPT** | Open-source LLM threat modeller. Inputs: an application description, an architecture image, a draw.io diagram, a GitHub repository URL, or a **local code base** (`stride-gpt analyze <path>`, agentic: plan, explore, synthesise per subsystem). Outputs: STRIDE threat model with mitigations, attack trees, DREAD scores, Gherkin test cases, DFDs, MITRE ATT&CK and ATLAS mapping, OWASP LLM and agentic risk overlays. Formats: Markdown, **JSON**, **SARIF**, self-contained HTML; `-o` also writes plan, findings and run JSON | `github.com/mrwadams/stride-gpt`, MIT, v0.20, about 1.1k stars. `pip install stride-gpt` gives the CLI; web UI from source (`uv sync`, Streamlit) or `docker pull mrwadams/stridegpt`. **Anthropic is supported** through LiteLLM (the README's About line still says OpenAI; it is stale). Recent PRs: threats get a stable identifier (#231), a `report_threat` tool that demands verifiable evidence plus a final grace round (#205), a cost estimate before an `analyze` run (#218) | **The threat-model generator for the review.** Run it on the slice, in JSON, and join each threat id to a TM-R/TM-F row or to "new". The stable ids and the evidence requirement are exactly what a join needs. The code it reads is Apache-2.0 and public; never point it at a folder holding a vault key or `.env` |
| **mcp-stride-gpt** | An MCP server that is a *framework provider, not an analyser*: it returns the STRIDE method, the DREAD rubric, attack-tree structure, test scaffolding and report skeletons; the client's model does the thinking. Eight tools (`get_repository_analysis_guide` by stage, `get_stride_threat_framework`, `generate_threat_mitigations`, `calculate_threat_risk_scores`, `create_threat_attack_trees`, `generate_security_tests`, `generate_threat_report`, `validate_threat_coverage`). Ships the companion **`stride-threat-modelling` skill** | `github.com/mrwadams/mcp-stride-gpt`, MIT. Hosted at `mcp.stridegpt.ai` (`claude mcp add stride-gpt https://mcp.stridegpt.ai/ --transport http`), or plugin (`/plugin marketplace add mrwadams/mcp-stride-gpt`), or copy `skills/stride-threat-modelling/` into `.claude/skills/`. Self-host: Python 3.12 standard library only, port 8787, no auth, keep on loopback | **Use the skill copy, not the hosted endpoint.** The hosted server receives the application description; the skill copy keeps everything in-session. It lets this agent do the STRIDE pass with the same rubric STRIDE GPT uses, so the two outputs are comparable |
| **TM-Bench** | A benchmark for LLM threat modelling, aimed at models that run on consumer hardware. Four dimensions: **STRIDE coverage and accuracy (30 %)**, **threat completeness (30 %)**, **technical validity (30 %)**, judged by an LLM (Claude Sonnet 4.6 in v2), and **JSON structure compliance (10 %)**, scored programmatically. Three complexity tiers of application description with synthetic ground-truth models | `tmbench.com` (home, methodology). No public repository or dataset found; maintainer not named on the site, the support link is `mrwadams`. v1 used Claude 3.7 Sonnet as judge, so v1 and v2 scores are not comparable | **Borrow the rubric, not the harness.** Our hand-written register (32 TM-R rows, 31 TM-F rows, each with a test) is a real ground truth. Scoring STRIDE GPT's output of the slice against it on TM-Bench's four dimensions is the measurable part of the case study, and a result worth sending to Matt |
| **threat-led-triage** | A Claude Code / Codex skill that *ranks* existing findings by what an attacker can reach and chain in this code base, not by CVSS. Inputs: findings (SARIF, SCA, CVE list, pentest, or free text), the checkout, and optionally a STRIDE GPT model of the same repo (supplies the trust boundaries). Output: ranked list with per-finding reachability, code path, boundary crossed, chains, and the severity adjustment with its reason; plus an explicit "could not determine" list. It finds nothing new | `github.com/mrwadams/threat-led-triage`, MIT. Run: `stride-gpt analyze . -o model.json -f json`, then `/threat-led-triage rank findings.json against model.json for this repo`. Worked example on OWASP crAPI in `test/` | **The triage step.** Semgrep, Bandit, pip-audit and the review skills will produce more findings than are worth a test. Ranking them by reachability across our boundaries (host, read-key holder, local, supply chain) is how the plan stays focused |
| **"Actions Speak Louder Than Tokens: An Insider Threat Model for Frontier AI Agents"** | A threat model that treats the agent as the insider. Five CERT dimensions adapted (motivation → optimisation objectives; opportunity → tool access and permissions; capability → model capabilities; predisposition → alignment profile; organisational factors → harness engineering). Four autonomy levels (L1 operator, L2 collaborator, L3 supervisor, L4 auditor). **Six** threat categories (credential compromise, supply-chain sabotage, data exfiltration, infrastructure sabotage, deception and evasion, containment and third-party impact). **27** STRIDE threats, each placed in a frequency × complexity quadrant (diffuse drift 10, opportunistic 8, targeted 9; the high-frequency high-complexity quadrant is empty). Detection with existing tooling: SIEM, UEBA, DLP, network, endpoint, deception (honey tokens, canary files). Monitor the *shape* of reasoning, not its content | `ai-insider-threat.matt-adams.co.uk`, source `github.com/mrwadams/ai-insider-threat`, CC BY 4.0, v1.0 dated April 2026 with sources into August 2026. Generated with STRIDE GPT. Search snippets still say 23 threats and five categories; the page lists 27 and six | **Adopt as an overlay.** Several of its threats are sgit rows already, seen from the other side (table below). Adding actor **A9, the agent holding the key** to §3 of the threat model, and a column mapping its 27 threats to our controls, is a small, concrete piece of work with a published method behind it |

### 1.1 First pass: the 27 insider threats against sgit's register

Done from the published list; to be confirmed against code in the review.

| Insider threat | sgit today | Register |
|---|---|---|
| S1 harvests keys and tokens | `vault_key`, `.pem`, the token and the credential store are on disk under `.sg_vault/local` (0600, directory 0755); keys appear in argv and `vault info` | TM-R14, TM-R15, TM-F05, TM-F16 |
| S2 forges commit author metadata | commits are signed by the clone's key, but any read-key holder can mint a key that verifies | **TM-R01**, TM-R17 |
| S5 replays a long-lived machine credential elsewhere | the write key is a bearer secret with no binding to a client, machine or time | TM-R13 |
| T1 subtle backdoor in code | out of sgit's scope as a tool; in scope for *this repository*, which agents write 61 % of (coding.sgit.ai) | review process, not register |
| T2 modifies CI/CD | three workflows, release actions SHA-pinned, publish from main only; the shipped workflow template pins nothing | TM-R21, SP-10 |
| R1 deletes logs and history | `history reflog` is local-only; the host keeps no plaintext log; a write-key holder can rewrite history, which clones detect as a rewind | TM-R13, rewind guard (TM-F12, F19, F23) |
| R3 changes code through paths that bypass signing | unsigned commits are refused under `signatures-required`, but only by sgit clients | TM-R26, TM-F10 |
| R4 suppresses client-side reporting | sgit emits no telemetry, so there is nothing to suppress; the host sees sizes and timing only | TM-R08 |
| I1, I5 exfiltration, data lands outside the deployment | `SGIT_DEFAULT_BASE_URL` once redirected a whole vault, token included; now pinned per vault | TM-F15, TM-F22, TM-R10 (`http://` allowed) |
| I4 secrets through reasoning logs | an agent that reads `vault_key` and prints it in its own transcript; nothing in sgit can prevent that, the skill rule can discourage it | new: skill rule (plan step 5) |
| D4 corrupts or deletes repository content | the write key can delete everything on the host; clones and backups recover | TM-R13 |
| E2 uses harvested credentials beyond its privilege | one write key per vault, all-or-nothing among holders; no per-writer authorisation | the "gap the note misses" in `10/08/review__git-to-sgit-security-mapping.md` |
| E5 reaches live systems from an environment believed isolated | unit and security tests are hermetic by construction (`tests/unit/conftest.py` fails any non-loopback connection) | test harness, not register |

Thirteen of 27 land on an existing row or mechanism after one reading. The rest (container
escape, `/proc` reads, ptrace, cloud resource churn, flooding internal services, account
creation) are host-and-harness threats that sgit cannot see; they belong in the deployment's
model, which is where the paper puts them.

## 2. The classical tools, and why they are not first

| Tool | What it is | Fit |
|---|---|---|
| **OWASP pytm** | Threat model as a Python file: elements, boundaries, dataflows; threat rules are Python conditions evaluated with `eval` (the README warns about the threat file's permissions); outputs a dot DFD, a PlantUML sequence diagram, a Markdown report. OWASP Production project | The right *shape* for a repository that already keeps everything as typed data, and the model file would sit naturally beside `review/intent/`. Not first: its threat library is web-app shaped; our value is in the register we already have. Worth a model file once the DFD is drawn, so the DFD is data and diffs |
| **Threagile** | Declarative YAML architecture model with automated risk rules; CLI, Docker, REST; produces risk report and diagrams | Same comment; YAML rather than Python. Its risk rules are infrastructure-shaped (containers, networks); few apply to a CLI and a storage API |
| **OWASP Threat Dragon** | DFD editor (web or desktop) with rule-assisted threat generation | A drawing tool. The house method keeps models as graph data, not drawings; use only if someone wants a picture for a talk |
| **Microsoft TMT, IriusRisk, ThreatModeler** | Desktop or commercial | Not for an open, agent-driven, data-first repository |

## 3. The house method, and where each tool plugs in

From `threat-modeling.sgit.ai/practice/`: bottom-up and fractal (file → method → class → module
→ path → endpoint → attack surface); one `.security.json` per source file in a parallel tree
with `attack_surface`, `vulnerabilities` (id, severity, attack vector, impact, status,
mitigation, **`risk_decision`** with owner and rationale), `secrets_exposure`, `dependencies`
with `trust_boundary_crossings`, `redundant_code`; STRIDE tables that keep `NOT MITIGATED`
rows; two modes never averaged; the method is always published, findings only once closed or
harmless by design.

| House artefact | Produced by | Note |
|---|---|---|
| `.security.json` per file (the slice only) | this agent, from the Trail of Bits dossier plus the review findings; every claim with a line | the dossier's "assumption, nothing found" rows become `attack_surface` and `trust_boundary_crossings` entries |
| STRIDE table for the slice | STRIDE GPT JSON (machine) and the `stride-threat-modelling` skill (this agent), reconciled | two independent passes; disagreements are published as such |
| Join: STRIDE threat ↔ TM-R/TM-F row ↔ test | this agent; a JSON table under `review/` | this is the TM-Bench "completeness" measurement, with our register as ground truth |
| Ranked findings | `threat-led-triage` over Semgrep, Bandit, pip-audit and skill output, with the STRIDE GPT model | explicit "could not determine" kept |
| Actor A9 and the insider overlay | the 27-threat table above, confirmed | an addition to §3 and §6 of the threat model, with `Known_Gaps` tests where a gap is proven |
| Disclosure | method now; findings when closed | the sgit.ai security page still says the internal review "is being prepared", and the 0.21.0 register is in this repository; the case study can close that loop |

## 4. Sources checked

- `github.com/mrwadams/stride-gpt` (README, changelog, PRs #205, #218, #231); `pypi.org/project/stride-gpt`
- `github.com/mrwadams/mcp-stride-gpt` (README)
- `tmbench.com` (home, methodology); shostack.org AppSec roundup March 2025 (TM-Bench introduction)
- `github.com/mrwadams/threat-led-triage` (README, `test/`)
- `ai-insider-threat.matt-adams.co.uk`; `github.com/mrwadams/ai-insider-threat`; `github.com/mrwadams`; matt-adams.co.uk/cv (talks at Securing Financial Services Summit 2026, Securing the Law Firm 2026)
- SE Radio 648 (Dec 2024), "Matthew Adams on AI Threat Modeling and Stride GPT"
- `devguide.owasp.org` pytm page; `pypi.org/project/pytm`; Threagile and Threat Dragon project pages
- `threat-modeling.sgit.ai` (index, practice, security-json pages)
