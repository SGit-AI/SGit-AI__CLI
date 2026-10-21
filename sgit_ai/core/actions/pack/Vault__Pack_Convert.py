"""Vault__Pack_Convert — the round trip between a normal vault and a pack vault.

`import`: a full clone of a normal vault becomes a NEW pack vault (its own vault key,
features 'packs' + 'blob-deflate', min_client = this client). `export`: a pack-vault
clone becomes a NEW normal vault. Both are the same rewrite, move-style: every
object reachable from the clone's HEAD is decrypted with the source key and written
again under the target key, bottom-up, so every id is still the content address of
its bytes (blobs deflated or not per the target; trees deterministic; commits
re-signed with the target clone's key, keeping message and timestamp). The source
is never touched. The target is a local vault that has not been pushed: `sgit push`
in it does the first push (one snapshot pack, or loose objects), and the vault id
and key are the target's own, so the two vaults never share a host folder.

Only the current branch's history travels (the clone's HEAD and its ancestors):
other named branches, tags and cache objects stay in the source. v1.
"""
import json
import os
import time

from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.core.Vault__Sync__Base              import Vault__Sync__Base
from sgit_ai.crypto.PKI__Crypto                  import PKI__Crypto
from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto, DEFLATE_MAGIC
from sgit_ai.schemas.Schema__Object_Tree         import Schema__Object_Tree
from sgit_ai.schemas.Schema__Object_Tree_Entry   import Schema__Object_Tree_Entry
from sgit_ai.storage.Vault__Commit               import Vault__Commit
from sgit_ai.storage.Vault__Object_Store         import Vault__Object_Store
from sgit_ai.storage.Vault__Ref_Manager          import Vault__Ref_Manager
from sgit_ai.storage.Vault__Storage              import Vault__Storage, SG_VAULT_DIR
from sgit_ai.storage.Vault__Sub_Tree             import Vault__Sub_Tree, LARGE_BLOB_THRESHOLD


