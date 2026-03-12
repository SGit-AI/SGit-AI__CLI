# CLAUDE.md — Villager Team

## Mission

The Villager team focuses on **refactoring and code quality**. While the Explorer team builds new features and capabilities, the Villager team strengthens what already exists — improving structure, consistency, test coverage, and adherence to Type_Safe patterns.

## Team Structure

The Villager team has 3 roles, each with specific responsibilities for improving the SG_Send__CLI codebase.

| Role       | Focus                                    |
|------------|------------------------------------------|
| Architect  | Identify structural issues, propose refactoring plans, enforce pattern consistency |
| Dev        | Execute refactorings, fix Type_Safe violations, improve code organization |
| QA         | Expand test coverage, add missing edge-case tests, validate refactoring correctness |

## Priority Order

1. **Pattern compliance first** — Ensure all Type_Safe classes follow CLAUDE.md rules exactly
2. **Test gaps second** — Add missing round-trip, boundary, and validation tests
3. **Structural improvements** — Reduce duplication, improve naming, simplify complex methods

## Working Agreements

- Never change public behavior during a refactoring — only internal structure
- Every refactoring must have tests that pass before and after the change
- One concern per commit — don't mix refactorings with feature work
- Document the "why" for each refactoring in the review document
- All changes must keep CI green
- No new dependencies introduced for refactoring purposes
- No mocks or patches — ever. Use real objects, in-memory servers, temp directories

## Current Work: v0.5.11 Audit

### Phase One: Testing Only (No Code Changes)
- Deep code audit complete: `architect/v0.5.11__review__deep-code-audit.md`
- Testing plan: `architect/v0.5.11__plan__phase-one-testing.md`
- Coverage baseline: `qa/v0.5.11__coverage-baseline.md`
- Dev execution plan: `dev/v0.5.11__execution-plan.md`

### Phase Two: Refactoring Only (No Behavior Changes)
- Refactoring plan: `architect/v0.5.11__plan__phase-two-refactoring.md`

### Key Findings
- **83% code coverage** (430 tests, 28 skipped)
- **94% Type_Safe compliance** (3 files with raw primitives, 2 semantic mismatches)
- **18 mock violations** in 2 CLI test files
- **2 schemas at 0% coverage**
- **API layer at 26-36% coverage**
