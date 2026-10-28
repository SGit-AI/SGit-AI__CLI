"""Vault__Blame — `sgit history blame`: each line of a file at a revision attributed to the
commit that last changed it (design__04 §5.6; Git's blame.c, its default passes).

Entries (final_start, count, suspect_start) are held per origin (commit, path). For an
origin: if a parent holds the very same file (same blob, or same content hash and size),
every entry moves there unchanged (Git's identical-parent shortcut, what makes a long
history cheap); otherwise each parent in order takes the lines its version shares with
this one (the equal blocks of the shared differ) and what is left stays on this commit.
Renames are followed: a parent without the path is searched for the file's rename
source in that commit. A root commit, a shallow boundary, or a parent not in this clone
ends the walk there, marked as a boundary (`^`). Each entry travels on its own, so the
result does not depend on the order origins are processed in."""
import heapq
import re
from   osbot_utils.type_safe.Type_Safe                       import Type_Safe
from   sgit_ai.core.Vault__Errors                            import Vault__Revision_Error
from   sgit_ai.core.actions.diff.Vault__Renames              import Vault__Renames
from   sgit_ai.core.actions.history.Vault__Blob_Reader       import Vault__Blob_Reader
from   sgit_ai.core.actions.history.Vault__Path_History      import Vault__Path_History
from   sgit_ai.core.text.Vault__Line_Diff                    import Vault__Line_Diff
from   sgit_ai.core.text.Vault__Line_Splitter                import Vault__Line_Splitter
from   sgit_ai.crypto.Vault__Crypto                          import Vault__Crypto
from   sgit_ai.schemas.history.Schema__Blame_Commit          import Schema__Blame_Commit
from   sgit_ai.schemas.history.Schema__Blame_Line            import Schema__Blame_Line
from   sgit_ai.schemas.history.Schema__Blame_Result          import Schema__Blame_Result
from   sgit_ai.storage.Vault__Commit                         import Vault__Commit
from   sgit_ai.storage.Vault__Sub_Tree                       import Vault__Sub_Tree

NO_EDIT_CAP = 10 ** 8                                           # blame diffs whole files, as git does


