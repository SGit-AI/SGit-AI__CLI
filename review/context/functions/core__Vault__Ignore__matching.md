# Pattern matching in sgit_ai/core/Vault__Ignore.py

All pure. `self.patterns` is a list of `dict(pattern, negate, dir_only)` from `_parse_line`. These decide only the `.gitignore` layer; structural and always-ignored names are decided before them (see `should_ignore_file`).

## `_matches` (L297-L309)
Iterates every pattern in file order; `dir_only` patterns skipped for files (L304-L305); on a match sets `ignored = not negate` (L308) — **last matching pattern wins**, as in git. No short-circuit.

## `_find_matching_pattern` (L285-L295)
Same walk, returns the text of the last positive match (`None` after a negation, L294), `''` if none. Used only by `explain`.

## `_path_matches` (L311-L315)
A pattern with a `/` anywhere except trailing → `_match_anchored`; otherwise `_match_basename`.

## `_match_basename` (L317-L323)
`fnmatch(basename, pattern) or fnmatch(rel_path, pattern)`. Note `fnmatch` `*` matches `/` too (it is not path-aware), so `*.log` also matches `a/b/c.log` via the second call — consistent with git here, but `a*b` would match `a/x/b`, which git's would not. `fnmatch.fnmatch` is case-insensitive on Windows (`normcase`) and case-sensitive on POSIX.

## `_match_anchored` (L325-L330)
`**` → `_match_doublestar`; else `fnmatch(rel_path, pattern)` — again `*` crosses `/`, so `docs/*.md` matches `docs/a/b.md` (git would not). Scope note, not a boundary issue: these rules only exclude.

## `_match_doublestar` (L332-L362)
`**` alone → everything (L333-L334). `**/rest` → `rest` against the whole path or any suffix starting at a component (L335-L344). `prefix/**` → path equals prefix or starts with `prefix/` (L345-L349). `before**after` → prefix test then `after` against any component-suffix of the remainder (L350-L362). A pattern with two `**` is split on the first only (L350); the second stays literal in `after` and is matched by `fnmatch` where `*` is already greedy.

## `_parse_line` (L364-L381)
Strips whitespace (so a trailing space in a pattern is lost — git treats a trailing unescaped space the same way), skips blank and `#` lines, `!` → negate, trailing `/` → dir_only, leading `/` dropped (so a leading-slash anchored pattern becomes a basename-or-full match via `_path_matches`, which is looser than git's root-anchoring when the remainder has no `/`). Escapes (`\#`, `\!`) are not handled: `\#foo` is kept literally including the backslash. Returns `None` or a dict.

## `_dir_matches_ignore_rule` (L118-L124), `_is_env_secret` (L183-L186)
Covered in `should_ignore_dir` / `should_ignore_file`.

**Callers:** `_matches` from `should_ignore_file` L137, `_dir_matches_ignore_rule` L124, `explain` L243, `_explain_dir_rule` L273. Tests: `tests/unit/sync/test_Vault__Ignore.py::Test_Vault__Ignore__Gitignore_Parsing`.

**Open Questions:** none that bear on the boundary; the `fnmatch`-vs-git semantic gaps above change only which of the user's own files are excluded.
