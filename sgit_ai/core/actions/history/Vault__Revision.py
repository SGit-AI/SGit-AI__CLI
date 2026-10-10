"""Vault__Revision — turn what a person types into a commit id.

Accepted, as in git (gitrevisions):
  HEAD / @                     this clone's head
  <rev>~n, <rev>~              n-th first-parent ancestor (default 1)
  <rev>^n, <rev>^              n-th parent (default the first); chains: HEAD~2^2~1
  @{n} / HEAD@{n}              where this clone's head was n moves ago (the reflog)
  <tag>, tag:<tag>             a tag's commit (sgit vault tag); a name that is both a tag and a
                               commit prefix is refused as ambiguous: say tag:<name> or the full id
  obj-cas-imm-<hex>, <hex>     a full id, the hex `history log` prints, or a
                               unique hex prefix of 4+ characters
Local only: nothing is fetched. A spelling that names nothing raises
Vault__Revision_Error naming it.
"""
import re
from   sgit_ai.core.Vault__Sync__Base               import Vault__Sync__Base
from   sgit_ai.core.Vault__Errors                   import Vault__Revision_Error
from   sgit_ai.storage.Vault__Commit                import Vault__Commit
from   sgit_ai.storage.Vault__Reflog                import Vault__Reflog

_REFLOG   = re.compile(r'^(?:HEAD)?@\{(\d+)\}$', re.IGNORECASE)
_SUFFIXES = re.compile(r'([~^])(\d*)')


