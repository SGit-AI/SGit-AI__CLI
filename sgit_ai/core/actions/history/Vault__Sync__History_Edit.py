"""Vault__Sync__History_Edit — undo, revert-as-commit, and the "already pushed?" rule.

  undo()            move this clone's head back to where it was before its last
                    move (the reflog), restoring the files; local only
  revert_commit()   a NEW commit that inverts an earlier one (git revert),
                    which is how a pushed commit is undone for everyone
  is_pushed()       the rule undo and `commit --amend` share: a commit that the
                    named branch already contains is shared history; moving
                    or rewriting it here would only diverge this clone

All refusals happen before anything changes and say what to do instead.
"""
from   sgit_ai.core.Vault__Sync__Base                  import Vault__Sync__Base
from   sgit_ai.core.Vault__Errors                      import Vault__Revision_Error, Vault__Scoped_Clone_Error
from   sgit_ai.core.actions.history.Vault__Revision    import Vault__Revision
from   sgit_ai.core.actions.pull.Vault__Ref_Guard      import Vault__Ref_Guard
from   sgit_ai.storage.Vault__Commit                   import Vault__Commit
from   sgit_ai.storage.Vault__Reflog                   import Vault__Reflog
from   sgit_ai.storage.Vault__Scope                    import Vault__Scope
from   sgit_ai.storage.Vault__Sub_Tree                 import Vault__Sub_Tree


