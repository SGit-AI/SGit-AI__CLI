# Agent skills for security review — what exists, what it would do here

**From:** the sgit-ai CLI agent · **Date:** 2026-10-11 · **For:** `skills.sgit.ai` (Documents), then
the case study once used.

**Method.** Each entry was checked at its source (the repository README or SKILL.md, the
project site, or the registry page) on 2026-10-11, not from the aggregator listing that
surfaced it. Where a claim could not be confirmed it says so. "On this code" means the sgit-ai
CLI: 469 Python files, Type_Safe throughout, two runtime dependencies (`osbot-utils`,
`cryptography`), AES-256-GCM / PBKDF2 / HKDF / ECDSA P-256 in `sgit_ai/crypto/`, a host
boundary in `sgit_ai/network/api/`, a local boundary in `sgit_ai/storage/`.

**The ranking rule.** A skill earns a place on this review if it does one of three things the
existing work does not already do: (a) brings a *method* (not a pattern list) that reaches
crypto, trust boundaries and file handling; (b) brings a *tool* with deterministic output
(SARIF, JSON) we can join to the threat model; (c) vets the other skills. Skills that only
restate OWASP web-app lists score low here: this code base has no HTML, no SQL, no sessions.

## 1. The catalogue

### 1.1 From the screenshot

| # | Skill | Source, licence | What it is | On this code | Verdict |
|---|---|---|---|---|---|
| S1 | **security-review** | `getsentry/skills`, `skills/security-review/SKILL.md`, Apache-2.0 (references credit the OWASP Cheat Sheet Series, CC BY-SA 4.0) | A review *method*: research the whole code base first, trace data flow, then report only high-confidence findings (`VULN-###`) with a separate "needs verification" list (`VERIFY-###`). Do-not-flag rules for tests, dead code, server-controlled config. Loads reference guides per topic (17: injection, XSS, authorization, authentication, **cryptography**, deserialization, **file security**, SSRF, CSRF, data protection, API, business logic, modern threats, misconfiguration, error handling, **supply chain**, **logging**) and per language (Python among five) | The cryptography, file-security, supply-chain and logging guides fit. The confidence discipline matches the house rule that a finding needs a reproducing test. Timon Weber's comparison of five Claude Code security skills picked this one as the only one worth installing | **Use.** Primary code-review skill for the slice |
| S2 | **Cisco software.security** → Project CodeGuard | `cosai-oasis/project-codeguard` (was `project-codeguard/rules`), CC BY 4.0; Tessl registry lists `cisco/software-security` at 82 % quality | Secure-by-default *rules* for AI coding agents, eight categories: cryptography, input validation, authentication, authorization, supply chain, cloud, platform, data protection. Ships a `.claude-plugin` and a `skills/` folder; translators to Cursor, Copilot, Windsurf | The cryptography and supply-chain rules are a checklist to read the slice against (safe algorithms, key management, dependency pinning). It is guidance for *writing* code; it has no review loop, no output format, no verification step | **Reference only.** Read its crypto and supply-chain rules once; cite them in findings where they apply. Do not install as a plugin for this review |
| S3 | **"Anthropic Cybersecurity Skills"** | `mukul975/Anthropic-Cybersecurity-Skills`, Apache-2.0, community project by Mahipal Jangra; README: "Not affiliated with Anthropic PBC" | About 817 skills in 34 domains mapped to MITRE ATT&CK v19.1, NIST CSF 2.0, ATLAS, D3FEND, NIST AI RMF, F3. SKILL.md with When to Use / Prerequisites / Workflow / Verification | No threat-modeling or secure-code-review domain. Cryptography (16 skills) is TLS, Ed25519, PQ migration, key management at the operations level, not code review. Much of it is offensive and dual-use (C2, exploitation). The review queue is self-described as months long | **Skip.** The name misleads; the content is a SOC and red-team library, not a code-review method |
| S4 | **audit-website** (squirrelscan) | `squirrelscan/skills`; the `squirrel` CLI from squirrelscan.com, installed by `curl \| sh` | Site audit: SEO, performance, accessibility, security headers, mixed content, leaked-secret patterns (96). Gen Agent Trust Hub rated the skill **Fail / high risk** for the pipe-to-shell install and agent-run fixes | Nothing to audit in a CLI. Possible later use on the published `*.sgit.ai` sites and on `sgit vault serve` / published static vaults, with the binary installed by hand and the agent never running its fixes | **Skip for the CLI.** Park for the website estate |
| S5 | **Varlock** | `wrsmith108/varlock-claude-skill` wrapping `dmno-dev/varlock` (varlock.dev) | A `.env.schema` with sensitivity flags; the skill's rules are "never echo environment variables, never read `.env` directly, validate with masked output". Thin: no support files in the skill repo | The *rule* is the point, and it is already a sgit concern: TM-R14 (keys in argv and logs, re-ranked High on 10/09 because agents' command lines are read by many tools), TM-R09 (`.env` tracked-wins), the always-ignored set in `Vault__Ignore`. We do not use `.env` at runtime | **Skip the skill, keep the rule.** Fold "never print a vault key, token or read key" into the sgit skill (`library/skills/sg-send-cli__SKILL.md`) as a stated rule; see plan step 5 |
| S6 | **OWASP Agentic Skills Top 10 (AST10)** | `OWASP/www-project-agentic-skills-top-10`, incubator, "1.0-2026", leads Ken Huang and Fabio Cerullo, CC BY-SA 4.0 | Ten risks for the skill layer (between model and tools): AST01 malicious skills, AST02 supply-chain compromise (both Critical), AST03 over-privileged, AST04 insecure metadata, AST05 untrusted external instructions, AST06 weak isolation (High), AST07 update drift, AST08 poor scanning, AST09 no governance, AST10 cross-platform reuse (Medium). A pre-install checklist | Not a review skill; it is the rubric for *installing* the others into a repository whose whole point is key custody. Every skill on this list is a third-party instruction file that will run with read access to the code and, in a careless session, to a vault key | **Use as the gate.** Plan step 0 applies its checklist to each installed skill and records the answers |
| S7 | **Behavioral verification** (canary run, signed manifest) | AST10 checklist items; tools: `cisco-ai-defense/skill-scanner` (Apache-2.0, PyPI `cisco-ai-skill-scanner`, SARIF, YARA + dataflow + optional LLM pass, pre-commit hook and reusable workflow), `getsentry/skills` `skill-scanner` skill, `skillsign` (Ed25519 over a skill folder), SkillLedger (content-addressed, SLSA L3) | The checklist asks for a valid Ed25519 signature with a content hash matching the manifest, and a run in an isolated canary environment with a report that observed behaviour matches declared behaviour | None of the skills above ship a signed manifest, so the signature check fails for all of them today (the `skills.sgit.ai` catalogue already shows version and permissions fields undeclared on our own eight). What we *can* do: scan each SKILL.md with the Cisco scanner, pin to a commit SHA, read it, and run it first in this cloud session (which has no vault key) before any session that holds one | **Use the scanner, note the gap.** The gap (no signatures anywhere in the ecosystem) is itself a `skills.sgit.ai` finding |

