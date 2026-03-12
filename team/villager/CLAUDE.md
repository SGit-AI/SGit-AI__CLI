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
