# CLAUDE.md — Villager Team

## Mission

The Villager team focuses on **refactoring and code quality**. While the Explorer team builds new features and capabilities, the Villager team strengthens what already exists — improving structure, consistency, test coverage, and adherence to Type_Safe patterns.

## Team Structure

The Villager team has 7 roles, each bringing a different angle to improving the SG_Send__CLI codebase.

| Role       | Focus                                    |
|------------|------------------------------------------|
| Architect  | Structural review, refactoring plans, pattern consistency |
| Dev        | Execute refactorings, fix Type_Safe violations, improve code organization |
| QA         | Test coverage, edge-case tests, validate refactoring correctness |
| AppSec     | Security audit, vulnerability identification, adversarial testing |
| Designer   | Product/DX review, CLI ergonomics, user journey mapping |
| DevOps     | Test infrastructure, CI integration, coverage reporting |
| Sherpa     | Phase coordination, acceptance criteria tracking, business alignment |

## Methodology

Follows the Explorer-to-Villager transition defined in:
`team/humans/dinis_cruz/briefs/03/12/v0.13.30__brief__code-quality-explorer-villager.md`

```
Phase 1: Architectural Review  →  Fresh eyes, multiple angles, no code changes
Phase 2: Test Coverage          →  Safety net, use-case coverage, zero mocks
Phase 3: Refactoring            →  Improve code, adversarial testing, all tests pass
Phase 4: Next Wave              →  Explorer returns on solid foundation
```

## Priority Order

1. **Understand first** — Multi-angle review (code, architecture, security, design, business)
2. **Test everything second** — Use-case coverage over line coverage, no mocks ever
3. **Refactor with confidence** — Tests catch every behaviour change
4. **Adversarial validation** — AppSec + QA stress-test the safety net

## Working Agreements

- Never change public behavior during a refactoring — only internal structure
- Every refactoring must have tests that pass before and after the change
- One concern per commit — don't mix refactorings with feature work
- Document the "why" for each refactoring in the review document
- All changes must keep CI green
- No new dependencies introduced for refactoring purposes
- No mocks or patches — ever. Use real objects, in-memory servers, temp directories

## Current Work: v0.5.11

### Phase 1: Architectural Review (COMPLETE)
- Deep code audit: `architect/v0.5.11__review__deep-code-audit.md`
- Coverage baseline: `qa/v0.5.11__coverage-baseline.md`
- Pending: AppSec security audit, Designer DX review

### Phase 2: Test Coverage (IN PROGRESS)
- Testing plan: `architect/v0.5.11__plan__phase-one-testing.md`
- Dev execution plan: `dev/v0.5.11__execution-plan.md`
- Pending: DevOps CI integration, test infrastructure

### Phase 3: Refactoring (PLANNED)
- Refactoring plan: `architect/v0.5.11__plan__phase-two-refactoring.md`
- Includes: adversarial testing exercise (AppSec + QA)

### Phase 4: Next Wave (FUTURE)
- Branch model, unified vault structure, remotes, signed commits, merge
- Explorer team takes over on solid foundation

### Key Findings
- **83% code coverage** (430 tests, 28 skipped)
- **94% Type_Safe compliance** (3 files with raw primitives, 2 semantic mismatches)
- **18 mock violations** in 2 CLI test files
- **2 schemas at 0% coverage**
- **API layer at 26-36% coverage**

### Acceptance Criteria (from brief)
1. Phase 1 architectural review completed (findings document) — **Done**
2. Test infrastructure: local send server bootable in CI — Pending
3. Zero mocks or patches in test suite — 18 remain
4. Coverage reported on every CI run — Pending
5. All known bugs captured as passing tests — In progress
6. All known vulnerabilities captured as passing tests — Pending
7. Adversarial testing exercise completed — Phase 3
8. Phase 3 refactoring with zero test regressions — Phase 3
9. CLI ready for branch model, unified vault, remotes — Phase 4