class Vault__Sync__History_Edit(Vault__Sync__Base):

    # ----------------------------------------------------------------- rule
    def is_pushed(self, directory: str, commit_id: str, c=None) -> bool:
        """True when the named branch (as this clone last saw it, locally or as the
        last remote head) already contains commit_id."""
        c      = c or self._init_components(directory)
        index  = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        config = self._read_local_config(directory, c.storage)
        named  = c.branch_manager.tracked_named_branch(index, str(config.my_branch_id or ''))
        heads  = {c.ref_manager.read_ref(str(named.head_ref_id), c.read_key) or '' if named else '',
                  self._read_remote_baseline(directory, c.storage, str(named.head_ref_id)) or '' if named else ''}
        guard  = Vault__Ref_Guard(crypto=self.crypto)
        return any(h and guard.is_ancestor(c, c.read_key, commit_id, h) for h in heads)

    # ----------------------------------------------------------------- undo
    def undo(self, directory: str, force: bool = False) -> dict:
        c      = self._init_components(directory)
        rev    = Vault__Revision(crypto=self.crypto, api=self.api)
        head   = rev.head(directory, c)
        moves  = Vault__Reflog(vault_path=c.sg_dir).entries(rev.head_ref_id(directory, c))
        if not moves or not moves[0].old_commit:
            raise Vault__Revision_Error('nothing to undo: the reflog has no earlier position for this clone\'s head '
                                        '(it starts with sgit-ai 0.21.0; sgit history reflog)')
        target = str(moves[0].old_commit)
        self._require_clean(directory, 'undo')
        forward = bool(head) and Vault__Ref_Guard(crypto=self.crypto).is_ancestor(c, c.read_key, head, target)
        if not force and head and not forward and self.is_pushed(directory, head, c):   # a redo onto pushed history is fine (S4)
            raise Vault__Revision_Error(
                f'the head {head} is already on the server: undo moves only this clone, and the next pull '
                f'would bring it back. To undo a pushed commit for everyone: sgit history revert --as-commit '
                f'--commit {head}. (--force moves this clone anyway.)')
        from sgit_ai.core.actions.pull.Vault__Sync__Pull import Vault__Sync__Pull
        result = Vault__Sync__Pull(crypto=self.crypto, api=self.api).reset(directory, target)
        return dict(from_commit=head, to_commit=target, restored=result['restored'], deleted=result['deleted'])

    # ------------------------------------------------------- revert-as-commit
    def revert_commit(self, directory: str, spec: str, message: str = '') -> dict:
        c      = self._init_components(directory)
        scope  = Vault__Scope().from_local_config(self._read_local_config(directory, c.storage))
        if scope.is_scoped():
            raise Vault__Scoped_Clone_Error('revert --as-commit needs the whole tree; run it from a full clone '
                                            '(or widen this one with sgit fetch <folder>)')
        rev    = Vault__Revision(crypto=self.crypto, api=self.api)
        target = rev.resolve(directory, spec)
        head   = rev.head(directory, c)
        vc     = Vault__Commit(crypto=self.crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
        commit = vc.load_commit(target, c.read_key)
        parents = [str(p) for p in (commit.parents or []) if str(p)]
        if not parents:
            raise Vault__Revision_Error(f'{target} is the first commit; there is nothing before it to go back to')
        if len(parents) > 1:
            raise Vault__Revision_Error(f'{target} is a merge commit; revert the individual commits instead')
        guard = Vault__Ref_Guard(crypto=self.crypto)
        if not guard.is_ancestor(c, c.read_key, target, head):
            raise Vault__Revision_Error(f'{target} is not in this clone\'s history (its head is {head})')
        self._require_clean(directory, 'revert --as-commit')

        sub_tree  = Vault__Sub_Tree(crypto=self.crypto, obj_store=c.obj_store)
        flat      = lambda cid: sub_tree.flatten(str(vc.load_commit(cid, c.read_key).tree_id), c.read_key)
        base_map, ours_map, theirs_map = flat(target), flat(head), flat(parents[0])
        from sgit_ai.core.actions.merge.Vault__Merge import Vault__Merge
        merge  = Vault__Merge(crypto=self.crypto).three_way_merge(base_map, ours_map, theirs_map)
        if merge['conflicts']:
            names = sorted(merge['conflicts'])
            raise Vault__Revision_Error(
                f'cannot revert {target} as a commit: later commits also changed '
                f'{", ".join(names[:10])}{"…" if len(names) > 10 else ""}. Nothing was changed. Edit those '
                f'files by hand (sgit history show {target} shows what it did) and commit.')
        merged = merge['merged_map']
        if {p: e.get('blob_id') for p, e in merged.items()} == {p: e.get('blob_id') for p, e in ours_map.items()}:
            raise Vault__Revision_Error(f'nothing to revert: the changes of {target} are no longer in the head')
        self._checkout_flat_map(directory, merged, c.obj_store, c.read_key)
        self._remove_deleted_flat(directory, ours_map, merged)
        original = ''
        if commit.message_enc:
            try:
                original = self.crypto.decrypt_metadata(c.read_key, str(commit.message_enc))
            except Exception:
                original = ''
        text = message or f'Revert "{(original or target).splitlines()[0][:200]}"\n\nThis reverts commit {target}.'
        from sgit_ai.core.actions.commit.Vault__Sync__Commit import Vault__Sync__Commit
        try:
            result = Vault__Sync__Commit(crypto=self.crypto, api=self.api).commit(directory, message=text)
        except Exception:
            self._checkout_flat_map(directory, ours_map, c.obj_store, c.read_key)    # put the working copy back
            self._remove_deleted_flat(directory, merged, ours_map)
            raise
        return dict(commit_id=result['commit_id'], reverted=target, message=text,
                    files=sorted(set(merged) ^ set(ours_map) |
                                 {p for p in merged if p in ours_map and merged[p].get('blob_id') != ours_map[p].get('blob_id')}))

    # --------------------------------------------------------------- helpers
    def _require_clean(self, directory: str, what: str) -> None:
        from sgit_ai.core.actions.status.Vault__Sync__Status import Vault__Sync__Status
        try:
            status = Vault__Sync__Status(crypto=self.crypto, api=None).status(directory)   # local only
        except Exception as error:
            raise Vault__Revision_Error(f'{what}: could not check the working copy ({error}); nothing was changed')
        if not status.get('clean', True):
            raise Vault__Revision_Error(f'{what} needs a clean working copy: commit your changes or '
                                        f'sgit vault stash them first. Nothing was changed.')
