# Explorer Review Process — What Happens After You Push

**Read this immediately after `00__index.md`.**

Your work on `claude/sonnet-onboarding-oMP6A` is not merged directly into
`dev`. An Explorer agent (Claude Opus, session `claude/cli-explorer-session-J3WqA`)
reviews every batch of commits, applies fixes, and merges into its own branch
which Dinis then merges to `dev`.

This doc tells you what the Explorer checks and what it consistently has to
fix — so you can avoid those issues before you push.

---

## The review checklist (things the Explorer fixes on every merge)

**1. Multi-paragraph docstrings — the most common issue**

CLAUDE.md says: *"Never write multi-paragraph docstrings or multi-line comment
blocks — one short line max."*

Wrong:
```python
def secure_unlink(self, path: str) -> None:
    """Overwrite a file's content with zero bytes then unlink it.

    Rationale: plain os.unlink only removes the inode reference...
    Residual risk: SSDs with TRIM may reallocate blocks...
    Zero bytes are used (not os.urandom) because...
    """
```

Right:
```python
def secure_unlink(self, path: str) -> None:
    """Zero-overwrite + fsync a file before unlinking to reduce key material recovery window."""
```

The rationale belongs in the AppSec finding doc or the debrief, not the
method docstring.

**2. Bare class instantiation just to call a utility method**

Wrong:
```python
Vault__Storage().chmod_local_file(path)   # creates a whole object to call chmod
```

Right:
```python
try:
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
except OSError:
    pass
```

Only instantiate a class when you need its state. A `chmod` call needs no
`Vault__Storage` state.

**3. Duplicated helpers across layers**

If a utility method already exists in one class, don't write an identical
private method in another class. Call the one that exists, or use the
underlying stdlib call directly. Example: `CLI__Token_Store._chmod_local()`
was identical to `Vault__Storage.chmod_local_file()` — one was removed.

**4. Missing `import stat` when using `stat.S_*` constants**

If you add `os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)` to a file,
make sure `import stat` is at the top. It is not pulled in by `import os`.

**5. Multi-paragraph module docstrings and class docstrings on exceptions**

Same rule as method docstrings. Module-level docstrings → single-line comment.
Exception class docstrings → one sentence.

---

## Brief 21 — use git worktrees, not git stash

**Read `21b__addendum-mutation-ci-architecture.md` before implementing brief 21.**

The brief says to use `git stash / git checkout --` to revert mutations.
That is unsafe in CI. The architectural decision (addendum 21b) replaces it
with `git worktree` isolation — one worktree per mutation, created from HEAD,
discarded after the run. The main checkout is never touched.

Brief 21 scope is updated: you must implement `tests/mutation/mutations.py`
(mutation catalogue) and `tests/mutation/run_mutations.py` (worktree
orchestrator) in addition to the original deliverables.

---

## What the Explorer review log looks like

After each merge the Explorer writes a section in:
`team/humans/dinis_cruz/claude-code-web/05/01/v0.10.30/10__villager-integration-review-log.md`

You can read it to see exactly what was fixed and why on previous merges.