### 1.2 Not in the screenshot, and stronger for this code

| # | Skill | Source, licence | What it is | On this code | Verdict |
|---|---|---|---|---|---|
| S8 | **Trail of Bits skills** | `trailofbits/skills`, CC BY-SA 4.0, plugin marketplace (`/plugin marketplace add trailofbits/skills`) | About 49 skills in named plugins. The ones that matter here: **audit-context-building** (a dossier per function: invariants, assumptions with the line that establishes each or "nothing found", callees; explicitly *no* verdicts; runs each function in its own subagent), **differential-review** (security review of a diff with git history), **insecure-defaults** (parallel hunt for fail-open defaults with a verifier per file), **sharp-edges** (error-prone APIs; AES-GCM nonce handling is their own example), **variant-analysis**, **fp-check** (gate review of each finding), **static-analysis** (CodeQL, Semgrep, SARIF), **semgrep-rule-creator**, **supply-chain-risk-auditor** (PyPI advisories, abandoned upstreams), **spec-to-code-compliance**, **property-based-testing** (Hypothesis), **mutation-testing** (surviving mutants), **post-patch-validation** (missed variants after a fix), **agentic-actions-auditor** (GitHub Actions used by agents). `constant-time-analysis` targets compiled code, so it is marginal for pure Python | This is the only set written by people who audit cryptographic code for a living. The context dossier is the data asset the code-review-graphs brief wants at the "explanation layer", written by an agent, with a line cited for every claim. `post-patch-validation` is tailor-made for 0.21.0, where two of the fixes introduced regressions (TM-F29, TM-F30). `supply-chain-risk-auditor` is TM-R21 | **Use.** The backbone of the review: context, then insecure-defaults and sharp-edges on `crypto/` and `storage/`, differential-review on 0.20.0→0.21.0, fp-check on everything, post-patch-validation on the 0.21 fixes |
| S9 | **Anthropic `/security-review`** and the `claude-code-security-review` GitHub Action | `anthropics/claude-code-security-review`, MIT; the slash command is built into Claude Code (present in this session) | Reviews pending changes (command) or a PR diff (Action). Categories: injection, auth, data exposure, cryptography (weak algorithms, key management, randomness), input validation, business logic (race, TOCTOU), configuration, supply chain, code execution, XSS. A second model pass filters false positives (excludes DoS, rate limiting, resource exhaustion, generic validation, open redirects). Prompt is customisable by copying `.claude/commands/security-review.md`. **Not hardened against prompt injection**: the README says review trusted PRs only | Cheap, already here, diff-scoped. The exclusions matter: three of our accepted rows are DoS-shaped (TM-R18 tree shapes, TM-R35 `--grep`), which this tool would not report by design. Useful as the PR gate once a baseline exists; the Action needs `pull-requests: write` and an API key secret | **Use on diffs**, not as the whole-slice review. Candidate for the CI job later, after the Bandit / pip-audit baseline (TM-R21), with the fork-approval setting on |
| S10 | **find-bugs**, **secret-serialization**, **gha-security-review** | `getsentry/skills`, Apache-2.0 | `find-bugs`: bugs and security issues in local branch changes. `secret-serialization`: secrets leaking through serialization, logs or spans. `gha-security-review`: GitHub Actions workflows for exploitation risk | `secret-serialization` is the exact shape of TM-R14 and TM-F05/F16 (keys written, printed, logged): `sgit vault info` prints the full key; `Vault__Secret_File`, `Secrets__Store`, `CLI__Debug_Log` are its targets. `gha-security-review` covers the three CI workflows and the SP-10 "template pins nothing" finding | **Use** `secret-serialization` on `crypto/`, `secrets/`, `cli/CLI__Debug_Log.py`, `cli/CLI__Vault.py`; `gha-security-review` on `.github/workflows/`. `find-bugs` overlaps S9; skip |
| S11 | **Classical scanners**: Semgrep (`p/python`, `python.cryptography.*` rules), Bandit, pip-audit, CodeQL | OSS; Trail of Bits `semgrep-rules` adds crypto rules | Deterministic pattern scanners with SARIF output | TM-R21 already asks for Bandit and pip-audit in the security CI job with a baseline; KI-SEC-06 counted about 23 Bandit mediums. Semgrep's crypto rules (insecure hash, insecure cipher, PKCS#1 v1.5) are the right first pass over `crypto/`. Their SARIF is what `threat-led-triage` consumes | **Use**, and keep: these become the CI baseline the threat model has wanted since 10/08 |

