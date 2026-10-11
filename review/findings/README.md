# review/findings — what each tool said, as data

One file per tool or skill, same record shape, written by the sgit-ai CLI agent during the
round-1 security review (2026-10-11). `raw/` holds the tools' own output untouched (SARIF,
JSON, the supply-chain report). Everything else is a claim to verify: step 4 (`fp-check`,
`threat-led-triage`) decides what becomes a `VULN` with a test, a `Known_Gaps` row, or a
`CLEARED`.

## Record shape

| Field | Meaning |
|---|---|
| `id` | `<TOOL>-<nnn>`, stable within this round |
| `tool` | which skill or scanner produced the claim (`sharp-edges`, `insecure-defaults`, `sentry-security-review`, `sentry-secret-serialization`, `semgrep`, `bandit`, `pip-audit`, `supply-chain-risk-auditor`, `gha-security-review`, `differential-review`, `post-patch-validation`, `stride`) |
| `group` | the slice group (`crypto`, `local`, `host`, `verify`, `supply-chain`) |
| `file`, `line` | where, in `sgit_ai/` (tests are evidence, never targets) |
| `title` | one line |
| `category` | the tool's own category (sharp-edge class, insecure-default corpus, OWASP topic, STRIDE letter) |
| `confidence` | `HIGH` (traced from a real input to the effect), `MEDIUM` (pattern present, path unconfirmed), `LOW` (theoretical) |
| `status` | `VULN` (reproduced), `VERIFY` (needs the step-4 check), `CLEARED` (false positive, with the reason), `KNOWN` (already a register row, with its id) |
| `evidence` | lines read, calls traced, reproduction if any |
| `register` | existing TM rows this touches |
| `proposed` | fix and test, when there is one |

Counts per tool, true and false positives, are tallied in the case study
(`team/humans/dinis_cruz/claude-code-web/10/11/case-study/`).
