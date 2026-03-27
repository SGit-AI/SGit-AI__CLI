import json
import os

from osbot_utils.type_safe.Type_Safe              import Type_Safe
from sgit_ai.crypto.Vault__Crypto                 import Vault__Crypto
from sgit_ai.crypto.PKI__Crypto                   import PKI__Crypto
from sgit_ai.crypto.Vault__Key_Manager            import Vault__Key_Manager
from sgit_ai.objects.Vault__Object_Store          import Vault__Object_Store
from sgit_ai.objects.Vault__Ref_Manager           import Vault__Ref_Manager
from sgit_ai.schemas.Schema__Dump_Branch          import Schema__Dump_Branch
from sgit_ai.schemas.Schema__Dump_Commit          import Schema__Dump_Commit
from sgit_ai.schemas.Schema__Dump_Object          import Schema__Dump_Object
from sgit_ai.schemas.Schema__Dump_Ref             import Schema__Dump_Ref
from sgit_ai.schemas.Schema__Dump_Result          import Schema__Dump_Result
from sgit_ai.schemas.Schema__Dump_Tree            import Schema__Dump_Tree
from sgit_ai.sync.Vault__Branch_Manager           import Vault__Branch_Manager
from sgit_ai.sync.Vault__Storage                  import Vault__Storage, SG_VAULT_DIR


