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
from osbot_utils.type_safe.Type_Safe              import Type_Safe
from sgit_ai.safe_types.Safe_Str__File_Path       import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Commit_Id       import Safe_Str__Commit_Id

OBJECT_ID_PREFIX = 'obj-cas-imm-'


class Vault__Scope(Type_Safe):
    paths      : list[Safe_Str__File_Path]    # normalised folder paths, no leading/trailing '/'; [] = whole vault
    boundaries : list[Safe_Str__Commit_Id]    # shallow boundary commit ids; [] = full history

    # ------------------------------------------------------------ construction
    def with_paths(self, paths) -> 'Vault__Scope':
        seen = []
        for p in paths or []:
            n = self.normalise(p)
            if n and n not in seen:
                seen.append(n)
        # a folder inside another held folder is already held: keep the widest only
        self.paths = [str(p) for p in seen if not any(p.startswith(o + '/') for o in seen if o != p)]
        return self

    def with_boundaries(self, commit_ids) -> 'Vault__Scope':
        ids = [str(c) for c in (commit_ids or []) if c]
        bad = [c for c in ids if not c.startswith(OBJECT_ID_PREFIX)]
        if bad:
            raise ValueError(f'shallow boundary is not a commit object id: {bad[0]}')
        self.boundaries = ids
        return self

    def normalise(self, path: str) -> str:
        """Vault-relative folder path: forward slashes, no empty or '.' parts.
        '..' and absolute paths are refused — a scope names folders INSIDE the
        vault tree, never a location on disk."""
        raw   = str(path or '').replace('\\', '/')
        parts = [part for part in raw.split('/') if part and part != '.']
        if '..' in parts:
            raise ValueError(f'scope folder must not contain "..": {path!r}')
        if raw.startswith('/') or (len(raw) > 1 and raw[1] == ':'):
            raise ValueError(f'scope folder must be vault-relative, not absolute: {path!r}')
        return '/'.join(parts)

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
        return bool(commit_id) and str(commit_id) in self.boundary_ids()

    def boundary_ids(self) -> list:
        """The boundary commit ids as plain str. The field holds Safe_Str__Commit_Id
        values, which validate but hash differently from str (so they fail set
        membership against plain ids) and get sanitised by os.path.join; every
        consumer that walks the store or builds sets takes these."""
        return [str(b) for b in (self.boundaries or [])]

    def folders(self) -> list:
        """The held folders as plain str (see boundary_ids)."""
        return [str(p) for p in (self.paths or [])]

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
            parts.append('folders: ' + ', '.join(self.folders()))
        if self.boundaries:
            parts.append(f'history stops at {len(self.boundaries)} boundary commit(s)')
        return '; '.join(parts) if parts else 'whole vault, full history'
