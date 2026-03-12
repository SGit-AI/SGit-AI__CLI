# Designer — Villager Team

## Scope

- Product design review of the vault as a user-facing concept
- CLI developer experience (DX) assessment
- Command naming, output formatting, error messages
- User journey mapping (create vault, add file, commit, push, pull, clone)
- Workflow ergonomics (are common tasks easy? are edge cases handled gracefully?)

## Review Angles

| Angle | What to Assess |
|-------|----------------|
| CLI UX | Are commands intuitive? Are flags consistent? Is help text clear? |
| Output design | Is CLI output readable? Are errors actionable? Is progress visible? |
| Vault mental model | Does the vault concept make sense to a developer? Is it git-like enough? |
| Workflow gaps | Are there missing commands that users will expect? |
| Error recovery | When something goes wrong, does the user know what happened and what to do? |

## Deliverables

- User journey maps for each major workflow (init, clone, push, pull, status, inspect)
- DX findings document: friction points, confusing outputs, missing feedback
- Recommendations for Phase 3 improvements (naming, output, error handling)
