import json
import os
from   osbot_utils.type_safe.Type_Safe                import Type_Safe
from   sg_send_cli.crypto.Vault__Crypto               import Vault__Crypto
from   sg_send_cli.objects.Vault__Object_Store        import Vault__Object_Store
from   sg_send_cli.schemas.Schema__Object_Tree        import Schema__Object_Tree
from   sg_send_cli.schemas.Schema__Object_Tree_Entry  import Schema__Object_Tree_Entry


class Vault__Sub_Tree(Type_Safe):
    """Build and traverse sub-tree structures.

    Sub-tree model: one tree object per directory level.
    Root tree contains entries for files + sub-tree references for folders.
    Each sub-tree contains entries for its own files + deeper sub-tree references.

    Building (bottom-up):
        _build() groups files by directory, builds deepest trees first,
        then references them from parent trees.

    Flattening (top-down):
        flatten() walks sub-trees recursively, returning a flat
        {path: {blob_id, content_hash}} map for comparison.
    """
    crypto    : Vault__Crypto
    obj_store : Vault__Object_Store

    def build(self, directory: str, file_map: dict, read_key: bytes,
              old_flat_entries: dict = None) -> str:
        """Build sub-tree objects bottom-up from working directory files.

        Args:
            directory:         working directory path
            file_map:          {relative_path: {size, content_hash}} from _scan_local_directory
            read_key:          vault read key for encryption
            old_flat_entries:  {path: Schema__Object_Tree_Entry} from previous commit
                               (used for blob reuse when content_hash matches)

        Returns:
            Root tree object ID (obj-cas-imm-{hash})
        """
        if old_flat_entries is None:
            old_flat_entries = {}

        # Step 1: Group files by parent directory
        # dir_contents maps dir_path → list of (filename, relative_path)
        # '' = root directory
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
                # Register all ancestor directories
                for i in range(1, len(parts)):
                    all_dirs.add('/'.join(parts[:i]))

        # Ensure all directories appear in dir_contents (some may have no direct files)
        for d in all_dirs:
            dir_contents.setdefault(d, [])
        dir_contents.setdefault('', [])  # root always exists

        # Step 2: Build trees bottom-up (deepest directories first)
        tree_ids = {}  # { dir_path: obj-cas-imm-{hash} }

        for dir_path in sorted(dir_contents.keys(),
                                key=lambda p: (-p.count('/'), p) if p else (1, ''),
                                reverse=False):
            # Sort by depth descending — deepest first, then root last
            pass

        # Process in correct order: deepest first
        sorted_dirs = sorted(dir_contents.keys(),
                             key=lambda p: (-p.count('/') if p else 1, p))

        for dir_path in sorted_dirs:
            entries = []

            # Add file entries for this directory
            for filename, rel_path in sorted(dir_contents[dir_path], key=lambda x: x[0]):
                if rel_path not in file_map:
                    continue

                local_file = os.path.join(directory, rel_path)
                if not os.path.isfile(local_file):
                    continue

                with open(local_file, 'rb') as f:
                    content = f.read()

                file_hash = self.crypto.content_hash(content)

                # Reuse blob from old commit if content unchanged
                old_entry = old_flat_entries.get(rel_path)
                if old_entry and str(old_entry.content_hash or '') == file_hash and old_entry.blob_id:
                    blob_id = str(old_entry.blob_id)
                else:
                    encrypted = self.crypto.encrypt(read_key, content)
                    blob_id   = self.obj_store.store(encrypted)

                entry = Schema__Object_Tree_Entry(
                    name    = filename,
                    blob_id = blob_id,
                    size    = len(content),
                    content_hash = file_hash,
                )
                entries.append(entry)

            # Add sub-directory entries (already built, tree_ids populated)
            for child_dir in sorted(all_dirs):
                # Is child_dir a direct child of dir_path?
                if dir_path == '':
                    if '/' not in child_dir:  # direct child of root
                        folder_name = child_dir
                    else:
                        continue
                elif child_dir.startswith(dir_path + '/'):
                    remainder = child_dir[len(dir_path) + 1:]
                    if '/' not in remainder:  # direct child
                        folder_name = remainder
                    else:
                        continue
                else:
                    continue

                if child_dir in tree_ids:
                    entry = Schema__Object_Tree_Entry(
                        name    = folder_name,
                        tree_id = tree_ids[child_dir],
                    )
                    entries.append(entry)

            # Build and store tree object
            tree_obj = Schema__Object_Tree(schema='tree_v1', entries=entries)
            tree_id  = self._store_tree(tree_obj, read_key)
            tree_ids[dir_path] = tree_id

        return tree_ids.get('', '')

    def flatten(self, tree_id: str, read_key: bytes, prefix: str = '') -> dict:
        """Walk sub-trees recursively, return flat {path: {blob_id, content_hash, size}} map.

        This is the inverse of build() — given a root tree ID, produces the
        same flat path map that _scan_local_directory would produce for a
        working directory with those files.
        """
        result = {}
        tree   = self._load_tree(tree_id, read_key)

        for entry in tree.entries:
            name = self._entry_name(entry)
            if not name:
                continue

            full_path = f'{prefix}/{name}' if prefix else name

            if entry.blob_id:
                result[full_path] = Schema__Object_Tree_Entry(
                    path         = full_path,
                    name         = name,
                    blob_id      = str(entry.blob_id),
                    size         = int(entry.size) if entry.size else 0,
                    content_hash = str(entry.content_hash) if entry.content_hash else '',
                )
            elif entry.tree_id:
                result.update(self.flatten(str(entry.tree_id), read_key, full_path))

        return result

    def checkout(self, directory: str, tree_id: str, read_key: bytes,
                 prefix: str = '') -> None:
        """Recursively extract files from a tree into the working directory."""
        tree = self._load_tree(tree_id, read_key)

        for entry in tree.entries:
            name = self._entry_name(entry)
            if not name:
                continue

            full_path = f'{prefix}/{name}' if prefix else name

            if entry.blob_id:
                blob_id    = str(entry.blob_id)
                ciphertext = self.obj_store.load(blob_id)
                plaintext  = self.crypto.decrypt(read_key, ciphertext)
                file_path  = os.path.join(directory, full_path)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, 'wb') as f:
                    f.write(plaintext)
            elif entry.tree_id:
                self.checkout(directory, str(entry.tree_id), read_key, full_path)

    # --- internal helpers ---

    def _store_tree(self, tree: Schema__Object_Tree, read_key: bytes) -> str:
        """Encrypt and store a tree object, return obj-cas-imm-{hash} ID."""
        from sg_send_cli.objects.Vault__Commit import Vault__Commit
        from sg_send_cli.crypto.PKI__Crypto   import PKI__Crypto
        vc = Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(),
                           object_store=self.obj_store, ref_manager=None)
        return vc.store_tree(tree, read_key)

    def _load_tree(self, tree_id: str, read_key: bytes) -> Schema__Object_Tree:
        """Load and decrypt a tree object."""
        from sg_send_cli.objects.Vault__Commit import Vault__Commit
        from sg_send_cli.crypto.PKI__Crypto   import PKI__Crypto
        vc = Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(),
                           object_store=self.obj_store, ref_manager=None)
        return vc.load_tree(tree_id, read_key)

    def _entry_name(self, entry: Schema__Object_Tree_Entry) -> str:
        """Get the display name from an entry (handles both flat and sub-tree models)."""
        if entry.name:
            return str(entry.name)
        if entry.path:
            return str(entry.path)
        return ''
