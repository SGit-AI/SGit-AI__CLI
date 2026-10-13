# review/ — the repository as layered graphs (round 1: the security slice)

Started 2026-10-11 by the sgit-ai CLI agent, per the sgit.ai brief "Code review graphs in the
repository" and the plan in `team/humans/dinis_cruz/claude-code-web/10/11/plan__security-review-with-skills.md`.
Round 1 covers the slice in `slice.json` (45 files: where the zero-knowledge guarantee and the
trust boundaries live). Not a vault, not a service, not a database.

| Folder | Layer | Produced by | Regenerate |
|---|---|---|---|
| `slice.json` | scope, as data | the plan, accepted 11 Oct | by hand (a scope change is a decision) |
| `graph/` | code, bottom-up: files, classes, methods, calls, tests importing each module | `tools/derive.py` (stdlib `ast`; never a model) | `python3 review/tools/derive.py`; `--check` fails when stale or hand-edited |
| `intent/` | the design, top-down: assets, actors, boundaries, mechanisms, each citing its threat-model section | the agent from the threat model, accepted with the plan | by hand; corrections in `BRIEF-CORRECTIONS.md` |
| `context/functions/` | one dossier per function: invariants, assumptions with the line that establishes each or `nothing found`, callees, open questions (Trail of Bits audit-context-building format) | four subagents, 2026-10-11 | by hand (an explanation layer) |
| `stride/` | STRIDE-per-element threats with DREAD, joined to the register; the insider-threat overlay | `agent.json` by the agent with the stride-threat-modelling skill; `join.json` / `coverage.json` by `tools/stride_join.py` | `python3 review/tools/stride_join.py` |
| `findings/` | one file per tool or skill, one record shape; `raw/` holds the tools' own output; `ranked.json` the threat-led-triage order | the agent running each tool; scanners' raw output untouched | per tool |
| `security/` | one `.security.json` per slice file in the house schema (attack surface, vulnerabilities with `risk_decision`, secrets exposure, dependencies with trust-boundary crossings, redundant code) | `tools/security_json.py` from the layers above; no model in the tool | `python3 review/tools/security_json.py` |
| `tools/` | the derivers, the join, the records writer, the pinned skill installer and its lock | | |

What is not here yet, from the brief: `join/` (intent ↔ code coverage as a figure), `changes/`
(one file per commit), `streams/`, `checks/` (house rules as queries), `ui/` (the navigator),
`self/`. Round 1 stopped at the layers a security review needs.

The case study of the tools used, with counts, is in
`team/humans/dinis_cruz/claude-code-web/10/11/case-study/`.
