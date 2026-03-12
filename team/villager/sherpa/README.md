# Sherpa — Villager Team

## Scope

- Guide the team through the Explorer-to-Villager transition methodology
- Ensure each phase completes fully before the next begins
- Track acceptance criteria across all phases
- Cross-role coordination (Architect findings feed Dev work, QA validates, AppSec stress-tests)
- Business alignment: does the architecture support billable units and the branch model?

## Phase Tracking

| Phase | Focus | Gate to Next Phase |
|-------|-------|--------------------|
| Phase 1: Architectural Review | Fresh eyes on everything | Findings document complete |
| Phase 2: Test Coverage | Build the safety net | Use-case coverage complete, CI green, zero mocks |
| Phase 3: Refactoring | Improve without changing behaviour | All tests pass, adversarial testing complete |
| Phase 4: Next Wave | Explorer returns | Codebase ready for branch model, unified vault, remotes |

## Acceptance Criteria (from brief)

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Phase 1 architectural review completed (findings document) | Done |
| 2 | Test infrastructure: local send server bootable in CI | Pending |
| 3 | Zero mocks or patches in test suite | 18 violations remain |
| 4 | Coverage reported on every CI run | Pending |
| 5 | All known bugs captured as passing tests | In progress |
| 6 | All known vulnerabilities captured as passing tests | Pending |
| 7 | Adversarial testing exercise completed | Phase 3 |
| 8 | Phase 3 refactoring with zero test regressions | Phase 3 |
| 9 | CLI ready for branch model, unified vault, remotes | Phase 4 |

## Coordination Model

```
Brief (Human)
    ↓
Sherpa (coordinates)
    ├── Architect (reviews, plans)
    ├── AppSec (security audit, adversarial testing)
    ├── Designer (UX/DX review)
    ├── DevOps (test infrastructure, CI)
    ├── Dev (executes plans)
    └── QA (validates everything)
```

## Business Context

The vault structure must support:
- Unified vault format (server-side = clone-side)
- Branch model (auto-branch on clone, PKI per branch)
- Signed commits
- Remotes
- Merge operations
- Nested vaults (vault inside vault)

The Villager team's job is to make the codebase ready for all of this.