## 2. What the vetting gate looks like (AST10 applied)

For every skill the plan installs, record this table in the case study before the first run:

| Check (AST10 checklist) | Evidence we can produce today |
|---|---|
| Provenance: author identity, content hash, signature | Repository and commit SHA pinned; `sha256` of each SKILL.md recorded; **no signature exists** for any of them |
| Scan status | `skill-scanner scan-all <dir> --format sarif` output kept under the case study; HIGH fails the install |
| Permissions: files, tools, network | Read from the frontmatter (`allowed-tools`); Sentry's security-review declares `Read, Grep, Glob, Bash, Task`. Any skill that fetches remote instructions at run time fails AST05 unless pinned |
| Identity files | Does it ask to write `CLAUDE.md`, `AGENTS.md`, memory? Sentry's `agents-md` does by design; the review skills must not |
| External content | `mcp-stride-gpt` hosted at `mcp.stridegpt.ai` sends the app description off-machine; use the skill copy or self-host on loopback (see the threat-modeling doc) |
| Dependencies pinned | `stride-gpt` from PyPI pinned by version and hash; the scanner itself pinned |
| Risk tier matches scope | A review skill that only reads is Low; anything that writes fixes is Medium and runs with `--dry-run` or not at all |
| Canary run | First run in a session with no vault key, no `.env`, no token on disk (this cloud environment qualifies: `find / -name .sg_vault` is empty) |

The honest finding for `skills.sgit.ai`: **the ecosystem's best security-review skills cannot pass
their own community's checklist**, because nobody signs skills yet. The `skills.sgit.ai` thesis
(skills as packages with version, permissions and provenance) is exactly the missing piece, and
this review is a worked example of the gap.

## 3. Two ideas worth taking, not installing

- **Confidence tiers with a "needs verification" list** (S1). Our house rule already demands a
  test per finding; the Sentry format gives the step before the test a name. Adopt the
  `VULN-###` / `VERIFY-###` split in the review output, then promote a VERIFY only when its test
  exists.
- **Context before verdicts** (S8 audit-context-building). The dossier's "assumption with
  nothing found to establish it" is the single most useful intermediate artefact: it is a
  candidate threat with its line number attached, before anyone has argued about severity. That
  is the `.security.json` row's `attack_surface` and `trust_boundary_crossings` fields, written
  by an agent with a citation, which is what the code-review-graphs brief allows at the
  explanation layer.

## 4. Sources checked

- `github.com/getsentry/skills` (README skill list; `skills/security-review/SKILL.md`)
- `github.com/trailofbits/skills` (README, plugin list; `audit-context-building` SKILL.md)
- `github.com/anthropics/claude-code-security-review` (README)
- `github.com/cosai-oasis/project-codeguard`, `github.com/project-codeguard/rules`; Cisco and OASIS announcements (Oct 2025, Feb 2026)
- `github.com/mukul975/Anthropic-Cybersecurity-Skills` (README)
- `owasp.org/www-project-agentic-skills-top-10/` (project page, README, checklist)
- `github.com/cisco-ai-defense/skill-scanner`
- `smithery.ai/skills/andymsun/audit-website`, `docs.squirrelscan.com`, Gen Agent Trust Hub rating
- `github.com/wrsmith108/varlock-claude-skill`, `varlock.dev`
- timonweb.com, "I checked 5 security skills for Claude Code, only one is worth installing"
