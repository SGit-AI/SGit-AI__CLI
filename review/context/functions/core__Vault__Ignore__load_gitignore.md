## `load_gitignore` in sgit_ai/core/Vault__Ignore.py (L76-L85)

```python
# L77-L85
gitignore_path = os.path.join(directory, '.gitignore')
if os.path.isfile(gitignore_path):
    with open(gitignore_path, 'r') as f:
        for line in f:
            line = line.rstrip('\n').rstrip('\r')
            parsed = self._parse_line(line)
            if parsed:
                self.patterns.append(parsed)
return self
```

**Purpose:** Load the vault root's `.gitignore` into `self.patterns`. Only the root file; nested `.gitignore`s are not read (git semantics differ — scope, not a bug claim).

**Inputs & Assumptions:**
- `directory` trusted. The `.gitignore` content: user-controlled, **and vault-controlled** — `.gitignore` is ordinary vault content, so a hostile vault author (A5) ships the rules every clone applies on its next scan. Rules can only *exclude* files from commits (or re-include via `!`), never write anything; the structural and `ALWAYS_IGNORED_FILES` rules run before `_matches` and cannot be negated by `!` because `should_ignore_file` returns at L134/L136 before L137 — wait: `!` negation inside `_matches` affects only `.gitignore` patterns; `ALWAYS_IGNORED_FILES` and `_is_env_secret` return True first (L133-L136), so a `!.env` line cannot un-ignore `.env`. `tests/unit/sync/test_Vault__Ignore.py::test_gitignore_negation_includes_specific_dotfile` covers negation of a tracked-by-default dotfile.
- Opened with plain `open()` (text mode, default encoding): follows a symlink (`.gitignore -> /dev/zero` or a FIFO would hang/consume; A6). `isfile` follows too. **nothing found** that routes this read through `read_regular`; the eed8084 grep-test for plain opens covers five action modules, not this file. A `UnicodeDecodeError` on non-UTF-8 content propagates out of every scan.

**Outputs & Effects:** Appends to `self.patterns` (idempotency: calling twice doubles the patterns; callers construct a fresh `Vault__Ignore()` each time). Returns `self` for chaining.

**Cross-Function Dependencies:** Callee `_parse_line` L364-L381. Callers: every scan site (`Vault__Ignore().load_gitignore(directory).load_tracked_from_vault(...)`) plus `CLI__Vault` L2333, `Vault__Branch_Switch` L429, `Vault__Bare` L110. `Vault__Repo_Ignore` L50-L59 is the writer that appends sgit's key-material lines to the same file.

**Open Questions:**
- The plain `open()` of a working-copy file (above).
