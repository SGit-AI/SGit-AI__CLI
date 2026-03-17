import base64
import json
import time
from   osbot_utils.type_safe.Type_Safe                import Type_Safe
from   sg_send_cli.crypto.Vault__Crypto               import Vault__Crypto
from   sg_send_cli.crypto.PKI__Crypto                 import PKI__Crypto
from   sg_send_cli.objects.Vault__Object_Store        import Vault__Object_Store
from   sg_send_cli.objects.Vault__Ref_Manager         import Vault__Ref_Manager
from   sg_send_cli.schemas.Schema__Object_Commit      import Schema__Object_Commit
from   sg_send_cli.schemas.Schema__Object_Tree        import Schema__Object_Tree
from   sg_send_cli.schemas.Schema__Object_Tree_Entry  import Schema__Object_Tree_Entry


class Vault__Commit(Type_Safe):
    crypto       : Vault__Crypto
    pki          : PKI__Crypto
    object_store : Vault__Object_Store
    ref_manager  : Vault__Ref_Manager

    def encrypt_tree_entry_fields(self, entry: Schema__Object_Tree_Entry, key: bytes) -> dict:
        """Encrypt tree entry metadata fields, return dict for JSON serialization."""
        entry_dict = {}
        # Determine name from available fields (path for flat, name for sub-tree)
        name_value = str(entry.path) if entry.path else (str(entry.name) if entry.name else '')
        if name_value:
            entry_dict['name_enc'] = self.crypto.encrypt_metadata(key, name_value)
        if entry.blob_id:
            entry_dict['blob_id'] = str(entry.blob_id)
        if entry.tree_id:
            entry_dict['tree_id'] = str(entry.tree_id)
        if entry.size and int(entry.size) > 0:
            entry_dict['size_enc'] = self.crypto.encrypt_metadata(key, str(int(entry.size)))
        if entry.content_hash:
            entry_dict['content_hash_enc'] = self.crypto.encrypt_metadata(key, str(entry.content_hash))
        return entry_dict

    def decrypt_tree_entry_fields(self, entry: Schema__Object_Tree_Entry, key: bytes) -> Schema__Object_Tree_Entry:
        """Decrypt encrypted metadata fields back into the entry."""
        if entry.name_enc and not entry.path and not entry.name:
            entry.path = self.crypto.decrypt_metadata(key, str(entry.name_enc))
        if entry.size_enc:
            entry.size = int(self.crypto.decrypt_metadata(key, str(entry.size_enc)))
        if entry.content_hash_enc and not entry.content_hash:
            entry.content_hash = self.crypto.decrypt_metadata(key, str(entry.content_hash_enc))
        return entry

    def create_commit(self, tree: Schema__Object_Tree = None, read_key: bytes = None,
                      tree_id: str = None,
                      parent_ids: list = None, message: str = '',
                      message_enc: str = None,
                      branch_id: str = None, signing_key=None,
                      timestamp_ms: int = None) -> str:
        """Create a commit object and store it.

        Accepts either:
        - tree: a Schema__Object_Tree (encrypts and stores it, returns tree_id) — flat model
        - tree_id: a pre-stored tree object ID — sub-tree model (tree already stored)
        """
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        # Store tree if provided as object (flat model path)
        if tree is not None and tree_id is None:
            tree_dict = tree.json()
            tree_dict['entries'] = [self.encrypt_tree_entry_fields(e, read_key) for e in tree.entries]
            tree_json      = json.dumps(tree_dict).encode()
            encrypted_tree = self.crypto.encrypt(read_key, tree_json)
            tree_id        = self.object_store.store(encrypted_tree)

        if tree_id is None:
            raise ValueError('Either tree or tree_id must be provided')

        parents = []
        if parent_ids:
            parents = [p for p in parent_ids if p]

        # Encrypt message if not already encrypted
        if not message_enc and message:
            message_enc = self.crypto.encrypt_metadata(read_key, message)

        commit = Schema__Object_Commit(tree_id      = tree_id,
                                        schema       = 'commit_v1',
                                        timestamp_ms = timestamp_ms,
                                        message      = message,         # legacy: kept for now
                                        message_enc  = message_enc,
                                        branch_id    = branch_id or '',
                                        parents      = parents)

        # Legacy parent field for backward compat during transition
        if parents:
            commit.parent = parents[0]

        commit_data = json.dumps(commit.json()).encode()

        if signing_key:
            sig_raw          = self.pki.sign(signing_key, commit_data)
            sig_b64          = base64.b64encode(sig_raw).decode()
            commit.signature = sig_b64
            commit_data      = json.dumps(commit.json()).encode()

        encrypted_commit = self.crypto.encrypt(read_key, commit_data)
        commit_id        = self.object_store.store(encrypted_commit)
        return commit_id

    def store_tree(self, tree: Schema__Object_Tree, read_key: bytes) -> str:
        """Encrypt and store a tree object, return its obj-cas-imm-{hash} ID.

        Used by the sub-tree builder to store individual tree objects
        (root tree, sub-trees at each directory level).
        """
        tree_dict = tree.json()
        tree_dict['entries'] = [self.encrypt_tree_entry_fields(e, read_key) for e in tree.entries]
        tree_json      = json.dumps(tree_dict).encode()
        encrypted_tree = self.crypto.encrypt(read_key, tree_json)
        return self.object_store.store(encrypted_tree)

    def load_commit(self, commit_id: str, read_key: bytes) -> Schema__Object_Commit:
        ciphertext  = self.object_store.load(commit_id)
        commit_data = self.crypto.decrypt(read_key, ciphertext)
        return Schema__Object_Commit.from_json(json.loads(commit_data))

    def load_tree(self, tree_id: str, read_key: bytes) -> Schema__Object_Tree:
        ciphertext = self.object_store.load(tree_id)
        tree_data  = self.crypto.decrypt(read_key, ciphertext)
        tree       = Schema__Object_Tree.from_json(json.loads(tree_data))
        for entry in tree.entries:
            self.decrypt_tree_entry_fields(entry, read_key)
        return tree

    def verify_commit_signature(self, commit: Schema__Object_Commit, public_key) -> bool:
        if not commit.signature:
            return False
        sig_raw = base64.b64decode(str(commit.signature))

        commit_dict = commit.json()
        commit_dict['signature'] = None
        commit_data = json.dumps(commit_dict).encode()

        return self.pki.verify(public_key, sig_raw, commit_data)
