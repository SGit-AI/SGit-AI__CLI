"""Vault__Pathspec — which paths `sgit commit <pathspec>…` takes (Git's `git commit --only`).

Patterns are relative to the current folder when it is inside the vault (`cd src &&
sgit commit -m x app.py` means src/app.py), else to the vault root; `..` and absolute
paths are allowed while they stay inside the vault. A literal names a file or a whole
folder (`.` is everything under the current folder); `* ? [..]` are globs over the full
vault path where `*` also crosses `/`, as in Git. Matching runs over HEAD's paths and the
working copy's, so a deleted tracked file is matched (its deletion is committed) and,
unlike Git, so is a new file (sgit has no `add`: naming it is how it gets committed).
"""
import fnmatch
import os
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.core.Vault__Errors                   import Vault__Pathspec_Error
from   sgit_ai.safe_types.Safe_Str__Pathspec        import Safe_Str__Pathspec

GLOB_CHARS = set('*?[')


class Vault__Pathspec(Type_Safe):
    patterns : list[Safe_Str__Pathspec]                  # vault-relative, '/' separators; '' = the whole vault
    typed    : list[Safe_Str__Pathspec]                  # as typed, for messages

    def from_args(self, args: list, cwd: str, root: str) -> 'Vault__Pathspec':
        root   = os.path.realpath(root)
        cwd    = os.path.realpath(cwd or root)
        prefix = os.path.relpath(cwd, root) if (cwd + os.sep).startswith(root + os.sep) or cwd == root else ''
        prefix = '' if prefix == '.' else prefix
        for raw in args:
            text = str(raw)
            if os.path.isabs(text):
                full = os.path.normpath(text)
            else:
                full = os.path.normpath(os.path.join(root, prefix, text))
            if full != root and not full.startswith(root + os.sep):
                raise Vault__Pathspec_Error(f"pathspec '{text}' is outside the vault")
            rel = os.path.relpath(full, root).replace(os.sep, '/')
            self.patterns.append(Safe_Str__Pathspec('' if rel == '.' else rel))
            self.typed.append(Safe_Str__Pathspec(text))
        return self

    def is_glob(self, pattern: str) -> bool:
        return any(ch in GLOB_CHARS for ch in pattern)

    def pattern_matches(self, pattern: str, path: str) -> bool:
        if pattern == '':
            return True
        if self.is_glob(pattern):
            return fnmatch.fnmatchcase(path, pattern)
        return path == pattern or path.startswith(pattern.rstrip('/') + '/')

    def match(self, paths) -> tuple:
        """(matched paths, patterns as typed that matched nothing)."""
        matched, unmatched = set(), []
        for pattern, typed in zip(self.patterns, self.typed):
            hits = {p for p in paths if self.pattern_matches(str(pattern), p)}
            if not hits:
                unmatched.append(str(typed))
            matched |= hits
        return matched, unmatched
