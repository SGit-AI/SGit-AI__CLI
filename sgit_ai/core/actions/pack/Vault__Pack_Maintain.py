"""Vault__Pack_Maintain — what keeps a pack vault's host folder small and honest.

  compact  one snapshot of the current head to snapshots/; the commit packs it
           absorbs, the snapshots it supersedes and the orphan commit packs older
           than a day move to archive/. Each move is copy, verify by listing, then
           delete the original. Nothing is deleted without its copy in archive/.
  ls       the three folders as the host lists them
  verify   every pack on the host, member by member, against the content address
  stats    counts and bytes on the host, and the local blob compression ratio

Compaction is idempotent and only runs on a clean clone whose named head is the
host's: a stale clone would snapshot an old head. Every pack name carries its
size, so a copy is verified by the listing alone (name + size), and a pack that
has to be rebuilt (archive move from a clone that holds its objects) is byte-
identical to the original because packs are deterministic.
"""
import io
import json
import os
import re
import time
import zipfile

from sgit_ai.core.actions.pack.Vault__Packs      import (Vault__Packs, PACK_COMMITS, PACK_SNAPSHOTS, PACK_ARCHIVE,
                                                         PACK_ORPHAN_AGE_S, PACK_COMPACT_COUNT, PACK_COMPACT_RATIO)
from sgit_ai.crypto.Vault__Crypto                import DEFLATE_MAGIC
from sgit_ai.storage.Vault__Object_Store         import Vault__Object_Store
from sgit_ai.storage.Vault__Storage              import SG_VAULT_DIR


