# Post-Patch Validation

The supplied checks found 1 failure to investigate and repair.

Declared evidence level: runtime (execution of the reported behavior and its safety assertions).

Assessment: complete. Human review is required.

## Findings

- `06-behavior-readable-index-parses-identically` (behavior): Behavior that should remain unchanged differs or fails after the patch.

## Validation gaps

All required checks produced usable evidence.

## Evidence

Finding: TM-F29: Index entries this build could not read were erased from the server by its next index write (push, tag create/delete, vault format, move, pull refresh), and a deleted tag whose tombstone it could not read came back; introduced by TM-F25's skip in f624d3b, fixed in d970599 by carrying unreadable entries as canonical JSON (carried_tags) and writing them back inside tags

Base commit: `f624d3b8e8f3b91504db464c3e823f044945def4`

Patch SHA-256: `4611ce4e36ca1f7452fbd952801252c78ef8179d39ee8c08cd1882d51fa5d2dc`

Submodules: none

Forwarded environment: none

The table records whether each run matched its expected result. For exploits and
variants, a matched baseline means the safety assertion failed as expected.
Observations require the controls and comparisons described in the findings and gaps.

| Check | Kind | Base expectation | Patched expectation | Output comparison |
|---|---|---|---|---|
| `01-control-readable-tag-survives-push` | control | matched | matched | not compared |
| `02-exploit-push-erases-unreadable-entries` | exploit | matched | matched | not compared |
| `03-variant-unreadable-tombstone-resurrects-tag` | variant | matched | matched | not compared |
| `04-variant-tag-create-delete-path` | variant | matched | matched | not compared |
| `05-variant-pull-refresh-path` | variant | matched | matched | not compared |
| `06-behavior-readable-index-parses-identically` | behavior | matched | matched | changed |
| `07-regression-tags-still-work` | regression | matched | matched | not compared |
| `08-security-tm-r06-far-future-entries` | security | matched | matched | not compared |
| `09-suite-security-tests` | suite | not run | matched | not compared |

## Next steps

Return findings to the patch author and investigate validation gaps.
After revising the patch or checks, pin the new inputs and save a fresh run.

Review the saved assertions and omitted paths before accepting the patch. A complete
assessment means the supplied checks produced usable evidence.
It does not establish that coverage is exhaustive.
