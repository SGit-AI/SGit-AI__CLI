"""Vault__Sync__Upload_History — fill a gap in the host's history from the clone that holds it (cli.build BR-1).

Builds up to 0.26.8 uploaded at most the newest 100 commits of one push and moved the ref anyway: the older
commits stayed in the pushing clone only, and no later push filled the gap, because a push stops at the remote
head. This walks every commit this clone's refs reach, works out which of them the host does not hold, and
uploads them with their trees and blobs in the vault's own format: loose objects on a loose vault, one commit pack
per missing commit (oldest first) on a pack vault. No ref moves.

What the host holds: a loose vault lists `bare/data/` once. On a pack vault a commit is held when a commit pack is
named after it, when a snapshot pack's commit reaches it (a snapshot carries everything reachable from its commit),
or when it is stored loose. Archived packs are not counted: readers do not look there, and a snapshot
already covers what a compaction archived.
"""
from cryptography.exceptions                                 import InvalidTag
from sgit_ai.core.Vault__Sync__Base                          import Vault__Sync__Base
from sgit_ai.core.actions.fsck.Vault__Sync__Upload_Objects   import Vault__Sync__Upload_Objects
from sgit_ai.core.actions.pack.Vault__Packs                  import Vault__Packs, PACK_COMMITS, PACK_SNAPSHOTS
from sgit_ai.storage.Vault__Commit_Graph                     import Vault__Commit_Graph


class Vault__Sync__Upload_History(Vault__Sync__Base):

    def upload_history(self, directory: str, dry_run: bool = False, on_progress: callable = None) -> dict:
        _p     = on_progress or (lambda *a, **k: None)
        result = dict(ok=True, dry_run=dry_run, pack_vault=False, commits_checked=0, missing_commits=[],
                      uploaded_objects=0, packs=[], errors=[])
        c = self._init_components(directory)
        if not c.write_key and not dry_run:
            result['ok'] = False
            result['errors'].append('No write key — cannot upload (read-only clone)')
            return result

        _p('step', 'Walking this clone\'s history')
        graph = Vault__Commit_Graph(crypto=self.crypto, obj_store=c.obj_store)
        local = set()
        for head in self.local_heads(c):
            local |= graph.reachable(head, c.read_key)
        local = {cid for cid in local if c.obj_store.exists(cid)}          # a shallow boundary's parents are not here
        result['commits_checked'] = len(local)

        _p('step', 'Listing what the host holds')
        packer     = Vault__Packs(crypto=self.crypto, api=self.api)
        pack_vault = packer.is_pack_vault(directory)
        result['pack_vault'] = pack_vault
        try:
            loose = self.host_loose_ids(c.vault_id)
            held  = self.host_pack_commits(packer, graph, c.vault_id, c.read_key, local) if pack_vault else set()
        except Exception as error:
            result['ok'] = False
            result['errors'].append(f'cannot list the host: {error}')
            return result

        missing = sorted(local - loose - held, key=lambda cid: (graph.info(cid, c.read_key)[0], cid))
        result['missing_commits'] = missing
        if dry_run or not missing:
            return result

        if pack_vault:
            result['packs']            = packer.push_packs(directory, c.vault_id, c.write_key, c.read_key, missing, on_progress)
            result['uploaded_objects'] = int(packer.last_pushed_objects)
            return result
        objects = set()
        for cid in missing:
            objects |= set(packer.objects_introduced(c.sg_dir, cid, c.read_key))
        objects = sorted(oid for oid in objects - loose if c.obj_store.exists(oid))
        upload  = Vault__Sync__Upload_Objects(crypto=self.crypto, api=self.api).upload_objects(directory, objects, on_progress)
        result['uploaded_objects'] = len(upload['uploaded'])
        if not upload['ok']:
            result['ok'] = False
            result['errors'].extend(upload['errors'])
        return result

    def local_heads(self, c) -> list:
        heads = []
        for ref_id in c.ref_manager.list_refs():
            try:
                head = c.ref_manager.read_ref(ref_id, c.read_key)
            except (ValueError, OSError, InvalidTag):                       # an unreadable ref names no commit here
                continue
            if head:
                heads.append(head)
        return heads

    def host_loose_ids(self, vault_id: str) -> set:
        return {str(fid).rsplit('/', 1)[-1] for fid in (self.api.list_files(vault_id, 'bare/data/') or [])
                if str(fid).rsplit('/', 1)[-1].startswith('obj-cas-imm-')}

    def host_pack_commits(self, packer, graph, vault_id: str, read_key: bytes, local: set) -> set:
        held = {entry['commit_id'] for entry in packer.list_folder(vault_id, PACK_COMMITS)}
        for entry in packer.list_folder(vault_id, PACK_SNAPSHOTS):
            if entry['commit_id'] in local:
                held |= graph.reachable(entry['commit_id'], read_key)
        return held
