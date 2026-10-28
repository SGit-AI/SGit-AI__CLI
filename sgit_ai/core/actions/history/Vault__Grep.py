"""Vault__Grep — `sgit grep`: Git's grep over the working copy or a revision (design__04 §5.7).

The pattern is a Python regular expression (D2: -E and -P mean the same, -F is literal),
checked by Vault__Regex_Guard; several -e are ORed; -w is Git's word rule on [A-Za-z0-9_].
Content is decoded with surrogateescape, so any byte sequence matches on its ASCII parts.
One scan of the whole file decides whether a file is opened line by line, so the common
case runs at the regex engine's speed. A file with a NUL in its first 8,000 bytes is
binary (Git's rule): `Binary file … matches`, skipped with -I, searched with --text.

Sources: the working copy's tracked files on disk (never through a link; a tracked file
not checked out is counted, not searched: D7), plus untracked ones with --untracked; or
a revision's tree, decrypted in memory, its blobs fetched when the clone has a remote."""
import os
import re
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   osbot_utils.type_safe.primitives.core.Safe_UInt    import Safe_UInt
from   sgit_ai.core.Vault__Errors                         import Vault__Revision_Error
from   sgit_ai.core.Vault__Regex_Guard                    import Vault__Regex_Guard
from   sgit_ai.crypto.Vault__Crypto                       import Vault__Crypto
from   sgit_ai.safe_types.Safe_Str__Grep_Pattern          import Safe_Str__Grep_Pattern

BINARY_PROBE_BYTES = 8000
WORD               = 'A-Za-z0-9_'


