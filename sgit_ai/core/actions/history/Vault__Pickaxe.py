"""Vault__Pickaxe — `history log -S <string>` / `-G <regex>` (design__04 §5.8), as git log:

  -S  a commit where the number of occurrences of the string changes in some file (literal,
      non-overlapping, as Git counts; --pickaxe-regex: of the regex). Binary files count.
  -G  a commit whose diff adds or removes a line matching the regex. Binary files are skipped.

A commit is compared with its only parent (the root with nothing); merge commits are not
searched, as git log without -m, and are counted for a note. Only the changed files are
read (the pruned tree diff), each through the blob reader."""
import re
from   osbot_utils.type_safe.Type_Safe                    import Type_Safe
from   osbot_utils.type_safe.primitives.core.Safe_UInt    import Safe_UInt
from   sgit_ai.core.Vault__Regex_Guard                    import Vault__Regex_Guard
from   sgit_ai.core.text.Vault__Line_Diff                 import Vault__Line_Diff
from   sgit_ai.core.text.Vault__Line_Splitter             import Vault__Line_Splitter
from   sgit_ai.safe_types.Safe_Str__Content_Path          import Safe_Str__Content_Path
from   sgit_ai.safe_types.Safe_Str__Grep_Pattern          import Safe_Str__Grep_Pattern

BINARY_PROBE_BYTES = 8000
NO_EDIT_CAP        = 10 ** 8


class Vault__Pickaxe(Type_Safe):
    mode          : Safe_Str__Grep_Pattern = 'S'               # 'S' or 'G'
    needle        : Safe_Str__Grep_Pattern
    regex         : bool = False                               # --pickaxe-regex (always true for -G)
    ignore_case   : bool = False
    only_path     : Safe_Str__Content_Path = None              # --file: search only this path
    merges_skipped: Safe_UInt
    pattern       : object = None

    def setup(self) -> 'Vault__Pickaxe':
        flags = re.IGNORECASE if self.ignore_case else 0
        if self.mode == 'G' or self.regex:
            self.pattern = Vault__Regex_Guard().check(str(self.needle), f'-{self.mode}', flags=flags)
        else:
            self.pattern = re.compile(re.escape(str(self.needle)), flags)
        return self

    def matches(self, changes: dict, content_of) -> list:
        """The changed paths that make this commit a match (diff_trees' shape: added, deleted,
        modified {path: (new, old)}); content_of(entry) -> bytes | None."""
        hits = []
        sides = [(p, None, e) for p, e in changes['added'].items()] + \
                [(p, e, None) for p, e in changes['deleted'].items()] + \
                [(p, old, new) for p, (new, old) in changes['modified'].items()]
        for path, old, new in sorted(sides, key=lambda s: s[0]):
            if self.only_path and path != str(self.only_path):
                continue
            before = content_of(old) if old is not None else b''
            after  = content_of(new) if new is not None else b''
            if before is None or after is None:
                continue
            if self.file_matches(before, after):
                hits.append(path)
        return hits

    def file_matches(self, before: bytes, after: bytes) -> bool:
        if self.mode == 'S':
            return self.count(before) != self.count(after)
        if b'\x00' in before[:BINARY_PROBE_BYTES] or b'\x00' in after[:BINARY_PROBE_BYTES]:
            return False                                                     # git -G skips binary files
        splitter = Vault__Line_Splitter()
        a, b     = splitter.split(before), splitter.split(after)
        a_ids, b_ids = splitter.intern(a, b)
        for tag, i1, i2, j1, j2 in Vault__Line_Diff(max_edit_cost=NO_EDIT_CAP).opcodes(a_ids, b_ids):
            if tag == 'equal':
                continue
            for line in a[i1:i2] + b[j1:j2]:
                if self.pattern.search(line.decode('utf-8', 'surrogateescape').rstrip('\n')):
                    return True
        return False

    def count(self, data: bytes) -> int:
        return len(self.pattern.findall(data.decode('utf-8', 'surrogateescape')))

    def search(self, directory: str, chain: list) -> list:
        """The entries of `chain` (inspector dicts: commit_id, parents, tree_id) that match, each
        with 'pickaxe_paths'; merges are skipped and counted."""
        from sgit_ai.core.Vault__Sync__Base                  import Vault__Sync__Base
        from sgit_ai.core.actions.history.Vault__Blob_Reader import Vault__Blob_Reader
        from sgit_ai.storage.Vault__Commit                   import Vault__Commit
        from sgit_ai.storage.Vault__Sub_Tree                 import Vault__Sub_Tree
        from sgit_ai.crypto.Vault__Crypto                    import Vault__Crypto
        crypto = Vault__Crypto()
        c      = Vault__Sync__Base(crypto=crypto)._init_components(directory)
        vc     = Vault__Commit(crypto=crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
        sub    = Vault__Sub_Tree(crypto=crypto, obj_store=c.obj_store)
        reader = Vault__Blob_Reader(crypto=crypto, obj_store=c.obj_store, read_key=c.read_key)
        out    = []
        for entry in chain:
            if not isinstance(entry, dict) or entry.get('error'):
                continue
            parents = [p for p in entry.get('parents') or [] if p]
            if len(parents) > 1:
                self.merges_skipped += 1
                continue
            tree        = str(entry.get('tree_id') or vc.load_commit(entry['commit_id'], c.read_key).tree_id)
            parent_tree = str(vc.load_commit(parents[0], c.read_key).tree_id) if parents else None
            paths       = self.matches(sub.diff_trees(tree, parent_tree, c.read_key), reader.content)
            if paths:
                out.append(dict(entry, pickaxe_paths=paths))
        return out