class Vault__Blame(Type_Safe):
    crypto            : Vault__Crypto
    api               : object = None
    ignore_whitespace : bool = False
    first_parent      : bool = False
    follow_renames    : bool = True
    text              : bool = False
    offline           : bool = False
    c                 : object = None                          # the per-run state, set by blame()
    vc                : object = None
    history           : object = None
    reader            : object = None
    splitter          : object = None
    commits           : object = None                          # commit id -> {'obj', 'previous', 'boundary'}
    lines_of          : object = None                          # blob id -> lines
    bounds            : object = None                          # shallow boundary ids

    def blame(self, directory: str, path: str, rev: str = '', ranges: list = None) -> Schema__Blame_Result:
        from sgit_ai.core.Vault__Sync__Base                 import Vault__Sync__Base
        from sgit_ai.core.actions.history.Vault__Revision   import Vault__Revision
        from sgit_ai.storage.Vault__Scope                   import Vault__Scope
        base   = Vault__Sync__Base(crypto=self.crypto, api=self.api)
        c      = base._init_components(directory)
        config = base._read_local_config(directory, c.storage)
        scope  = Vault__Scope().from_local_config(config)
        if scope.is_scoped() and not scope.contains_path(path):
            raise Vault__Revision_Error(f"'{path}' is outside this clone's folders ({', '.join(scope.folders())}); "
                                        f"widen with: sgit fetch <folder>")
        start  = Vault__Revision(crypto=self.crypto).resolve(directory, rev or 'HEAD')
        self.c         = c
        self.vc        = Vault__Commit(crypto=self.crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
        self.history   = Vault__Path_History(sub_tree=Vault__Sub_Tree(crypto=self.crypto, obj_store=c.obj_store),
                                             read_key=c.read_key)
        self.reader    = Vault__Blob_Reader(crypto=self.crypto, obj_store=c.obj_store, read_key=c.read_key,
                                            vault_id=str(c.vault_id), sg_dir=str(c.sg_dir),
                                            api=self.api, offline=self.offline)
        self.splitter  = Vault__Line_Splitter(ignore_whitespace=self.ignore_whitespace)
        self.commits   = {}
        self.lines_of  = {}
        self.bounds    = set(scope.boundary_ids())
        result         = Schema__Blame_Result(path=path, rev=start, boundary_reason='')
        head           = self.commit(start)
        entry          = self.history.entry_at(str(head.tree_id), path)
        if entry is None:
            raise Vault__Revision_Error(f"path '{path}' does not exist in {rev or 'HEAD'}")
        content = self.content(entry)
        if content is None:
            raise Vault__Revision_Error(f"'{path}' at {rev or 'HEAD'} is not in this clone and could not be fetched")
        if not self.text and self.splitter.is_binary(content):
            raise Vault__Revision_Error(f"'{path}' is a binary file: pass --text to blame it line by line")
        lines   = self.splitter.split(content)
        entries = [[s, n, s] for s, n in self.parse_ranges(ranges or [], lines)]
        finals  = self.assign(start, path, entry, entries, result)
        for commit_id, origin_path, final_start, count, suspect in sorted(finals, key=lambda f: f[2]):
            for k in range(count):
                result.lines.append(Schema__Blame_Line(final_line=final_start + k + 1, orig_line=suspect + k + 1,
                                                       commit_id=commit_id, orig_path=origin_path,
                                                       text=self.display(lines[final_start + k])))
        result.blobs_read = int(self.reader.blobs_read)
        self.describe_commits(directory, result)
        return result

    # --- the walk -----------------------------------------------------------------------

    def assign(self, start: str, path: str, entry: dict, entries: list, result) -> list:
        queue, waiting, finals, seq = [], {}, [], 0
        def offer(commit_id, origin_path, origin_entry, new_entries):
            nonlocal seq
            key = (commit_id, origin_path)
            if key in waiting:
                waiting[key][1].extend(new_entries)
                return
            waiting[key] = [origin_entry, list(new_entries)]
            seq += 1
            heapq.heappush(queue, (-int(self.commit(commit_id).timestamp_ms or 0), seq, commit_id, origin_path))
        offer(start, path, entry, entries)
        while queue:
            _, _, commit_id, origin_path = heapq.heappop(queue)
            origin_entry, pending = waiting.pop((commit_id, origin_path))
            result.commits_visited += 1
            left = self.pass_to_parents(commit_id, origin_path, origin_entry, pending, offer, result)
            finals += [(commit_id, origin_path, s, n, sus) for s, n, sus in left]
        return finals

    def pass_to_parents(self, commit_id, path, entry, pending, offer, result) -> list:
        commit  = self.commit(commit_id)
        parents = [str(p) for p in (commit.parents or []) if str(p)]
        if self.first_parent:
            parents = parents[:1]
        if not parents or commit_id in self.bounds:
            self.boundary(commit_id, 'shallow' if commit_id in self.bounds else '', result)
            return pending
        found = []
        for parent_id in parents:
            if not self.c.obj_store.exists(parent_id):
                self.boundary(commit_id, 'offline', result)
                return pending
            parent      = self.commit(parent_id)
            p_path      = path
            p_entry     = self.history.entry_at(str(parent.tree_id), path)
            if p_entry is None and self.follow_renames:
                p_path, p_entry = self.rename_source(str(commit.tree_id), str(parent.tree_id), path, entry)
            if p_entry is not None:
                found.append((parent_id, p_path, p_entry))
        self.commits.setdefault(commit_id, {})['previous'] = (found[0][0], found[0][1]) if found else None
        for parent_id, p_path, p_entry in found:                         # the identical-parent shortcut
            if self.same_file(entry, p_entry):
                offer(parent_id, p_path, p_entry, pending)
                return []
        mine = self.lines(entry)
        for parent_id, p_path, p_entry in found:
            theirs = self.lines(p_entry)
            if mine is None or theirs is None:
                continue
            moved, pending = self.split_by_blocks(pending, self.equal_blocks(theirs, mine))
            if moved:
                offer(parent_id, p_path, p_entry, moved)
            if not pending:
                break
        return pending

    def split_by_blocks(self, pending: list, blocks: list) -> tuple:
        """(entries moved to the parent, entries left): each entry's suspect lines that fall in
        an equal block (i parent, j here, n lines) move, remapped to the parent's numbering."""
        moved, left = [], []
        for final_start, count, suspect in pending:
            cursor, end = suspect, suspect + count
            for i, j, n in blocks:
                lo, hi = max(cursor, j), min(end, j + n)
                if lo >= hi:
                    continue
                if lo > cursor:
                    left.append([final_start + (cursor - suspect), lo - cursor, cursor])
                moved.append([final_start + (lo - suspect), hi - lo, i + (lo - j)])
                cursor = hi
            if cursor < end:
                left.append([final_start + (cursor - suspect), end - cursor, cursor])
        return moved, left

    def equal_blocks(self, parent_lines: list, lines: list) -> list:
        a_ids, b_ids = self.splitter.intern(parent_lines, lines)
        return [(i1, j1, i2 - i1) for tag, i1, i2, j1, j2 in Vault__Line_Diff(max_edit_cost=NO_EDIT_CAP).opcodes(a_ids, b_ids)
                if tag == 'equal' and i2 > i1]

    def rename_source(self, tree, parent_tree, path, entry) -> tuple:
        changes = self.history.changed_paths(tree, parent_tree)
        if not changes['deleted']:
            return path, None
        pairs = Vault__Renames().detect(dict(changes['deleted']), {path: entry}, content_of=self.content).pairs
        if not pairs:
            return path, None
        old = str(pairs[0].old_path)
        return old, changes['deleted'][old]

    # --- helpers ------------------------------------------------------------------------

    def commit(self, commit_id: str):
        if commit_id not in self.commits or 'obj' not in self.commits[commit_id]:
            self.commits.setdefault(commit_id, {})['obj'] = self.vc.load_commit(commit_id, self.c.read_key)
        return self.commits[commit_id]['obj']

    def content(self, entry):
        return self.reader.content(entry)

    def lines(self, entry):
        blob_id = str(entry['blob_id'])
        if blob_id not in self.lines_of:
            data = self.content(entry)
            self.lines_of[blob_id] = self.splitter.split(data) if data is not None else None
        return self.lines_of[blob_id]

    def same_file(self, a: dict, b: dict) -> bool:
        if str(a.get('blob_id')) == str(b.get('blob_id')):
            return True
        return bool(a.get('content_hash')) and (a['content_hash'], a.get('size')) == (b.get('content_hash'), b.get('size'))

    def boundary(self, commit_id: str, reason: str, result) -> None:
        self.commits.setdefault(commit_id, {})['boundary'] = True
        if reason and not result.boundary_reason:
            result.boundary_reason = reason

    def display(self, line: bytes) -> str:
        text = line.decode('utf-8', 'replace').rstrip('\n')
        return ''.join(ch if ch == '\t' or ch >= ' ' and ch != '\x7f' else '?' for ch in text)

    def parse_ranges(self, ranges: list, lines: list) -> list:
        """Git's -L forms on 1-based lines: N,M  N,+K  N,-K  N  ,M  /re/  /re/,+K; merged, sorted,
        as (start index, count). No range: the whole file."""
        total = len(lines)
        if not ranges:
            return [(0, total)] if total else []
        spans = []
        for spec in ranges:
            begin_text, _, end_text = str(spec).partition(',')
            begin = self.line_of(begin_text, lines, 1) if begin_text else 1
            if begin > total or begin < 1:
                raise Vault__Revision_Error(f'file has only {total} line{"s" if total != 1 else ""}')
            if not end_text:
                end = total
            elif end_text.startswith('+'):
                end = begin + int(end_text[1:]) - 1
            elif end_text.startswith('-'):
                begin, end = max(1, begin - int(end_text[1:]) + 1), begin
            else:
                end = self.line_of(end_text, lines, begin)
            begin, end = min(begin, end), max(begin, end)
            spans.append((begin - 1, min(end, total)))
        spans.sort()
        merged = []
        for lo, hi in spans:
            if merged and lo <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))
        return [(lo, hi - lo) for lo, hi in merged]

    def line_of(self, text: str, lines: list, after: int) -> int:
        if text.startswith('/') and text.endswith('/') and len(text) > 1:
            from sgit_ai.core.Vault__Regex_Guard import Vault__Regex_Guard
            pattern = Vault__Regex_Guard().check(text[1:-1], '-L', flags=0)
            for k in range(max(after - 1, 0), len(lines)):
                if pattern.search(lines[k].decode('utf-8', 'replace')):
                    return k + 1
            raise Vault__Revision_Error(f'-L {text}: no match')
        if not re.fullmatch(r'\d+', text):
            raise Vault__Revision_Error(f'-L: {text!r} is not a line number or /regex/')
        return int(text)

    def describe_commits(self, directory: str, result) -> None:
        names = self.branch_names(directory)
        for commit_id in {str(l.commit_id) for l in result.lines}:
            commit  = self.commit(commit_id)
            meta    = self.commits.get(commit_id, {})
            message = ''
            if commit.message_enc:
                try:
                    message = self.crypto.decrypt_metadata(self.c.read_key, str(commit.message_enc))
                except Exception:
                    message = ''
            key_id  = str(commit.author_key_id or '')
            author  = names.get(str(commit.branch_id or ''), '') or key_id[:24] or 'unknown'
            prev    = meta.get('previous')
            result.commits[commit_id] = Schema__Blame_Commit(
                timestamp_ms  = int(commit.timestamp_ms or 0),
                author        = author,
                author_key_id = key_id or None,
                summary       = (message.splitlines() or [''])[0][:500],
                boundary      = bool(meta.get('boundary')),
                previous_id   = prev[0] if prev else None,
                previous_path = prev[1] if prev else '')

    def branch_names(self, directory: str) -> dict:
        try:
            index = self.c.branch_manager.load_branch_index(directory, self.c.branch_index_file_id, self.c.read_key)
            return {str(b.branch_id): str(b.name) for b in index.branches if b.name}
        except Exception:
            return {}
