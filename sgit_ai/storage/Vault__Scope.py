"""Vault__Scope — which folders, and how much history, a clone holds.

A clone can be partial in two independent ways, both recorded in its local
config and both empty for an ordinary full clone:

  * scope_paths  — folders the clone holds (trees, blobs, working copy). Every
                   other folder is known only by its tree id in the parent
                   tree ("opaque"), which is all a commit needs to carry it
                   forward unchanged: a Merkle tree rebuilds a path by
                   replacing one entry per level and keeping the siblings' ids.
  * boundaries   — commits whose parents were deliberately not fetched
                   (`--depth`). History walks stop there.

Why: ten agents share one vault and most of them live in one folder. The HEAD
of that vault is 626 trees / 3,435 files; `mail/crm.riskmandate/` alone is 61
trees / 365 files plus the two trees on the spine above it. A scoped clone of
that folder is ~430 objects instead of 18,684 — and two agents in different
folders can never produce a merge conflict, because out-of-scope entries are
always taken from the remote by id.

Everything here is pure path logic; no I/O.
"""
from osbot_utils.type_safe.Type_Safe import Type_Safe


class Vault__Scope(Type_Safe):
    paths      : list[str]           # normalised folder paths, no leading/trailing '/'; [] = whole vault
    boundaries : list[str]           # shallow boundary commit ids; [] = full history

    # ------------------------------------------------------------ construction
    def with_paths(self, paths) -> 'Vault__Scope':
        seen = []
        for p in paths or []:
            n = self.normalise(p)
            if n and n not in seen:
                seen.append(n)
        self.paths = seen
        return self

    def with_boundaries(self, commit_ids) -> 'Vault__Scope':
        self.boundaries = [str(c) for c in (commit_ids or []) if c]
        return self

    def normalise(self, path: str) -> str:
        return '/'.join(part for part in str(path or '').replace('\\', '/').split('/') if part and part != '.')

    def from_local_config(self, local_config) -> 'Vault__Scope':
        paths      = getattr(local_config, 'scope_paths', None) or []
        boundaries = getattr(local_config, 'shallow_boundaries', None) or []
        return self.with_paths([str(p) for p in paths]).with_boundaries([str(b) for b in boundaries])

    # ------------------------------------------------------------- predicates
    def is_whole(self) -> bool:          # every folder held
        return not self.paths

    def is_scoped(self) -> bool:
        return bool(self.paths)

    def is_shallow(self) -> bool:
        return bool(self.boundaries)

    def is_partial(self) -> bool:
        return self.is_scoped() or self.is_shallow()

    def is_boundary(self, commit_id: str) -> bool:
        return bool(commit_id) and str(commit_id) in self.boundaries

    def contains_path(self, path: str) -> bool:
        """A file (or folder) path lies inside one of the scope folders."""
        if self.is_whole():
            return True
        p = self.normalise(path)
        for root in self.paths:
            if p == root or p.startswith(root + '/'):
                return True
        return False

    def is_spine_dir(self, dir_path: str) -> bool:
        """A folder on the way down to a scope folder (its contents are NOT held,
        except the one child that leads on; the walk must descend into it)."""
        if self.is_whole():
            return False
        d = self.normalise(dir_path)
        for root in self.paths:
            if d == '' or root.startswith(d + '/'):
                return True
        return False

    def descends_into(self, dir_path: str) -> bool:
        """Should a walk open this folder? Yes for held folders and the spine."""
        return self.is_whole() or self.contains_path(dir_path) or self.is_spine_dir(dir_path)

    def paths_outside(self, paths) -> list:
        return sorted(p for p in paths if not self.contains_path(p))

    def describe(self) -> str:
        parts = []
        if self.paths:
            parts.append('folders: ' + ', '.join(self.paths))
        if self.boundaries:
            parts.append(f'history stops at {len(self.boundaries)} boundary commit(s)')
        return '; '.join(parts) if parts else 'whole vault, full history'
