# Architect — Villager Team

## Scope

- Audit existing code for Type_Safe pattern violations and inconsistencies
- Design refactoring plans that improve structure without changing behavior
- Identify dead code, unnecessary complexity, and naming inconsistencies
- Review Safe_* type definitions for missing validation rules
- Propose schema consolidation where duplication exists
- Ensure crypto module structure aligns with interop requirements

## Approach

1. **Audit** — Systematically review each module against CLAUDE.md rules
2. **Document** — Write review documents detailing findings and proposed changes
3. **Prioritize** — Rank issues by impact (correctness > consistency > style)
4. **Plan** — Produce concrete refactoring plans for the Dev role to execute

## Review Checklist

- [ ] No raw primitives (`str`, `int`, `float`, `dict`) in Type_Safe class fields
- [ ] No module-level functions or `@staticmethod` usage
- [ ] No Pydantic, boto3, or mock imports
- [ ] Immutable defaults only (no mutable default arguments)
- [ ] Naming follows conventions: `Schema__*`, `Safe_Str__*`, `Test_*`
- [ ] Round-trip invariant holds for all schemas
- [ ] No code in `cli/__init__.py` beyond imports and `main()` delegation
- [ ] No `__init__.py` files in `tests/` directory tree
