# `load_tracked_paths` and `load_tracked_from_vault` in sgit_ai/core/Vault__Ignore.py

## `load_tracked_paths` (L87-L93)

```python
# L88-L93
for path in paths:
    self.tracked_paths.add(path)
    parts = path.split('/')
    for i in range(1, len(parts)):
        self.tracked_dirs.add('/'.join(parts[:i]))
```
Adds each tracked path and all its ancestor prefixes. `paths` are the vault head's flattened keys (vault-authored, A5). A hostile head with a path `.github/workflows/x.yml` makes `.github` tracked (grandfathered) so the checkout writes it — the accepted decision-17 behaviour; a head path under `.git/` or `.sg_vault/` is also added here, but `is_protected` in `should_ignore_*`/checkout refuses it regardless (A2). Pure set mutation; returns `self`.

## `load_tracked_from_vault` (L95-L106)

```python
# L102-L106
from sgit_ai.core.Vault__Head_Paths import Vault__Head_Paths
helper = Vault__Head_Paths(crypto=crypto)
self.load_tracked_paths(helper.paths(directory))
self._emit_github_migration_notice_once(directory)
return self
```
Best-effort: `Vault__Head_Paths.paths` → `flat` (L17-L71) resolves the working branch exactly as status/commit do (`_init_components`, `load_branch_index`, `_resolve_working_branch`, `read_ref`, `load_commit`, `flatten`, scoped or not) and returns `{}` on **any** exception (L70-L71). So "not a vault", "no key", "empty history", *and* "corrupt index/ref/commit" all yield an empty tracked set → plain rule matching → tracked-wins off. The A6 review argument (L30-L40) is that the scan itself fails loudly under the same corruption, so no silent deletion can be committed; `tests/unit/sync/test_Vault__Ignore__Tracked_Wins.py::Test_A6__Fail_Open_Coupling` pins one such case.

Side effect: `_emit_github_migration_notice_once` (L151-L181) — when any tracked path is under `.github/`, writes `.sg_vault/local/notices.json` once via plain `open('w')` (L169; swallowed on any error, L171-L172) and prints the decision-17 notice to stderr. The write is to a fixed name inside `local/`; not through `Vault__Secret_File` (holds no secret).

**Callers:** every vault scan site (list in `should_ignore_file`), `CLI__Vault` L2333 (`vault ignore explain`).

**Open Questions:**
- Every exception in `Vault__Head_Paths.flat` is swallowed, including programming errors; the coupling argument relies on the scan's own path raising first. Which exceptions the scan raises vs. swallows is outside this slice.
