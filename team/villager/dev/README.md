# Dev — Villager Team

## Scope

- Execute refactorings identified by the Architect
- Fix Type_Safe pattern violations across the codebase
- Eliminate code duplication and simplify complex methods
- Improve internal naming consistency without changing public APIs
- Restructure modules that have grown beyond their original responsibility

## Refactoring Principles

1. **Behavior preservation** — Tests must pass identically before and after every change
2. **Small steps** — One refactoring per commit, easy to review and revert
3. **Test first** — Ensure adequate test coverage exists before refactoring; add tests if missing
4. **No gold-plating** — Only fix what the Architect review identified; resist scope creep

## Execution Order

1. Fix Type_Safe violations (raw primitives, mutable defaults)
2. Fix naming convention violations
3. Remove dead code and unused imports
4. Extract duplicated logic into shared Type_Safe classes
5. Simplify overly complex methods
6. Restructure modules if needed