class Vault__Revision(Vault__Sync__Base):

    def resolve(self, directory: str, spec: str) -> str:
        text = str(spec or '').strip()
        if not text:
            raise Vault__Revision_Error('no revision given')
        c          = self._init_components(directory)
        base, mods = self._split(text)
        commit_id  = self._base(c, directory, base, text)
        vc         = Vault__Commit(crypto=self.crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
        for op, count in mods:
            n = int(count) if count else 1
            if op == '~':
                for _ in range(n):
                    commit_id = self._parent(vc, c, commit_id, 1, text)
            else:
                commit_id = self._parent(vc, c, commit_id, n, text) if n else commit_id
        return commit_id

    def resolve_soft(self, directory: str, spec: str) -> str:
        """As resolve(), except that a full object id passes through untouched even
        when it is not local, so callers that fetch missing commits on demand
        (history show / diff) keep doing so."""
        text = str(spec or '').strip()
        if re.fullmatch(r'obj-cas-imm-(?:[0-9a-f]{12}|[0-9a-f]{32})', text):
            return text
        return self.resolve(directory, text)

    def head(self, directory: str, c=None) -> str:
        c      = c or self._init_components(directory)
        config = self._read_local_config(directory, c.storage)
        index  = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        meta   = c.branch_manager.get_branch_by_id(index, str(config.my_branch_id)) if config.my_branch_id else None
        if meta is None:
            meta = c.branch_manager.get_branch_by_name(index, 'current')
        return (c.ref_manager.read_ref(str(meta.head_ref_id), c.read_key) or '') if meta else ''

    def head_ref_id(self, directory: str, c=None) -> str:
        c      = c or self._init_components(directory)
        config = self._read_local_config(directory, c.storage)
        index  = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        meta   = c.branch_manager.get_branch_by_id(index, str(config.my_branch_id)) if config.my_branch_id else None
        return str(meta.head_ref_id) if meta else ''

    # ------------------------------------------------------------- helpers
    def _split(self, text: str) -> tuple:
        if _REFLOG.match(text):
            return text, []
        m = re.search(r'[~^]', text)
        if not m:
            return text, []
        base, rest = text[:m.start()], text[m.start():]
        mods = _SUFFIXES.findall(rest)
        if ''.join(op + n for op, n in mods) != rest:
            raise Vault__Revision_Error(f'{text!r} is not a revision this CLI understands '
                                        f'(HEAD, HEAD~2, HEAD^2, @{{1}}, a tag, or a commit id)')
        return base or 'HEAD', mods

    def _base(self, c, directory: str, base: str, text: str) -> str:
        if base.upper() in ('HEAD', '@'):
            head = self.head(directory, c)
            if not head:
                raise Vault__Revision_Error('this clone has no commits yet')
            return head
        m = _REFLOG.match(base)
        if m:
            return self._reflog(c, directory, int(m.group(1)), text)
        from sgit_ai.core.actions.tag.Vault__Sync__Tag import Vault__Sync__Tag
        tags = Vault__Sync__Tag(crypto=self.crypto, api=self.api)
        if base.startswith('tag:'):                                        # explicitly a tag
            by_tag = tags.resolve(directory, base[len('tag:'):])
            if not by_tag:
                raise Vault__Revision_Error(f'no tag named {base[len("tag:"):]!r}')
            return by_tag
        if re.fullmatch(r'(obj-cas-imm-)?[0-9a-fA-F]{4,32}', base):       # a commit prefix (any case; a blob or tree
            commit_id = self._commit_by_prefix(c, base, text)              # prefix never counts: B4b, d3b8eef)
            if commit_id:
                if not self._is_full_id(base) and tags.exists(directory, base):
                    raise Vault__Revision_Error(                           # a mined 4-hex commit must not shadow a
                        f'{base!r} is ambiguous: it is a tag and a prefix of commit {commit_id}. '   # signed tag (0a0707d F2)
                        f'Use tag:{base} for the tag, or the full commit id.')
                return commit_id
        by_tag = tags.resolve(directory, base)
        if by_tag:
            return by_tag
        try:
            commit_id = c.obj_store.resolve_id(base)
        except ValueError as error:
            raise Vault__Revision_Error(str(error))
        if not c.obj_store.exists(commit_id):
            raise Vault__Revision_Error(f'{text!r} names no commit this clone has (a commit id, a short id from '
                                        f'`sgit history log`, a tag, HEAD~n or @{{n}}); run sgit pull if it is new')
        try:                                                               # a short id matched trees and blobs too
            Vault__Commit(crypto=self.crypto, pki=c.pki, object_store=c.obj_store,
                          ref_manager=c.ref_manager).load_commit(commit_id, c.read_key)
        except Exception:
            raise Vault__Revision_Error(f'{text!r} names {commit_id}, which is a folder listing or a file, '
                                        f'not a commit')
        return commit_id

    def _is_full_id(self, base: str) -> bool:
        return bool(re.fullmatch(r'(obj-cas-imm-)?(?:[0-9a-fA-F]{12}|[0-9a-fA-F]{32})', base))

    def _commit_by_prefix(self, c, base: str, text: str) -> str:
        """The one commit in the store whose id starts with base (case-insensitive), or ''.
        Two or more commits raise, naming them."""
        from sgit_ai.storage.Vault__Object_Store import OBJ_CAS_IMM_PREFIX
        hex_part = base.lower()
        hex_part = hex_part[len(OBJ_CAS_IMM_PREFIX):] if hex_part.startswith(OBJ_CAS_IMM_PREFIX) else hex_part
        vc       = Vault__Commit(crypto=self.crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
        commits  = []
        for oid in c.obj_store.all_object_ids():
            if not oid.startswith(OBJ_CAS_IMM_PREFIX + hex_part):
                continue
            try:
                vc.load_commit(oid, c.read_key)
                commits.append(oid)
            except Exception:
                continue                                                   # a tree or a blob
        if len(commits) > 1:
            raise Vault__Revision_Error(f'{text} is ambiguous: it matches {len(commits)} commits '
                                        f'({", ".join(commits[:3])}); give more characters')
        return commits[0] if commits else ''

    def _reflog(self, c, directory: str, n: int, text: str) -> str:
        if n == 0:
            return self.head(directory, c)
        moves = Vault__Reflog(vault_path=c.sg_dir).entries(self.head_ref_id(directory, c))
        if n > len(moves) or not moves[n - 1].old_commit:
            raise Vault__Revision_Error(f'{text}: the reflog has only {len(moves)} move(s) of this clone\'s head '
                                        f'(sgit history reflog)')
        return str(moves[n - 1].old_commit)

    def _parent(self, vc, c, commit_id: str, n: int, text: str) -> str:
        if not c.obj_store.exists(commit_id):
            raise Vault__Revision_Error(f'{text}: history stops before {commit_id} in this clone '
                                        f'(shallow clone? sgit fetch --unshallow)')
        parents = [str(p) for p in (vc.load_commit(commit_id, c.read_key).parents or []) if str(p)]
        if n > len(parents):
            raise Vault__Revision_Error(f'{text}: {commit_id} has {len(parents)} parent(s), not {n}')
        return parents[n - 1]
