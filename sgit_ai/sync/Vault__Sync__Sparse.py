"""Vault__Sync__Sparse — sparse checkout operations (Brief 22 — E5-8)."""
import os
from   urllib.request                          import urlopen
from   sgit_ai.crypto.PKI__Crypto              import PKI__Crypto
from   sgit_ai.objects.Vault__Commit           import Vault__Commit
from   sgit_ai.sync.Vault__Sub_Tree            import Vault__Sub_Tree
from   sgit_ai.sync.Vault__Branch_Manager      import Vault__Branch_Manager
from   sgit_ai.sync.Vault__Sync__Base          import Vault__Sync__Base


class Vault__Sync__Sparse(Vault__Sync__Base):

    def _get_head_flat_map(self, directory: str) -> tuple:
        """Return (flat_entries, obj_store, read_key) for the clone branch HEAD."""
        c           = self._init_components(directory)
        storage     = c.storage
        obj_store   = c.obj_store
        ref_manager = c.ref_manager
        read_key    = c.read_key
        pki         = PKI__Crypto()

        local_config = self._read_local_config(directory, storage)
        branch_id    = str(local_config.my_branch_id)
        index_id     = c.branch_index_file_id
        branch_index = c.branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = c.branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            branch_meta = c.branch_manager.get_branch_by_name(branch_index, 'current')
            if not branch_meta:
                return {}, obj_store, read_key, str(c.vault_id), c.sg_dir

        commit_id = ref_manager.read_ref(str(branch_meta.head_ref_id), read_key)
        if not commit_id:
            return {}, obj_store, read_key, str(c.vault_id), c.sg_dir

        vc       = Vault__Commit(crypto=self.crypto, pki=pki,
                                 object_store=obj_store, ref_manager=ref_manager)
        sub_tree = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        commit   = vc.load_commit(commit_id, read_key)
        flat     = sub_tree.flatten(str(commit.tree_id), read_key)
        return flat, obj_store, read_key, str(c.vault_id), c.sg_dir

    def sparse_ls(self, directory: str, path: str = None) -> list:
        """List vault tree entries with local fetch status."""
        flat, obj_store, read_key, vault_id, sg_dir = self._get_head_flat_map(directory)
        prefix  = (path.rstrip('/') + '/') if path else None
        results = []
        for entry_path, entry_data in sorted(flat.items()):
            if prefix and not (entry_path == path or entry_path.startswith(prefix)):
                continue
            blob_id = entry_data.get('blob_id', '')
            results.append(dict(
                path    = entry_path,
                size    = entry_data.get('size', 0),
                blob_id = blob_id,
                fetched = obj_store.exists(blob_id) if blob_id else False,
                large   = bool(entry_data.get('large', False)),
            ))
        return results

    def sparse_fetch(self, directory: str, path: str = None,
                     on_progress: callable = None) -> dict:
        """Fetch file(s) to the local object store and write to working copy."""
        flat, obj_store, read_key, vault_id, sg_dir = self._get_head_flat_map(directory)
        _p = on_progress or (lambda *a, **k: None)

        prefix  = (path.rstrip('/') + '/') if path else None
        entries = []
        for entry_path, entry_data in flat.items():
            if prefix and not (entry_path == path or entry_path.startswith(prefix)):
                continue
            blob_id = entry_data.get('blob_id', '')
            if not blob_id:
                continue
            entries.append(dict(
                path    = entry_path,
                blob_id = blob_id,
                size    = entry_data.get('size', 0),
                large   = bool(entry_data.get('large', False)),
                fetched = obj_store.exists(blob_id),
            ))

        if not entries:
            return dict(fetched=0, already_local=0, written=[])

        to_download   = [e for e in entries if not e['fetched']]
        already_local = len(entries) - len(to_download)

        if to_download:
            LARGE_THRESHOLD = 2 * 1024 * 1024
            small = [e for e in to_download if not e['large'] and e['size'] <= LARGE_THRESHOLD]
            large = [e for e in to_download if e['large'] or e['size'] > LARGE_THRESHOLD]
            total = len(to_download)
            done  = 0
            _p('download', 'Fetching objects', f'0/{total}')

            if small:
                fids = [f'bare/data/{e["blob_id"]}' for e in small]
                for fid, data in self.api.batch_read(vault_id, fids).items():
                    if data:
                        blob_id    = fid.replace('bare/data/', '')
                        local_path = os.path.join(sg_dir, 'bare', 'data', blob_id)
                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                        with open(local_path, 'wb') as f:
                            f.write(data)
                    done += 1
                    _p('download', 'Fetching objects', f'{done}/{total}')

            for e in large:
                fid      = f'bare/data/{e["blob_id"]}'
                url_info = self.api.presigned_read_url(vault_id, fid)
                s3_url   = url_info.get('url') or url_info.get('presigned_url', '')
                with urlopen(s3_url) as resp:
                    data = resp.read()
                local_path = os.path.join(sg_dir, 'bare', 'data', e['blob_id'])
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(data)
                done += 1
                _p('download', 'Fetching objects', f'{done}/{total}')

        written = []
        for e in entries:
            if obj_store.exists(e['blob_id']):
                ciphertext = obj_store.load(e['blob_id'])
                plaintext  = self.crypto.decrypt(read_key, ciphertext)
                full_path  = os.path.join(directory, e['path'])
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'wb') as f:
                    f.write(plaintext)
                written.append(e['path'])

        return dict(fetched=len(to_download), already_local=already_local, written=written)

    def sparse_cat(self, directory: str, path: str) -> bytes:
        """Decrypt and return file content. Fetches blob from server if not locally cached."""
        flat, obj_store, read_key, vault_id, sg_dir = self._get_head_flat_map(directory)
        match = flat.get(path)
        if not match:
            raise RuntimeError(f'File not found in vault: {path}')

        blob_id = match.get('blob_id', '')
        if not blob_id:
            raise RuntimeError(f'No blob stored for: {path}')

        if not obj_store.exists(blob_id):
            fid = f'bare/data/{blob_id}'
            if match.get('large'):
                url_info = self.api.presigned_read_url(vault_id, fid)
                s3_url   = url_info.get('url') or url_info.get('presigned_url', '')
                with urlopen(s3_url) as resp:
                    data = resp.read()
            else:
                data = self.api.read(vault_id, fid)
            if data:
                local_path = os.path.join(sg_dir, 'bare', 'data', blob_id)
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, 'wb') as f:
                    f.write(data)

        if not obj_store.exists(blob_id):
            raise RuntimeError(f'Failed to fetch {path!r} from server')

        ciphertext = obj_store.load(blob_id)
        return self.crypto.decrypt(read_key, ciphertext)
