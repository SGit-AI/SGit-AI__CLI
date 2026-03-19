import json
import mimetypes
import os
from   osbot_utils.type_safe.Type_Safe                import Type_Safe
from   sg_send_cli.crypto.Vault__Crypto               import Vault__Crypto
from   sg_send_cli.objects.Vault__Object_Store        import Vault__Object_Store
from   sg_send_cli.schemas.Schema__Object_Tree        import Schema__Object_Tree
from   sg_send_cli.schemas.Schema__Object_Tree_Entry  import Schema__Object_Tree_Entry


class Vault__Sub_Tree(Type_Safe):
    """Build and traverse sub-tree structures.

    Stored tree entries contain ONLY encrypted metadata:
      blob_id/tree_id + name_enc + size_enc + content_hash_enc + content_type_enc

    Plaintext values (path, name, size, content_hash, content_type) exist only
    in-memory as dicts returned by flatten() — never serialized.
    """
    crypto    : Vault__Crypto
    obj_store : Vault__Object_Store

    def build(self, directory: str, file_map: dict, read_key: bytes,
              old_flat_entries: dict = None) -> str:
        """Build sub-tree objects bottom-up from working directory files.

        Returns root tree object ID (obj-cas-imm-{hash}).
        """
        if old_flat_entries is None:
            old_flat_entries = {}

        dir_contents = {}
        all_dirs     = set()

        for rel_path in sorted(file_map.keys()):
            parts = rel_path.split('/')
            if len(parts) == 1:
                dir_contents.setdefault('', []).append((parts[0], rel_path))
            else:
                dir_path = '/'.join(parts[:-1])
                filename = parts[-1]
                dir_contents.setdefault(dir_path, []).append((filename, rel_path))
                for i in range(1, len(parts)):
                    all_dirs.add('/'.join(parts[:i]))

        for d in all_dirs:
            dir_contents.setdefault(d, [])
        dir_contents.setdefault('', [])

        tree_ids = {}
        sorted_dirs = sorted(dir_contents.keys(),
                             key=lambda p: (-p.count('/') if p else 1, p))

        for dir_path in sorted_dirs:
            entries = []

            for filename, rel_path in sorted(dir_contents[dir_path], key=lambda x: x[0]):
                if rel_path not in file_map:
                    continue
                local_file = os.path.join(directory, rel_path)
                if not os.path.isfile(local_file):
                    continue

                with open(local_file, 'rb') as f:
                    content = f.read()

                file_hash = self.crypto.content_hash(content)
                old_entry = old_flat_entries.get(rel_path)
                if old_entry and old_entry.get('content_hash', '') == file_hash and old_entry.get('blob_id'):
                    blob_id = old_entry['blob_id']
                else:
                    encrypted = self.crypto.encrypt(read_key, content)
                    blob_id   = self.obj_store.store(encrypted)

                content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                entries.append(Schema__Object_Tree_Entry(
                    blob_id          = blob_id,
                    name_enc         = self.crypto.encrypt_metadata(read_key, filename),
                    size_enc         = self.crypto.encrypt_metadata(read_key, str(len(content))),
                    content_hash_enc = self.crypto.encrypt_metadata(read_key, file_hash),
                    content_type_enc = self.crypto.encrypt_metadata(read_key, content_type),
                ))

            for child_dir in sorted(all_dirs):
                if dir_path == '':
                    if '/' not in child_dir:
                        folder_name = child_dir
                    else:
                        continue
                elif child_dir.startswith(dir_path + '/'):
                    remainder = child_dir[len(dir_path) + 1:]
                    if '/' not in remainder:
                        folder_name = remainder
                    else:
                        continue
                else:
                    continue

                if child_dir in tree_ids:
                    entries.append(Schema__Object_Tree_Entry(
                        tree_id  = tree_ids[child_dir],
                        name_enc = self.crypto.encrypt_metadata(read_key, folder_name),
                    ))

            tree_obj = Schema__Object_Tree(schema='tree_v1', entries=entries)
            tree_id  = self._store_tree(tree_obj, read_key)
            tree_ids[dir_path] = tree_id

        return tree_ids.get('', '')

    def build_from_flat(self, flat_map: dict, read_key: bytes) -> str:
        """Build sub-tree objects from a flat {path: dict} map.

        Used after merge — blobs already exist in the object store,
        we just need to construct the tree structure with encrypted metadata.

        Returns root tree object ID.
        """
        dir_contents = {}
        all_dirs     = set()

        for rel_path in sorted(flat_map.keys()):
            parts = rel_path.split('/')
            if len(parts) == 1:
                dir_contents.setdefault('', []).append((parts[0], rel_path))
            else:
                dir_path = '/'.join(parts[:-1])
                filename = parts[-1]
                dir_contents.setdefault(dir_path, []).append((filename, rel_path))
                for i in range(1, len(parts)):
                    all_dirs.add('/'.join(parts[:i]))

        for d in all_dirs:
            dir_contents.setdefault(d, [])
        dir_contents.setdefault('', [])

        tree_ids = {}
        sorted_dirs = sorted(dir_contents.keys(),
                             key=lambda p: (-p.count('/') if p else 1, p))

        for dir_path in sorted_dirs:
            entries = []

            for filename, rel_path in sorted(dir_contents[dir_path], key=lambda x: x[0]):
                entry_data = flat_map.get(rel_path)
                if not entry_data:
                    continue

                content_type = entry_data.get('content_type', '') or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                entries.append(Schema__Object_Tree_Entry(
                    blob_id          = entry_data['blob_id'],
                    name_enc         = self.crypto.encrypt_metadata(read_key, filename),
                    size_enc         = self.crypto.encrypt_metadata(read_key, str(entry_data.get('size', 0))),
                    content_hash_enc = self.crypto.encrypt_metadata(read_key, entry_data.get('content_hash', '')),
                    content_type_enc = self.crypto.encrypt_metadata(read_key, content_type),
                ))

            for child_dir in sorted(all_dirs):
                if dir_path == '':
                    if '/' not in child_dir:
                        folder_name = child_dir
                    else:
                        continue
                elif child_dir.startswith(dir_path + '/'):
                    remainder = child_dir[len(dir_path) + 1:]
                    if '/' not in remainder:
                        folder_name = remainder
                    else:
                        continue
                else:
                    continue

                if child_dir in tree_ids:
                    entries.append(Schema__Object_Tree_Entry(
                        tree_id  = tree_ids[child_dir],
                        name_enc = self.crypto.encrypt_metadata(read_key, folder_name),
                    ))

            tree_obj = Schema__Object_Tree(schema='tree_v1', entries=entries)
            tree_id  = self._store_tree(tree_obj, read_key)
            tree_ids[dir_path] = tree_id

        return tree_ids.get('', '')

    def flatten(self, tree_id: str, read_key: bytes, prefix: str = '') -> dict:
        """Walk sub-trees recursively, return flat {path: dict} map.

        Returns {path: {'blob_id': str, 'size': int, 'content_hash': str, 'content_type': str}}
        """
        result = {}
        tree   = self._load_tree(tree_id, read_key)

        for entry in tree.entries:
            name = self._decrypt_name(entry, read_key)
            if not name:
                continue

            full_path = f'{prefix}/{name}' if prefix else name

            if entry.blob_id:
                result[full_path] = dict(
                    blob_id      = str(entry.blob_id),
                    size         = self._decrypt_size(entry, read_key),
                    content_hash = self._decrypt_content_hash(entry, read_key),
                    content_type = self._decrypt_content_type(entry, read_key),
                )
            elif entry.tree_id:
                result.update(self.flatten(str(entry.tree_id), read_key, full_path))

        return result

    def checkout(self, directory: str, tree_id: str, read_key: bytes,
                 prefix: str = '') -> None:
        """Recursively extract files from a tree into the working directory."""
        tree = self._load_tree(tree_id, read_key)

        for entry in tree.entries:
            name = self._decrypt_name(entry, read_key)
            if not name:
                continue

            full_path = f'{prefix}/{name}' if prefix else name

            if entry.blob_id:
                ciphertext = self.obj_store.load(str(entry.blob_id))
                plaintext  = self.crypto.decrypt(read_key, ciphertext)
                file_path  = os.path.join(directory, full_path)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, 'wb') as f:
                    f.write(plaintext)
            elif entry.tree_id:
                self.checkout(directory, str(entry.tree_id), read_key, full_path)

    # --- internal helpers ---

    def _store_tree(self, tree: Schema__Object_Tree, read_key: bytes) -> str:
        """Encrypt and store a tree object. Entries already have _enc fields."""
        tree_json      = json.dumps(tree.json()).encode()
        encrypted_tree = self.crypto.encrypt(read_key, tree_json)
        return self.obj_store.store(encrypted_tree)

    def _load_tree(self, tree_id: str, read_key: bytes) -> Schema__Object_Tree:
        ciphertext = self.obj_store.load(tree_id)
        tree_data  = self.crypto.decrypt(read_key, ciphertext)
        return Schema__Object_Tree.from_json(json.loads(tree_data))

    def _decrypt_name(self, entry, read_key):
        if entry.name_enc:
            return self.crypto.decrypt_metadata(read_key, str(entry.name_enc))
        return ''

    def _decrypt_size(self, entry, read_key):
        if entry.size_enc:
            return int(self.crypto.decrypt_metadata(read_key, str(entry.size_enc)))
        return 0

    def _decrypt_content_hash(self, entry, read_key):
        if entry.content_hash_enc:
            return self.crypto.decrypt_metadata(read_key, str(entry.content_hash_enc))
        return ''

    def _decrypt_content_type(self, entry, read_key):
        if entry.content_type_enc:
            return self.crypto.decrypt_metadata(read_key, str(entry.content_type_enc))
        return 'application/octet-stream'