class Vault__Pack_Maintain(Vault__Packs):
    last_deleted      : int = 0              # originals this compaction removed after their archive copy was listed
    last_already_gone : int = 0              # originals another compaction had removed first (a 404 on the delete)

    def _require_pack_clone(self, directory: str):
        c = self._init_components(directory)
        if not self.pack_vault:
            raise RuntimeError(f'{directory} is not a pack vault (branch-index feature "packs" absent)')
        return c

    def _named_head(self, directory: str, c) -> tuple:
        config = self._read_local_config(directory, c.storage)
        index  = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        meta   = c.branch_manager.tracked_named_branch(index, str(config.my_branch_id or ''))
        if meta is None or not meta.head_ref_id:
            raise RuntimeError('no named branch to compact')
        return str(meta.head_ref_id), c.ref_manager.read_ref(str(meta.head_ref_id), c.read_key)

    # ------------------------------------------------------------------ ls / stats
    def ls(self, directory: str) -> dict:
        c = self._require_pack_clone(directory)
        return dict(commits   = self.list_folder(c.vault_id, PACK_COMMITS),
                    snapshots = self.list_folder(c.vault_id, PACK_SNAPSHOTS),
                    archive   = self.list_folder(c.vault_id, PACK_ARCHIVE),
                    absorbed  = sorted(self.load_absorbed(directory)))

    def stats(self, directory: str) -> dict:
        """Host: packs and bytes per folder, loose objects (must be 0). Local: blobs,
        how many are deflated, and the plaintext-to-ciphertext ratio of the store."""
        c      = self._require_pack_clone(directory)
        listed = self.ls(directory)
        host   = {k: dict(packs=len(v), bytes=sum(e['size'] for e in v)) for k, v in listed.items() if k != 'absorbed'}
        index  = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        tag_ids = {str(t.tag_id) for t in (getattr(index, 'tags', None) or []) if getattr(t, 'tag_id', None)}
        loose  = [str(f) for f in (self.api.list_files(c.vault_id, 'bare/data/') or [])]
        host['tag_objects']   = len([f for f in loose if f.rsplit('/', 1)[-1] in tag_ids])   # tags stay loose, by design
        host['loose_objects'] = len(loose) - host['tag_objects']
        sg_dir   = os.path.join(directory, SG_VAULT_DIR)
        store    = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        data_dir = os.path.join(sg_dir, 'bare', 'data')
        local    = dict(objects=0, deflated=0, cipher_bytes=0, plain_bytes=0, blobs=0)
        _, head  = self._named_head(directory, c)
        blob_ids = set()
        for cid in self.reachable_commits(sg_dir, head, c.read_key):
            blob_ids |= self._blob_ids_of_commit(sg_dir, cid, c.read_key)
        for name in os.listdir(data_dir) if os.path.isdir(data_dir) else []:
            if not name.startswith('obj-cas-imm-'):
                continue
            local['objects'] += 1
            cipher = store.load(name)
            if name in blob_ids:
                local['blobs']        += 1
                local['cipher_bytes'] += len(cipher)
                if cipher[:len(DEFLATE_MAGIC)] == DEFLATE_MAGIC:
                    local['deflated'] += 1
                try:
                    local['plain_bytes'] += len(self.crypto.decrypt(c.read_key, cipher))
                except Exception:
                    local['unreadable'] = local.get('unreadable', 0) + 1
        local['ratio'] = round(local['plain_bytes'] / local['cipher_bytes'], 3) if local['cipher_bytes'] else 1.0
        return dict(vault_id=c.vault_id, host=host, local=local, head=head)

    def _blob_ids_of_commit(self, sg_dir: str, commit_id: str, read_key: bytes) -> set:
        """Blobs under a commit's tree, through the memoised tree walk (a flatten per
        commit took 14 minutes on the comms vault's 1,229 commits)."""
        try:
            commit = self._vault_commit(sg_dir).load_commit(commit_id, read_key)
        except Exception:
            return set()
        return set(self.tree_blobs(sg_dir, str(commit.tree_id), read_key)) if commit.tree_id else set()

    # ------------------------------------------------------------------ verify
    def server_heads(self, c) -> tuple:
        """(heads, unreadable): the commit each ref on the host names (named and clone
        branches alike: a branch-only push is a ref too), and the refs that could not
        be read. Reachability for compaction starts from ALL of them."""
        heads, unreadable = set(), []
        try:
            refs = [str(f) for f in (self.api.list_files(c.vault_id, 'bare/refs/') or []) if str(f).startswith('bare/refs/')]
        except Exception as error:
            raise RuntimeError(f'could not list the refs on the server ({error}); nothing was changed')
        got = self.api.batch_read(c.vault_id, refs) if refs else {}
        for fid in refs:
            data = got.get(fid)
            head = ''
            if data:
                try:
                    head = json.loads(self.crypto.decrypt(c.read_key, data)).get('commit_id') or ''
                except Exception:
                    head = ''
            if head:
                heads.add(str(head))
            else:
                unreadable.append(fid)
        return heads, unreadable

    def verify(self, directory: str, folders: tuple = (PACK_COMMITS, PACK_SNAPSHOTS, PACK_ARCHIVE)) -> dict:
        """Fetch every pack and check each member hashes to its id. Returns per pack
        the member count and the members that failed; never writes anything."""
        c      = self._require_pack_clone(directory)
        report = dict(packs=0, members=0, bad=[], sizes_wrong=[])
        for folder in folders:
            for entry in self.list_folder(c.vault_id, folder):
                try:
                    data = self.fetch_pack(c.vault_id, entry)
                except Exception as error:
                    report['sizes_wrong'].append(dict(name=entry['name'], error=str(error)))
                    continue
                report['packs'] += 1
                try:
                    opened = zipfile.ZipFile(io.BytesIO(data))
                except zipfile.BadZipFile as error:
                    report['bad'].append(dict(pack=entry['name'], member=f'(not a zip: {error})'))
                    continue
                with opened as pack:
                    infos = pack.infolist()
                    if len({i.filename for i in infos}) != len(infos):
                        report['bad'].append(dict(pack=entry['name'], member='(duplicate member names)'))
                        continue
                    for info in infos:
                        report['members'] += 1
                        member = info.filename
                        oid    = member.rsplit('/', 1)[-1]
                        why    = self.member_is_safe(info, len(data))
                        if why:
                            report['bad'].append(dict(pack=entry['name'], member=f'{member} ({why})'))
                        elif self.crypto.compute_object_id(pack.read(info), len(oid) - len('obj-cas-imm-')) != oid:
                            report['bad'].append(dict(pack=entry['name'], member=member))
        report['ok'] = not report['bad'] and not report['sizes_wrong']
        return report

    # ------------------------------------------------------------------ compact
    def needs_compaction(self, directory: str) -> bool:
        listed    = self.ls(directory)
        commits   = listed['commits']
        snapshots = listed['snapshots']
        if not snapshots:
            return bool(commits)
        newest = snapshots[-1]['size'] or 1
        return len(commits) > PACK_COMPACT_COUNT or sum(e['size'] for e in commits) > PACK_COMPACT_RATIO * newest

    def compact(self, directory: str, dry_run: bool = False, on_progress=None, now: int = None) -> dict:
        _p       = on_progress or (lambda *a, **k: None)
        c        = self._require_pack_clone(directory)
        if not c.write_key:
            raise RuntimeError('compaction writes to the host: this clone has no write key (a read-only clone)')
        sg_dir   = os.path.join(directory, SG_VAULT_DIR)
        now      = int(time.time()) if now is None else int(now)
        ref_id, head = self._named_head(directory, c)
        server_head  = self._server_named_commit_id(c.vault_id, ref_id, c.read_key)
        if server_head is None:
            raise RuntimeError('could not read the named branch on the server; nothing was changed')
        if server_head != head:
            raise RuntimeError(f'this clone\'s named head ({head[:20]}…) is not the server\'s ({server_head[:20]}…): '
                               f'run `sgit pull` first, then compact')
        from sgit_ai.core.actions.status.Vault__Sync__Status import Vault__Sync__Status
        if not Vault__Sync__Status(crypto=self.crypto, api=self.api).status(directory).get('clean', True):
            raise RuntimeError('working directory has uncommitted changes; commit or stash them, then compact')

        # the packs this clone has not absorbed: it cannot judge them, so bring them first
        self.sync_down(directory, c.vault_id, c.read_key, _p, head=head)

        # reachability starts from every ref on the host, not this clone's branch alone: a
        # branch-only push or another named branch is history too, and its packs stay
        heads, unreadable = self.server_heads(c)
        heads.add(head)
        reachable = set()
        unjudged  = list(unreadable)
        for h in heads:
            if not os.path.isfile(os.path.join(sg_dir, 'bare', 'data', h)):
                unjudged.append(h)                                            # a head this clone does not hold
            reachable |= self.reachable_commits(sg_dir, h, c.read_key)
        on_branch = self.reachable_commits(sg_dir, head, c.read_key)          # what the snapshot will carry
        listed    = self.ls(directory)
        plan      = dict(snapshot=None, absorbed=[], superseded=[], orphans=[], kept=[], head=head,
                         unjudged=unjudged)
        existing  = next((s for s in listed['snapshots'] if s['commit_id'] == head), None)   # ANY snapshot of this
        if existing:                                                           # head, not only the newest by name:
            plan['snapshot'] = dict(name=existing['name'], existing=True)      # two written in the same second sort
        else:                                                                  # by commit hex, which says nothing
            plan['snapshot'] = dict(name=None, existing=False)
        for e in listed['commits']:
            if e['commit_id'] in on_branch:
                plan['absorbed'].append(e)
            elif e['commit_id'] in reachable or unjudged:                     # another ref's history, or one we cannot judge
                plan['kept'].append(e)
            elif now - e['epoch'] > PACK_ORPHAN_AGE_S:
                plan['orphans'].append(e)
            else:
                plan['kept'].append(e)
        plan['superseded'] = [e for e in listed['snapshots']                  # only snapshots this head descends from:
                              if e['commit_id'] != head and e['commit_id'] in on_branch]   # a newer one is never ours to move
        if unjudged:
            _p('warning', 'Orphan packs are not archived this run',
               f'{len(unjudged)} ref(s) on the host name commits this clone cannot read or does not hold')
        if dry_run:
            return dict(plan=plan, dry_run=True, moved=0)

        work_dir = os.path.join(sg_dir, 'work', 'packs')
        os.makedirs(work_dir, exist_ok=True)
        # 1. the snapshot (built from the loose store; its name carries its size)
        uploaded = None
        if not plan['snapshot']['existing']:
            path, name = self.build_snapshot_pack(sg_dir, head, c.read_key, work_dir)
            if self._server_named_commit_id(c.vault_id, ref_id, c.read_key) != head:    # moved while we built it
                os.remove(path)
                raise RuntimeError('the named branch moved while compacting; nothing was written. '
                                   'Pull and run `sgit pack compact` again.')
            _p('step', 'Uploading snapshot', f'{name} ({os.path.getsize(path) / 1e6:.2f} MB)')
            self.upload_pack(c.vault_id, c.write_key, PACK_SNAPSHOTS + name, path, _p)
            self._assert_listed(c.vault_id, PACK_SNAPSHOTS, name)
            os.remove(path)
            self._write_index_after(directory, c.vault_id, c.write_key, c.read_key, PACK_SNAPSHOTS, name, head, _p)
            self.record_absorbed(directory, [name])
            plan['snapshot']['name'] = name
            uploaded = name
        # 2. moves: copy to archive/, verify by listing, delete the original — but only if the
        # branch is still where this clone saw it: a compaction that ran meanwhile wrote a newer
        # snapshot this clone must not touch
        self._moves_about_to_start(c)
        if self._server_named_commit_id(c.vault_id, ref_id, c.read_key) != head:
            # the snapshot just written stays: another compaction of the same head may have adopted it
            # (same name, by determinism) and archived the packs it absorbs, so deleting it here would
            # delete the only live copy (round-3 review R1). A stray snapshot costs storage until the
            # next compaction archives it; clones choose their snapshot by the branch head, never by name.
            raise RuntimeError('the named branch moved while compacting: nothing was archived'
                               + (f' (the snapshot {uploaded} stays on the host)' if uploaded else '')
                               + '. Pull and run `sgit pack compact` again.')
        moved = 0
        self.last_deleted, self.last_already_gone = 0, 0
        for kind in ('absorbed', 'superseded', 'orphans'):
            for e in plan[kind]:
                self._move_to_archive(c, sg_dir, e, work_dir, _p)
                moved += 1
        already = int(self.last_already_gone)
        _p('step', 'Compacted', f'snapshot {plan["snapshot"]["name"]}; {moved} pack(s) archived'
                                + (f' ({already} already in archive)' if already else ''))
        return dict(plan=plan, dry_run=False, moved=moved, already_archived=already, snapshot=plan['snapshot']['name'])

    def _moves_about_to_start(self, c) -> None:
        """A seam for tests: runs between the snapshot upload and the head re-check."""

    def _assert_listed(self, vault_id: str, folder: str, name: str) -> dict:
        for e in self.list_folder(vault_id, folder):
            if e['name'] == name:
                return e
        raise RuntimeError(f'{folder}{name}: uploaded but not listed by the host; nothing was deleted')

    def _move_to_archive(self, c, sg_dir: str, entry: dict, work_dir: str, _p) -> None:
        """archive/<same name>: rebuilt from the loose store when every object is here
        (deterministic, so byte-identical), else fetched from the host; then verified
        by the listing and only then removed from its folder."""
        name = entry['name']
        if any(e['name'] == name for e in self.list_folder(c.vault_id, PACK_ARCHIVE)):
            self._delete_original(c, entry['file_id'])                        # the copy is already there
            return
        path = os.path.join(work_dir, 'archive-' + name)
        data = None
        try:
            if entry['file_id'].startswith(PACK_SNAPSHOTS):
                size = self.write_pack(sg_dir, self.reachable_objects(sg_dir, entry['commit_id'], c.read_key), path)
            else:
                size = self.write_pack(sg_dir, self.objects_introduced(sg_dir, entry['commit_id'], c.read_key), path)
            if size != entry['size']:
                data = self.fetch_pack(c.vault_id, entry)
        except Exception:
            data = self.fetch_pack(c.vault_id, entry)
        if data is not None:
            with open(path, 'wb') as f:
                f.write(data)
        _p('step', 'Archiving pack', name)
        self.upload_pack(c.vault_id, c.write_key, PACK_ARCHIVE + name, path, _p)
        self._assert_listed(c.vault_id, PACK_ARCHIVE, name)
        os.remove(path)
        self._delete_original(c, entry['file_id'])
        self._archive_index_pack(c, entry, work_dir, _p)

    def _archive_index_pack(self, c, entry: dict, work_dir: str, _p) -> None:
        """The index pack of a data pack just archived moves with it (indexes/archive/,
        same copy-verify-delete sequence). An index pack is derived: a failure here is a
        warning, and an index whose data pack is gone is deleted by the next run."""
        from sgit_ai.core.actions.pack.Vault__Pack_Index import Vault__Pack_Index, PACK_INDEX_ARCHIVE
        try:
            indexer = Vault__Pack_Index(crypto=self.crypto, api=self.api)
            folder  = PACK_SNAPSHOTS if entry['file_id'].startswith(PACK_SNAPSHOTS) else PACK_COMMITS
            index   = indexer.index_pack_for(c.vault_id, folder, entry)
            if index is None:
                return
            name = index['name']
            if not any(e['name'] == name for e in self.list_folder(c.vault_id, PACK_INDEX_ARCHIVE)):
                path = os.path.join(work_dir, 'archive-index-' + name)
                with open(path, 'wb') as f:
                    f.write(self.fetch_pack(c.vault_id, index))
                self.upload_pack(c.vault_id, c.write_key, PACK_INDEX_ARCHIVE + name, path, _p)
                self._assert_listed(c.vault_id, PACK_INDEX_ARCHIVE, name)
                os.remove(path)
            self._delete_original(c, index['file_id'])
        except Exception as error:
            _p('warning', 'Index pack not archived with its data pack', f'{entry["name"]}: {str(error)[:120]}')

    def _delete_original(self, c, file_id: str) -> None:
        """The original of a pack whose archive copy the host lists. A 404 is success:
        another compaction of the same head deleted it first (round-3 review R3)."""
        try:
            self.api.delete(c.vault_id, file_id, c.write_key)
            self.last_deleted += 1
        except Exception as error:
            if self._is_not_found(error):
                self.last_already_gone += 1
                return
            raise

    def _is_not_found(self, error: Exception) -> bool:
        """By the status code the error carries, never by a substring of its text: a pack
        name is full of digits, so '404' can sit inside an epoch or a size (round 4, nit 1)."""
        from urllib.error import HTTPError
        code = getattr(error, 'code', None) if isinstance(error, HTTPError) else getattr(error, 'status', None)
        if code is None:
            cause = getattr(error, '__cause__', None)
            if isinstance(cause, HTTPError):
                code = cause.code
        if code is not None:
            return int(code) == 404
        return bool(re.match(r'^(API Error: )?HTTP 404\b', str(error)))    # the in-memory host and older messages: the
                                                                             # status at the start of the text, not inside it