class Vault__Grep(Type_Safe):
    crypto        : Vault__Crypto
    api           : object = None
    patterns      : list[Safe_Str__Grep_Pattern]
    fixed         : bool = False
    ignore_case   : bool = False
    word          : bool = False
    invert        : bool = False
    untracked     : bool = False
    text          : bool = False
    skip_binary   : bool = False
    offline       : bool = False
    max_count     : Safe_UInt
    before        : Safe_UInt
    after         : Safe_UInt
    compiled      : object = None
    skipped       : object = None                       # {'not_checked_out': n, 'not_local': n, 'outside_scope': n}

    def compile(self):
        if not self.patterns:
            raise Vault__Revision_Error('no pattern given')
        parts = []
        for pattern in self.patterns:
            text = re.escape(str(pattern)) if self.fixed else str(pattern)
            if not self.fixed:
                Vault__Regex_Guard().check(text, 'grep', flags=re.IGNORECASE if self.ignore_case else 0)
            parts.append(f'(?:{text})')
        joined = '|'.join(parts)
        if self.word:
            joined = f'(?<![{WORD}])(?:{joined})(?![{WORD}])'
        self.compiled = re.compile(joined, re.IGNORECASE if self.ignore_case else 0)
        self.skipped  = dict(not_checked_out=0, not_local=0, outside_scope=0)
        return self.compiled

    # --- one file -----------------------------------------------------------------------

    def search(self, data: bytes) -> dict:
        """dict(binary, rows=[(line_no, text, spans, is_match)] with context rows, count of
        selected lines). rows is empty for a binary file (only `matched` tells)."""
        binary = b'\x00' in data[:BINARY_PROBE_BYTES]
        if binary and self.skip_binary:
            return dict(binary=True, rows=[], count=0, matched=False)
        content = data.decode('utf-8', 'surrogateescape')
        if not self.invert and not self.compiled.search(content):                    # one scan: most files stop here
            return dict(binary=binary, rows=[], count=0, matched=False)
        lines    = content.split('\n')
        if lines and lines[-1] == '':
            lines.pop()
        selected = []
        for number, line in enumerate(lines, start=1):
            spans = [m.span() for m in self.compiled.finditer(line) if m.end() > m.start() or not line]
            hit   = bool(spans) or (self.compiled.search(line) is not None)
            if hit != self.invert:
                selected.append((number, line, spans if not self.invert else []))
                if int(self.max_count) and len(selected) >= int(self.max_count):
                    break
        if binary and not self.text:
            return dict(binary=True, rows=[], count=len(selected), matched=bool(selected))
        return dict(binary=False, rows=self.with_context(lines, selected), count=len(selected), matched=bool(selected))

    def with_context(self, lines: list, selected: list) -> list:
        if not int(self.before) and not int(self.after):
            return [(n, t, s, True) for n, t, s in selected]
        chosen = {n: (t, s) for n, t, s in selected}
        shown  = set()
        for n in chosen:
            shown.update(range(max(1, n - int(self.before)), min(len(lines), n + int(self.after)) + 1))
        return [(n, lines[n - 1], chosen[n][1] if n in chosen else [], n in chosen) for n in sorted(shown)]

    # --- sources ------------------------------------------------------------------------

    def working_files(self, directory: str, pathspec=None):
        """(path, bytes) of the tracked files on disk (and, with untracked, the other files the
        scan lists), sorted; tracked files not on disk are counted in skipped."""
        from sgit_ai.core.Vault__Head_Paths    import Vault__Head_Paths
        from sgit_ai.core.Vault__Sync__Base    import Vault__Sync__Base
        from sgit_ai.storage.Vault__Path_Guard import Vault__Path_Guard
        tracked = Vault__Head_Paths(crypto=self.crypto).paths(directory)
        on_disk = Vault__Sync__Base(crypto=self.crypto)._scan_local_directory(directory)
        paths   = set(on_disk) if self.untracked else (tracked & set(on_disk))
        missing = tracked - set(on_disk)
        if pathspec is not None:
            paths   = pathspec.match(paths)[0]
            missing = pathspec.match(missing)[0] if missing else set()
        self.skipped['not_checked_out'] = len(missing)
        guard = Vault__Path_Guard()
        for path in sorted(paths):
            full = os.path.join(directory, path)
            if os.path.islink(full) or guard.has_link_component(os.path.abspath(directory), os.path.abspath(full)):
                continue
            data = guard.read_regular(full, path)
            if data is not None:
                yield path, data

    def revision_files(self, directory: str, rev: str, pathspec=None):
        """(path, bytes) of a revision's files, sorted, decrypted in memory."""
        from sgit_ai.core.Vault__Sync__Base                   import Vault__Sync__Base
        from sgit_ai.core.actions.history.Vault__Blob_Reader  import Vault__Blob_Reader
        from sgit_ai.core.actions.history.Vault__Revision     import Vault__Revision
        from sgit_ai.storage.Vault__Commit                    import Vault__Commit
        from sgit_ai.storage.Vault__Scope                     import Vault__Scope
        from sgit_ai.storage.Vault__Scoped_Tree               import Vault__Scoped_Tree
        from sgit_ai.storage.Vault__Sub_Tree                  import Vault__Sub_Tree
        base      = Vault__Sync__Base(crypto=self.crypto, api=self.api)
        c         = base._init_components(directory)
        commit_id = Vault__Revision(crypto=self.crypto).resolve(directory, rev)
        commit    = Vault__Commit(crypto=self.crypto, pki=c.pki, object_store=c.obj_store,
                                  ref_manager=c.ref_manager).load_commit(commit_id, c.read_key)
        scope     = Vault__Scope().from_local_config(base._read_local_config(directory, c.storage))
        if scope.is_scoped():
            flat, opaque = Vault__Scoped_Tree(crypto=self.crypto, obj_store=c.obj_store).flatten(
                str(commit.tree_id), c.read_key, scope)
            self.skipped['outside_scope'] += len(opaque or {})
        else:
            flat = Vault__Sub_Tree(crypto=self.crypto, obj_store=c.obj_store).flatten(str(commit.tree_id), c.read_key)
        paths  = pathspec.match(set(flat))[0] if pathspec is not None else set(flat)
        reader = Vault__Blob_Reader(crypto=self.crypto, obj_store=c.obj_store, read_key=c.read_key,
                                    vault_id=str(c.vault_id), sg_dir=str(c.sg_dir), api=self.api,
                                    offline=self.offline, memo_bytes=0)
        reader.prefetch([flat[p] for p in paths])
        for path in sorted(paths):
            data = reader.content(flat[path])
            if data is None:
                self.skipped['not_local'] += 1
                continue
            yield path, data
