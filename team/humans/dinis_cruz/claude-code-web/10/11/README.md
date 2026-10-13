# Security review with agent skills — research pack and plan

**From:** the sgit-ai CLI agent · **Date:** 2026-10-11 · **Branch:** `claude/youthful-feynman-bpunv5`

**Ask (Dinis, 11 Oct).** Review the best agent skills and threat-modeling tools we could use on
this code base, including the ones from the two screenshots (the "Top AI Agent Skills for
Security Review" list, and Matt Adams' STRIDE GPT / TM-Bench / insider-threat work). Write them
up as research docs for `skills.sgit.ai` and `threat-modeling.sgit.ai` first, as a case study
later once used. Map the security reviews already done here. Then plan which tools to use for
the next security review, and start the review graphs and data assets (the
`secrets.sgit.ai/review/` approach), focused, not everywhere.

## The pack

| File | What it is | Goes to |
|---|---|---|
| `research__security-review-skills.md` | Eleven skills and tools for agent-driven security review, each checked at source: who maintains it, licence, install, what it would do on *this* code, verdict. Includes the OWASP Agentic Skills Top 10 vetting rubric and two skill scanners | `skills.sgit.ai` (Documents) |
| `research__threat-modeling-tools.md` | Matt Adams' stack (STRIDE GPT, its MCP server, TM-Bench, threat-led-triage, "Actions Speak Louder Than Tokens"), the classical tools (pytm, Threagile, Threat Dragon), and how each fits the house method (`.security.json`, STRIDE tables, disclosure rule) | `threat-modeling.sgit.ai` (Documents) |
| `map__security-work-already-done.md` | Every threat model, review, adversarial test and design note this repo already holds, with ids, counts and what each does not cover | both sites, and the case study |
| `plan__security-review-with-skills.md` | The plan: scope (one slice, where the zero-knowledge guarantee lives), the tools chosen and why, the order, the data assets produced at each step (`review/` graphs, dossier, STRIDE model, join tables, `.security.json`), acceptance, and what the case study will measure | this repo; executes next |

## Three corrections to the screenshots, found while checking sources

1. **"Anthropic Cybersecurity Skills" is not Anthropic's.** It is `mukul975/Anthropic-Cybersecurity-Skills`,
   a community project by Mahipal Jangra whose README says "Not affiliated with Anthropic PBC".
   It has no threat-modeling or secure-code-review domain. Not for this review.
2. **"Cisco Software Security" is Project CodeGuard**, donated by Cisco to the Coalition for Secure
   AI in February 2026 (`cosai-oasis/project-codeguard`). It is secure-by-default guidance for
   code *generation*; its review value is as a rule list, not a review workflow.
3. **TM-Bench scores four dimensions**, not three: STRIDE coverage and accuracy, threat
   completeness, technical validity (each 30 %), and JSON structure compliance (10 %). Its judge
   is Claude Sonnet 4.6. "Actions Speak Louder Than Tokens" now lists 27 STRIDE threats in six
   categories (the sixth, containment and third-party impact, was added after the July 2026
   disclosures); search snippets still say 23 and five.

## What happened next (same day)

Dinis accepted the plan as written (the slice, `review/` at the repository root, no need to tell
Matt beforehand). The review ran through its six steps; the record is:

| Where | What |
|---|---|
| `case-study/README.md` | the case study: what each tool found, with counts; five defects fixed with tests; what the tools got wrong; cost |
| `case-study/00__vetting.md` | the skills vetted, pinned and scanned before use |
| `review/` (repository root) | the data: derived graph, intent, 270 function dossiers, the STRIDE model joined to the register, 104 finding records, the ranking, 41 per-file security records |
| `team/explorer/appsec/threat-model/v0.21.0__threat-model.md` §6.1 | rows TM-F32 to TM-F36 |
| `tests/security/test_Security__Fixed__PKI_Paths.py`, `test_Security__Fixed__Lying_Host.py`, `test_Security__Fixed__Index_Overwrite.py` | the proofs |

## Published (13 Oct)

`research__threat-modeling-tools.md`, `map__security-work-already-done.md` and `case-study/README.md`
are on the `threat-modeling.sgit.ai` repository (`SGit-AI__Website__Threat-Modeling`, branch
`claude/youthful-feynman-bpunv5`, release `site v0.1.1`) as `briefs/07__`, `08__` and `10__`, each
with a provenance paragraph naming the source commit (`fb63254`). The case study copy is redacted
under that site's disclosure rule: the two paragraphs naming open findings (AC-L-001 and the head
of the VERIFY queue) are replaced in place by a dated held-count note; the full text stays here.
The site deploys on a push to its `dev` branch, so that step waits for Dinis. Still to publish:
`research__security-review-skills.md` and `case-study/00__vetting.md` to `skills.sgit.ai`, whose
repository was not in this session's scope.