class Vault__Pack_Convert(Vault__Sync__Base):

    def head_of(self, directory: str) -> dict:
        """The clone's HEAD commit and the keys/managers of a source clone."""
        c       = self._init_components(directory)
        config  = self._read_local_config(directory, c.storage)
        index   = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        meta    = c.branch_manager.get_branch_by_id(index, str(config.my_branch_id or ''))
        if meta is None:
            meta = c.branch_manager.tracked_named_branch(index, str(config.my_branch_id or ''))
        if meta is None or not meta.head_ref_id:
            raise RuntimeError(f'{directory}: no branch head to convert from')
        head = c.ref_manager.read_ref(str(meta.head_ref_id), c.read_key)
        if not head:
            raise RuntimeError(f'{directory}: the branch has no commits')
        return dict(components=c, head=head, index=index)

    def convert(self, source_dir: str, target_dir: str, packs: bool, vault_key: str = None,
                deflate: bool = None, on_progress=None) -> dict:
        """Rewrite source_dir's HEAD history into a fresh vault at target_dir. packs=True
        makes a pack vault (import), False a normal vault (export). deflate defaults
        to packs. Returns the stats of the rewrite."""
        from sgit_ai.core.Vault__Sync import Vault__Sync
        _p       = on_progress or (lambda *a, **k: None)
        deflate  = packs if deflate is None else bool(deflate)
        t0       = time.monotonic()
        source   = self.head_of(source_dir)
        sc       = source['components']
        src_key  = sc.read_key
        src_store= sc.obj_store
        src_vc   = Vault__Commit(crypto=self.crypto, pki=sc.pki, object_store=src_store, ref_manager=sc.ref_manager)
        src_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=src_store)

        if os.path.isdir(os.path.join(target_dir, SG_VAULT_DIR)):
            raise RuntimeError(f'{target_dir} is already a vault')
        _p('step', 'Creating the target vault', 'pack vault' if packs else 'normal vault')
        target_crypto = Vault__Crypto()
        target_sync   = Vault__Sync(crypto=target_crypto, api=self.api)
        created       = target_sync.init(target_dir, vault_key=vault_key, packs=packs, deflate=deflate, allow_nonempty=True)
        tc            = target_sync._init_components(target_dir)                     # sets deflate_blobs from the index
        target_crypto.deflate_blobs = deflate
        tgt_key       = tc.read_key
        tgt_store     = tc.obj_store
        tgt_vc        = Vault__Commit(crypto=target_crypto, pki=tc.pki, object_store=tgt_store, ref_manager=tc.ref_manager)
        tgt_tree      = Vault__Sub_Tree(crypto=target_crypto, obj_store=tgt_store)
        config        = self._read_local_config(target_dir, tc.storage)
        clone_meta    = tc.branch_manager.get_branch_by_id(
            tc.branch_manager.load_branch_index(target_dir, tc.branch_index_file_id, tgt_key), str(config.my_branch_id))
        signing_key   = tc.key_manager.load_private_key_locally(str(clone_meta.public_key_id), tc.storage.local_dir(target_dir))

        stats = dict(commits=0, trees=0, blobs=0, blobs_reused=0, deflated=0, missing=[],
                     blob_plain_bytes=0, blob_cipher_bytes_source=0, blob_cipher_bytes_target=0)
        blob_map, tree_map, commit_map = {}, {}, {}

        def convert_blob(old_id: str) -> tuple:
            if old_id in blob_map:
                stats['blobs_reused'] += 1
                return blob_map[old_id]
            if not src_store.exists(old_id):                 # a reference the source cannot resolve either (an
                stats['missing'].append(old_id)              # older version never uploaded): carried as it is,
                blob_map[old_id] = (old_id, False)           # so that commit stays exactly as readable as before
                return blob_map[old_id]
            cipher    = src_store.load(old_id)
            plaintext = self.crypto.decrypt(src_key, cipher)
            new_cipher= target_crypto.encrypt(tgt_key, plaintext, deflate=True)
            new_id    = tgt_store.store(new_cipher)
            stats['blobs'] += 1
            stats['blob_plain_bytes']         += len(plaintext)
            stats['blob_cipher_bytes_source'] += len(cipher)
            stats['blob_cipher_bytes_target'] += len(new_cipher)
            if new_cipher[:len(DEFLATE_MAGIC)] == DEFLATE_MAGIC:
                stats['deflated'] += 1
            blob_map[old_id] = (new_id, len(new_cipher) > LARGE_BLOB_THRESHOLD)
            return blob_map[old_id]

        def convert_tree(old_id: str) -> str:
            if old_id in tree_map:
                return tree_map[old_id]
            if not src_store.exists(old_id):
                stats['missing'].append(old_id)
                tree_map[old_id] = old_id
                return old_id
            tree    = src_tree._load_tree(old_id, src_key)
            entries = []
            for e in tree.entries:
                new = Schema__Object_Tree_Entry()
                for field in ('name_enc', 'size_enc', 'content_hash_enc', 'content_type_enc'):
                    value = getattr(e, field)
                    if value:
                        plain = self.crypto.decrypt_metadata(src_key, str(value))
                        setattr(new, field, target_crypto.encrypt_metadata_deterministic(tgt_key, plain))
                if e.blob_id:
                    new_id, large = convert_blob(str(e.blob_id))
                    new.blob_id = new_id
                    new.large   = large
                if e.tree_id:
                    new.tree_id = convert_tree(str(e.tree_id))
                entries.append(new)
            new_tree = Schema__Object_Tree(schema=str(tree.schema or 'tree_v1'), entries=entries)
            new_id   = tgt_tree._store_tree(new_tree, tgt_key)
            tree_map[old_id] = new_id
            stats['trees'] += 1
            return new_id

        def convert_commit(old_id: str) -> str:
            if old_id in commit_map:
                return commit_map[old_id]
            commit  = src_vc.load_commit(old_id, src_key)
            parents = [convert_commit(str(p)) for p in (commit.parents or []) if str(p)]
            tree_id = convert_tree(str(commit.tree_id))
            message = ''
            if commit.message_enc:
                try:
                    message = self.crypto.decrypt_metadata(src_key, str(commit.message_enc))
                except Exception:
                    message = ''
            new_id = tgt_vc.create_commit(read_key      = tgt_key,
                                          tree_id       = tree_id,
                                          parent_ids    = parents,
                                          message       = message,
                                          branch_id     = str(clone_meta.branch_id),
                                          signing_key   = signing_key,
                                          timestamp_ms  = int(commit.timestamp_ms) if commit.timestamp_ms else None,
                                          author_key_id = str(clone_meta.public_key_id))
            commit_map[old_id] = new_id
            stats['commits'] += 1
            if stats['commits'] % 50 == 0:
                _p('step', 'Rewriting commits', f'{stats["commits"]} done, {stats["blobs"]} blobs')
            return new_id

        # commits parents-first, without recursion on long histories
        order, seen, stack = [], set(), [source['head']]
        while stack:
            cid = stack[-1]
            if cid in seen:
                stack.pop(); continue
            parents = [str(p) for p in (src_vc.load_commit(cid, src_key).parents or []) if str(p)]
            missing = [p for p in parents if p not in seen]
            if missing:
                stack.extend(missing); continue
            seen.add(cid); order.append(cid); stack.pop()
        _p('step', 'Rewriting the object graph', f'{len(order)} commit(s) from {source["head"]}')
        for cid in order:
            convert_commit(cid)
        new_head = commit_map[source['head']]

        # both refs point at the new head: the history is the vault's, not work on top of
        # it, so status says "never pushed", not "N ahead, 1 behind" (review 10/21 UX);
        # the first `sgit push` sees a host with no ref and uploads everything
        index      = tc.branch_manager.load_branch_index(target_dir, tc.branch_index_file_id, tgt_key)
        named_meta = tc.branch_manager.tracked_named_branch(index, str(config.my_branch_id))
        tc.ref_manager.write_ref(str(named_meta.head_ref_id), new_head, tgt_key)
        tc.ref_manager.write_ref(str(clone_meta.head_ref_id), new_head, tgt_key)

        _p('step', 'Writing the working copy')
        head_commit = tgt_vc.load_commit(new_head, tgt_key)
        tgt_tree.checkout(target_dir, str(head_commit.tree_id), tgt_key)

        stats.update(source_head=source['head'], target_head=new_head, target_dir=target_dir,
                     vault_id=created['vault_id'], vault_key=created['vault_key'],
                     packs=packs, deflate=deflate, elapsed_s=round(time.monotonic() - t0, 3))
        ratio = (stats['blob_cipher_bytes_source'] / stats['blob_cipher_bytes_target']) if stats['blob_cipher_bytes_target'] else 1.0
        stats['blob_ratio'] = round(ratio, 3)
        if stats['missing']:
            _p('warning', 'References the source could not resolve were carried unchanged',
               f'{len(stats["missing"])} object(s); those historical files stay missing, as in the source')
        _p('step', 'Converted', f'{stats["commits"]} commits, {stats["trees"]} trees, {stats["blobs"]} blobs '
                                f'({stats["blob_cipher_bytes_source"] / 1e6:.1f} MB -> {stats["blob_cipher_bytes_target"] / 1e6:.1f} MB, '
                                f'x{ratio:.2f}) in {stats["elapsed_s"]:.1f}s')
        return stats
