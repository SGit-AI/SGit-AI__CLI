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
        priv_key_id = 'key-rnd-imm-' + self.key_manager.generate_key_id()

        private_key, public_key = self.key_manager.generate_branch_key_pair()

        self.key_manager.store_public_key(pub_key_id, public_key, read_key)
        self.key_manager.store_private_key(priv_key_id, private_key, read_key)

        meta = Schema__Branch_Meta(branch_id      = branch_id,
                                   name           = name,
                                   branch_type    = Enum__Branch_Type.NAMED,
                                   head_ref_id    = ref_id,
                                   public_key_id  = pub_key_id,
                                   private_key_id = priv_key_id,
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
        data = json.loads(self.crypto.decrypt(read_key, ciphertext))
        return Schema__Branch_Index.from_json(data)

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