class Vault__Dump(Type_Safe):
    """Produces a complete structural snapshot of a vault (local or remote).

    The dump traverses the vault from root refs to leaf blobs and collects:
      - traversal_path  : ordered sequence of object IDs visited (root → leaves)
      - refs            : all ref files in bare/refs
      - branches        : all branches decoded from the branch index
      - commits         : all commit objects encountered
      - trees           : all tree objects encountered
      - objects         : all objects in bare/data (IDs + sizes, no content)
      - dangling_ids    : objects not referenced by any tree or commit

    When `structure_key` is provided (and not the full read_key), only metadata
    (refs, branches, trees, commits) is readable.  Blob content is never read —
    the dump is structural only.
    """

    crypto  : Vault__Crypto

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def dump_local(self, directory: str, read_key: bytes = None) -> Schema__Dump_Result:
        """Produce a full structural dump of the local vault at *directory*.

        If *read_key* is None the method attempts to read it from the vault's
        ``local/vault_key`` file.  If that also fails the dump is produced
        without decrypting any metadata (refs/branches/commits/trees will show
        errors rather than decoded values).
        """
        sg_dir     = os.path.join(directory, SG_VAULT_DIR)
        read_key   = read_key or self._load_read_key(directory, sg_dir)
        obj_store  = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        ref_mgr    = Vault__Ref_Manager(vault_path=sg_dir,  crypto=self.crypto)
        storage    = Vault__Storage()
        pki        = PKI__Crypto()
        key_mgr    = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        branch_mgr = Vault__Branch_Manager(vault_path    = sg_dir,
                                           crypto        = self.crypto,
                                           key_manager   = key_mgr,
                                           ref_manager   = ref_mgr,
                                           storage       = storage)

        result          = Schema__Dump_Result(source='local', directory=directory)
        referenced_ids  = set()

        # 1. Dump all refs
        for ref_id in ref_mgr.list_refs():
            ref_entry = self._dump_ref(ref_id, ref_mgr, read_key)
            result.refs.append(ref_entry)

        # 2. Dump branch index
        index_id = self._find_index_id(storage, directory)
        if index_id and read_key:
            branch_dumps = self._dump_branches(branch_mgr, ref_mgr,
                                               directory, index_id, read_key)
            result.branches.extend(branch_dumps)
        elif index_id:
            result.errors.append(f'branch index found ({index_id}) but read_key is missing')

        # 3. Traverse commits + trees reachable from all refs
        traversal_path = []
        commit_ids_seen = set()
        for ref_entry in result.refs:
            commit_id = str(ref_entry.commit_id) if ref_entry.commit_id else ''
            if not commit_id or commit_id in commit_ids_seen:
                continue
            self._traverse_commit(commit_id, obj_store, read_key,
                                  result, traversal_path,
                                  commit_ids_seen, referenced_ids)

        result.traversal_path = [s for s in traversal_path]

        # 4. Inventory all raw objects and detect dangling ones
        all_object_ids = obj_store.all_object_ids()
        for oid in all_object_ids:
            is_dangling = oid not in referenced_ids
            size_bytes  = 0
            integrity   = True
            try:
                path       = obj_store.object_path(oid)
                size_bytes = os.path.getsize(path)
                integrity  = obj_store.verify_integrity(oid)
            except Exception:
                integrity = False
            result.objects.append(Schema__Dump_Object(
                object_id   = oid,
                size_bytes  = size_bytes,
                is_dangling = is_dangling,
                integrity   = integrity,
            ))

        # 5. Collect dangling IDs
        for obj in result.objects:
            if obj.is_dangling:
                result.dangling_ids.append(str(obj.object_id))

        # 6. Counts
        result.total_objects  = len(result.objects)
        result.total_refs     = len(result.refs)
        result.total_branches = len(result.branches)
        result.dangling_count = len(result.dangling_ids)

        return result

    def dump_with_structure_key(self, directory: str,
                                structure_key: bytes) -> Schema__Dump_Result:
        """Produce a structural dump using only the structure key.

        Refs, branches, trees, and commit metadata are decrypted.
        Blob content is never accessed.  This is the structure-key-only
        diagnostic path (AC9).
        """
        # The structure key is derived from the read key but cannot decrypt
        # blobs (which are encrypted with the read key, not the structure key).
        # We pass it as the read_key for metadata decryption.
        result = self.dump_local(directory, read_key=structure_key)
        result.source = 'local(structure-key)'
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_read_key(self, directory: str, sg_dir: str) -> bytes:
        """Try to load vault_key from local/ and derive read_key."""
        key_path = os.path.join(sg_dir, 'local', 'vault_key')
        if not os.path.isfile(key_path):
            return None
        try:
            with open(key_path, 'r') as fh:
                vault_key = fh.read().strip()
            keys = self.crypto.derive_keys_from_vault_key(vault_key)
            return keys['read_key_bytes']
        except Exception:
            return None

    def _find_index_id(self, storage: Vault__Storage, directory: str) -> str:
        indexes_dir = storage.bare_indexes_dir(directory)
        if not os.path.isdir(indexes_dir):
            return ''
        for name in sorted(os.listdir(indexes_dir)):
            if name.startswith('idx-pid-muw-'):
                return name
        return ''

    def _dump_ref(self, ref_id: str, ref_mgr: Vault__Ref_Manager,
                  read_key: bytes) -> Schema__Dump_Ref:
        commit_id = None
        error     = None
        try:
            commit_id = ref_mgr.read_ref(ref_id, read_key)
        except Exception as exc:
            error = str(exc)
        return Schema__Dump_Ref(ref_id=ref_id, commit_id=commit_id, error=error)

    def _dump_branches(self, branch_mgr: Vault__Branch_Manager,
                       ref_mgr: Vault__Ref_Manager,
                       directory: str, index_id: str,
                       read_key: bytes) -> list:
        try:
            branch_index = branch_mgr.load_branch_index(directory, index_id, read_key)
        except Exception as exc:
            return []
        dumps = []
        for branch_meta in branch_index.branches:
            head_ref_id = str(branch_meta.head_ref_id) if branch_meta.head_ref_id else ''
            head_commit = None
            if head_ref_id:
                try:
                    head_commit = ref_mgr.read_ref(head_ref_id, read_key)
                except Exception:
                    head_commit = None
            dumps.append(Schema__Dump_Branch(
                branch_id   = str(branch_meta.branch_id)   if branch_meta.branch_id   else '',
                name        = str(branch_meta.name)         if branch_meta.name         else '',
                branch_type = str(branch_meta.branch_type)  if branch_meta.branch_type  else '',
                head_ref_id = head_ref_id,
                head_commit = head_commit,
                created_at  = int(branch_meta.created_at)  if branch_meta.created_at  else 0,
            ))
        return dumps

    def _traverse_commit(self, commit_id: str, obj_store: Vault__Object_Store,
                         read_key: bytes, result: Schema__Dump_Result,
                         traversal_path: list, seen_commits: set,
                         referenced_ids: set) -> None:
        """DFS traverse commit chain and tree objects, recording traversal."""
        if commit_id in seen_commits:
            return
        seen_commits.add(commit_id)

        if not obj_store.exists(commit_id):
            result.errors.append(f'commit object not found: {commit_id}')
            return

        traversal_path.append(commit_id)
        referenced_ids.add(commit_id)

        commit_dump = Schema__Dump_Commit(commit_id=commit_id)

        if read_key:
            try:
                ciphertext  = obj_store.load(commit_id)
                plaintext   = self.crypto.decrypt(read_key, ciphertext)
                parsed      = json.loads(plaintext)

                tree_id     = parsed.get('tree_id', '')
                parents     = parsed.get('parents', [])
                ts          = parsed.get('timestamp_ms', 0)
                branch_id   = parsed.get('branch_id', '')
                message_enc = parsed.get('message_enc', '')

                message = None
                if message_enc:
                    try:
                        message = self.crypto.decrypt_metadata(read_key, message_enc)
                    except Exception:
                        message = '[encrypted]'

                commit_dump.tree_id      = tree_id
                commit_dump.parents      = [p for p in parents if p]
                commit_dump.timestamp_ms = int(ts) if ts else 0
                commit_dump.branch_id    = branch_id
                commit_dump.message      = message

                # traverse tree
                if tree_id:
                    traversal_path.append(tree_id)
                    referenced_ids.add(tree_id)
                    self._traverse_tree(tree_id, obj_store, read_key,
                                        result, traversal_path, referenced_ids)

                # recurse into parents
                for parent_id in parents:
                    if parent_id:
                        self._traverse_commit(parent_id, obj_store, read_key,
                                              result, traversal_path,
                                              seen_commits, referenced_ids)
            except Exception as exc:
                commit_dump.error = str(exc)
        else:
            commit_dump.error = 'read_key not available'

        result.commits.append(commit_dump)

    def _traverse_tree(self, tree_id: str, obj_store: Vault__Object_Store,
                       read_key: bytes, result: Schema__Dump_Result,
                       traversal_path: list, referenced_ids: set) -> None:
        """Traverse one tree object, recording all referenced blobs and sub-trees."""
        if not obj_store.exists(tree_id):
            result.errors.append(f'tree object not found: {tree_id}')
            return

        tree_dump = Schema__Dump_Tree(tree_id=tree_id)

        try:
            ciphertext  = obj_store.load(tree_id)
            plaintext   = self.crypto.decrypt(read_key, ciphertext)
            parsed      = json.loads(plaintext)
            entries     = parsed.get('entries', [])

            blob_ids     = []
            sub_tree_ids = []

            for entry in entries:
                blob_id    = entry.get('blob_id', '')
                sub_tree_id = entry.get('tree_id', '')

                if blob_id:
                    blob_ids.append(blob_id)
                    referenced_ids.add(blob_id)
                    traversal_path.append(blob_id)

                if sub_tree_id:
                    sub_tree_ids.append(sub_tree_id)
                    referenced_ids.add(sub_tree_id)
                    traversal_path.append(sub_tree_id)
                    self._traverse_tree(sub_tree_id, obj_store, read_key,
                                        result, traversal_path, referenced_ids)

            tree_dump.entry_count  = len(entries)
            tree_dump.blob_ids     = blob_ids
            tree_dump.sub_tree_ids = sub_tree_ids

        except Exception as exc:
            tree_dump.error = str(exc)

        result.trees.append(tree_dump)
