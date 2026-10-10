import json
import os
import secrets
from   osbot_utils.type_safe.Type_Safe                import Type_Safe
from   sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from   sgit_ai.crypto.Vault__Key_Manager          import Vault__Key_Manager
from   sgit_ai.storage.Vault__Ref_Manager         import Vault__Ref_Manager
from   sgit_ai.safe_types.Safe_Str__Vault_Path    import Safe_Str__Vault_Path
from   sgit_ai.safe_types.Enum__Branch_Type       import Enum__Branch_Type
from   sgit_ai.schemas.Schema__Branch_Meta        import Schema__Branch_Meta
from   sgit_ai.schemas.Schema__Branch_Index       import Schema__Branch_Index
from   sgit_ai.storage.Vault__Storage                import Vault__Storage

import time


class Vault__Branch_Manager(Type_Safe):
    vault_path  : Safe_Str__Vault_Path = None
    crypto      : Vault__Crypto
    key_manager : Vault__Key_Manager
    ref_manager : Vault__Ref_Manager
    storage     : Vault__Storage

    def create_named_branch(self, directory: str, name: str, read_key: bytes,
                            head_ref_id: str = None,
                            timestamp_ms: int = None) -> Schema__Branch_Meta:
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        branch_id   = 'branch-named-' + secrets.token_hex(8)
        ref_id      = head_ref_id or ('ref-pid-muw-' + secrets.token_hex(6))
        pub_key_id  = 'key-rnd-imm-' + self.key_manager.generate_key_id()

        _private_key, public_key = self.key_manager.generate_branch_key_pair()
        self.key_manager.store_public_key(pub_key_id, public_key, read_key)
        # The private half is deliberately NOT stored. It used to go into bare/keys/
        # under the read key, so every read-key holder (every read-only share) could
        # sign as the named branch (threat model TM-R02). Every commit is signed by
        # the writing clone's own key, whose private half never leaves that clone.

        meta = Schema__Branch_Meta(branch_id      = branch_id,
                                   name           = name,
                                   branch_type    = Enum__Branch_Type.NAMED,
                                   head_ref_id    = ref_id,
                                   public_key_id  = pub_key_id,
                                   created_at     = timestamp_ms)
        return meta

    def create_clone_branch(self, directory: str, name: str, read_key: bytes,
                            head_ref_id: str = None,
                            creator_branch_id: str = None,
                            timestamp_ms: int = None) -> Schema__Branch_Meta:
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        branch_id  = 'branch-clone-' + secrets.token_hex(8)
        ref_id     = head_ref_id or ('ref-pid-snw-' + secrets.token_hex(6))
        pub_key_id = 'key-rnd-imm-' + self.key_manager.generate_key_id()

        private_key, public_key = self.key_manager.generate_branch_key_pair()

        self.key_manager.store_public_key(pub_key_id, public_key, read_key)

        local_dir = self.storage.local_dir(directory)
        self.key_manager.store_private_key_locally(pub_key_id, private_key, local_dir)

        meta = Schema__Branch_Meta(branch_id      = branch_id,
                                   name           = name,
                                   branch_type    = Enum__Branch_Type.CLONE,
                                   head_ref_id    = ref_id,
                                   public_key_id  = pub_key_id,
                                   created_at     = timestamp_ms,
                                   creator_branch = creator_branch_id)
        return meta

    def save_branch_index(self, directory: str, index: Schema__Branch_Index,
                          read_key: bytes, index_file_id: str = None) -> None:
        if not index_file_id:
            index_file_id = 'idx-pid-muw-' + secrets.token_hex(6)
        data       = json.dumps(index.json()).encode()
        ciphertext = self.crypto.encrypt(read_key, data)
        path       = self.storage.index_path(directory, index_file_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(ciphertext)

    def load_branch_index(self, directory: str, index_id: str, read_key: bytes) -> Schema__Branch_Index:
        path = self.storage.index_path(directory, index_id)
        with open(path, 'rb') as f:
            ciphertext = f.read()
        data  = json.loads(self.crypto.decrypt(read_key, ciphertext))
        from sgit_ai.storage.Vault__Index_Reader import Vault__Index_Reader
        index = Vault__Index_Reader().parse(data)                     # one unreadable tag entry never breaks the index
        from sgit_ai.storage.Vault__Format import Vault__Format
        Vault__Format().check_client(index)                  # refuse by name when the vault needs a newer client
        return index

    def get_branch_by_id(self, index: Schema__Branch_Index, branch_id: str) -> Schema__Branch_Meta:
        for branch in index.branches:
            if str(branch.branch_id) == branch_id:
                return branch
        return None

    def get_branch_by_name(self, index: Schema__Branch_Index, name: str) -> Schema__Branch_Meta:
        for branch in index.branches:
            if str(branch.name) == name:
                return branch
        return None

    def tracked_named_branch(self, index: Schema__Branch_Index, clone_branch_id: str = None) -> Schema__Branch_Meta:
        """The named branch a clone branch works against: the one it was created from
        (`clone` and `branch switch` record it as creator_branch), else 'current'. A
        recorded branch that is not in the index gives None (callers refuse by name):
        push used to fall back to 'current' and land work on the main branch.
        Push, pull, fetch and status all use this, so work on `feature` goes to
        `feature`, never to the main branch."""
        clone = self.get_branch_by_id(index, str(clone_branch_id)) if clone_branch_id else None
        if clone is not None and clone.creator_branch:
            named = self.get_branch_by_id(index, str(clone.creator_branch))
            if named is not None and named.branch_type == Enum__Branch_Type.NAMED:
                return named
            return None                                  # its branch is gone: never silently 'current' (S11)
        return self.get_branch_by_name(index, 'current')
