# CLAUDE.md — Explorer Team

## Team Structure

The Explorer team has 9 roles, each with specific responsibilities for the SGit-AI__CLI project.

| Role        | Focus                                    |
|-------------|------------------------------------------|
| Architect   | Type_Safe patterns, crypto design, API contracts |
| Dev         | Implementation of Safe_* types, schemas, Vault__Crypto |
| QA          | Tests, round-trip validation, interop test vectors |
| DevOps      | CI/CD pipeline, GitHub Actions, PyPI publishing |
| Librarian   | Dependency tracking, osbot-utils version management |
| Historian   | Decision log, session summaries, reality documents |
| Designer    | Visual identity, UX patterns, sgit.ai website design |
| Ambassador  | Ecosystem positioning, messaging, website copy, SG/Vault case study |
| Sherpa      | Squad coordination, sprint planning, cross-role sequencing |

## Squads

### Website Squad (sgit.ai)

Focused on creating the sgit.ai website, leveraging SGraph-AI ecosystem components.

| Role | Responsibility |
|------|---------------|
| Sherpa | Sprint plan, cross-role coordination, MVP scoping |
| Ambassador | Value proposition, ecosystem positioning, website copy |
| Designer | Site structure, visual design, interactive demos |

## Launching Agents

Use the Claude Code `Agent` tool to launch Explorer team roles. Each agent receives its role definition file as context.

| Agent | Role Definition | How to Launch |
|-------|----------------|---------------|
| **Architect** | `team/explorer/architect/ROLE.md` | Launch an Agent with prompt: *"Read your role definition at `team/explorer/architect/ROLE.md` and `CLAUDE.md`. Then: {task}"* |
| **Developer** | `team/explorer/dev/README.md` | Launch an Agent with prompt: *"Read your role definition at `team/explorer/dev/README.md` and `CLAUDE.md`. Then: {task}"* |
| **QA** | `team/explorer/qa/README.md` | Launch an Agent with prompt: *"Read your role definition at `team/explorer/qa/README.md` and `CLAUDE.md`. Then: {task}"* |
| **Librarian** | `team/explorer/librarian/ROLE.md` | Launch an Agent with prompt: *"Read your role definition at `team/explorer/librarian/ROLE.md` and `CLAUDE.md`. Then: {task}"* |

Agents can be launched in parallel for independent tasks. Always include `CLAUDE.md` so the agent knows the project rules.

## Session 1 Priority Order

1. **Pipeline first** — CI/CD must be green before feature work
2. **Crypto second** — Vault__Crypto with interop test vectors
3. **Everything else** — Safe_* types, schemas, sync logic

## Working Agreements

- Every Type_Safe class gets a test class
- Every Safe_* type gets validation edge-case tests
- Every schema gets a round-trip (json → from_json → json) test
- Crypto operations get interop test vectors (known inputs → known outputs)
- No PR merges without green CI
