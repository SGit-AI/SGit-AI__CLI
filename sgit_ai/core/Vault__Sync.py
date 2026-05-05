import json
import os
import secrets
import string
import time
from   sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from   sgit_ai.crypto.PKI__Crypto                import PKI__Crypto
from   sgit_ai.crypto.Vault__Key_Manager         import Vault__Key_Manager
from   sgit_ai.network.api.Vault__API                    import Vault__API
from   sgit_ai.storage.Vault__Storage               import Vault__Storage, SG_VAULT_DIR
from   sgit_ai.storage.Vault__Branch_Manager        import Vault__Branch_Manager
from   sgit_ai.storage.Vault__Sub_Tree              import Vault__Sub_Tree
from   sgit_ai.storage.Vault__Object_Store       import Vault__Object_Store
from   sgit_ai.storage.Vault__Ref_Manager        import Vault__Ref_Manager
from   sgit_ai.storage.Vault__Commit             import Vault__Commit
from   sgit_ai.schemas.Schema__Object_Tree       import Schema__Object_Tree
from   sgit_ai.schemas.Schema__Branch_Index      import Schema__Branch_Index
from   sgit_ai.schemas.Schema__Local_Config      import Schema__Local_Config
from   sgit_ai.safe_types.Enum__Local_Config_Mode    import Enum__Local_Config_Mode
from   sgit_ai.core.Vault__Sync__Base            import Vault__Sync__Base
from   sgit_ai.core.actions.commit.Vault__Sync__Commit          import Vault__Sync__Commit
from   sgit_ai.core.actions.pull.Vault__Sync__Pull            import Vault__Sync__Pull
from   sgit_ai.core.actions.push.Vault__Sync__Push            import Vault__Sync__Push
from   sgit_ai.core.actions.status.Vault__Sync__Status          import Vault__Sync__Status
from   sgit_ai.core.actions.clone.Vault__Sync__Clone           import Vault__Sync__Clone
from   sgit_ai.core.actions.branch.Vault__Sync__Branch_Ops      import Vault__Sync__Branch_Ops
from   sgit_ai.core.actions.gc.Vault__Sync__GC_Ops          import Vault__Sync__GC_Ops
from   sgit_ai.core.actions.lifecycle.Vault__Sync__Lifecycle       import Vault__Sync__Lifecycle
from   sgit_ai.core.actions.sparse.Vault__Sync__Sparse          import Vault__Sync__Sparse
from   sgit_ai.core.actions.fsck.Vault__Sync__Fsck            import Vault__Sync__Fsck


class Vault__Sync(Vault__Sync__Base):
    crypto       : Vault__Crypto
    api          : Vault__API

    def generate_vault_key(self) -> str:
        alphabet   = string.ascii_lowercase + string.digits
        passphrase = ''.join(secrets.choice(alphabet) for _ in range(24))
        vault_id   = ''.join(secrets.choice(alphabet) for _ in range(8))
        return f'{passphrase}:{vault_id}'

    def init(self, directory: str, vault_key: str = None,
             allow_nonempty: bool = False, token: str = None) -> dict:
        from sgit_ai.network.transfer.Simple_Token import Simple_Token
        if os.path.exists(directory):
            entries = [e for e in os.listdir(directory) if e != SG_VAULT_DIR]
            if entries and not allow_nonempty:
                raise RuntimeError(f'Directory is not empty: {directory}')
        os.makedirs(directory, exist_ok=True)

        # Simple token path: token arg takes precedence over vault_key
        simple_token_mode = False
        if token and Simple_Token.is_simple_token(token):
            simple_token_mode = True
            vault_key         = token
        elif vault_key and Simple_Token.is_simple_token(vault_key):
            simple_token_mode = True
            token             = vault_key

        if not vault_key:
            vault_key = self.generate_vault_key()

        if simple_token_mode:
            keys = self.crypto.derive_keys_from_simple_token(vault_key)
        else:
            keys = self.crypto.derive_keys_from_vault_key(vault_key)
        vault_id   = keys['vault_id']
        read_key   = keys['read_key_bytes']

        storage = Vault__Storage()
        sg_dir  = storage.create_bare_structure(directory)

        pki         = PKI__Crypto()
        key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)

        branch_manager = Vault__Branch_Manager(vault_path    = sg_dir,
                                               crypto        = self.crypto,
                                               key_manager   = key_manager,
                                               ref_manager   = ref_manager,
                                               storage       = storage)

        timestamp_ms   = int(time.time() * 1000)
        clone_ref_id   = 'ref-pid-snw-' + self.crypto.derive_branch_ref_file_id(
                             read_key, vault_id, 'local')
        named_branch   = branch_manager.create_named_branch(directory, 'current', read_key,
                                                             head_ref_id=keys['ref_file_id'],
                                                             timestamp_ms=timestamp_ms)
        clone_branch   = branch_manager.create_clone_branch(directory, 'local', read_key,
                                                             head_ref_id=clone_ref_id,
                                                             creator_branch_id=str(named_branch.branch_id),
                                                             timestamp_ms=timestamp_ms)

        branch_index = Schema__Branch_Index(schema   = 'branch_index_v1',
                                            branches = [named_branch, clone_branch])
        branch_manager.save_branch_index(directory, branch_index, read_key,
                                         index_file_id=keys['branch_index_file_id'])

        clone_private_key = key_manager.load_private_key_locally(
            str(clone_branch.public_key_id), storage.local_dir(directory))

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        # Create empty root tree and store it
        sub_tree     = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)
        empty_tree   = Schema__Object_Tree(schema='tree_v1')
        root_tree_id = sub_tree._store_tree(empty_tree, read_key)

        commit_id = vault_commit.create_commit(read_key      = read_key,
                                               tree_id       = root_tree_id,
                                               message       = 'init',
                                               branch_id     = str(clone_branch.branch_id),
                                               signing_key   = clone_private_key,
                                               timestamp_ms  = timestamp_ms)

        ref_manager.write_ref(str(named_branch.head_ref_id), commit_id, read_key)
        ref_manager.write_ref(str(clone_branch.head_ref_id), commit_id, read_key)

        local_config = Schema__Local_Config(
            my_branch_id = str(clone_branch.branch_id),
            mode         = Enum__Local_Config_Mode.SIMPLE_TOKEN if simple_token_mode else None,
            edit_token   = vault_key if simple_token_mode else None,
        )
        config_path  = storage.local_config_path(directory)
        with open(config_path, 'w') as f:
            json.dump(local_config.json(), f, indent=2)
        storage.chmod_local_file(config_path)

        vault_key_path = storage.vault_key_path(directory)
        with open(vault_key_path, 'w') as f:
            f.write(vault_key)
        storage.chmod_local_file(vault_key_path)

        return dict(directory    = directory,
                    vault_key    = vault_key,
                    vault_id     = vault_id,
                    branch_id    = str(clone_branch.branch_id),
                    named_branch = str(named_branch.branch_id),
                    commit_id    = commit_id)

    def commit(self, directory: str, message: str = '') -> dict:
        return Vault__Sync__Commit(crypto=self.crypto, api=self.api).commit(directory, message)

    def write_file(self, directory: str, path: str, content: bytes,
                   message: str = '', also: dict = None) -> dict:
        return Vault__Sync__Commit(crypto=self.crypto, api=self.api).write_file(
            directory, path, content, message, also)

    def reset(self, directory: str, commit_id: str = None) -> dict:
        return Vault__Sync__Pull(crypto=self.crypto, api=self.api).reset(directory, commit_id)

    def status(self, directory: str) -> dict:
        return Vault__Sync__Status(crypto=self.crypto, api=self.api).status(directory)

    def pull(self, directory: str, on_progress: callable = None) -> dict:
        return Vault__Sync__Pull(crypto=self.crypto, api=self.api).pull(directory, on_progress)

    def fetch(self, directory: str, on_progress: callable = None) -> dict:
        from sgit_ai.core.actions.fetch.Vault__Sync__Fetch import Vault__Sync__Fetch
        return Vault__Sync__Fetch(crypto=self.crypto, api=self.api).fetch(directory, on_progress)

    def push(self, directory: str, message: str = '', force: bool = False,
             use_batch: bool = True, branch_only: bool = False,
             on_progress: callable = None) -> dict:
        return Vault__Sync__Push(crypto=self.crypto, api=self.api).push(
            directory, message, force, use_batch, branch_only, on_progress)

    def merge_abort(self, directory: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).merge_abort(directory)

    def branches(self, directory: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).branches(directory)

    def gc_drain(self, directory: str) -> dict:
        return Vault__Sync__GC_Ops(crypto=self.crypto, api=self.api).gc_drain(directory)

    def create_change_pack(self, directory: str, files: dict) -> dict:
        return Vault__Sync__GC_Ops(crypto=self.crypto, api=self.api).create_change_pack(directory, files)

    def remote_add(self, directory: str, name: str, url: str, vault_id: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).remote_add(directory, name, url, vault_id)

    def remote_remove(self, directory: str, name: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).remote_remove(directory, name)

    def remote_list(self, directory: str) -> dict:
        return Vault__Sync__Branch_Ops(crypto=self.crypto, api=self.api).remote_list(directory)

    def clone(self, vault_key: str, directory: str, on_progress: callable = None, sparse: bool = False) -> dict:
        return Vault__Sync__Clone(crypto=self.crypto, api=self.api).clone(vault_key, directory, on_progress, sparse)

    def clone_branch(self, vault_key: str, directory: str,
                     on_progress: callable = None, bare: bool = False) -> dict:
        return Vault__Sync__Clone(crypto=self.crypto, api=self.api).clone_branch(
            vault_key, directory, on_progress, bare)

    def clone_headless(self, vault_key: str, directory: str,
                       on_progress: callable = None) -> dict:
        return Vault__Sync__Clone(crypto=self.crypto, api=self.api).clone_headless(
            vault_key, directory, on_progress)

    def clone_range(self, vault_key: str, directory: str, range_from: str = '',
                    range_to: str = '', on_progress: callable = None,
                    bare: bool = False) -> dict:
        return Vault__Sync__Clone(crypto=self.crypto, api=self.api).clone_range(
            vault_key, directory, range_from, range_to, on_progress, bare)

    def clone_read_only(self, vault_id: str, read_key_hex: str, directory: str,
                        on_progress: callable = None, sparse: bool = False) -> dict:
        return Vault__Sync__Clone(crypto=self.crypto, api=self.api).clone_read_only(
            vault_id, read_key_hex, directory, on_progress, sparse)

    def clone_from_transfer(self, token_str: str, directory: str, debug_log=None) -> dict:
        return Vault__Sync__Clone(crypto=self.crypto, api=self.api).clone_from_transfer(
            token_str, directory, debug_log)

    def delete_on_remote(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).delete_on_remote(directory)

    def rekey_check(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey_check(directory)

    def rekey_wipe(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey_wipe(directory)

    def rekey_init(self, directory: str, new_vault_key: str = None) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey_init(directory, new_vault_key)

    def rekey_commit(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey_commit(directory)

    def rekey(self, directory: str, new_vault_key: str = None) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).rekey(directory, new_vault_key)

    def probe_token(self, token_str: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).probe_token(token_str)

    def uninit(self, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).uninit(directory)

    def restore_from_backup(self, zip_path: str, directory: str) -> dict:
        return Vault__Sync__Lifecycle(crypto=self.crypto, api=self.api).restore_from_backup(zip_path, directory)

    def _get_head_flat_map(self, directory: str) -> tuple:
        return Vault__Sync__Sparse(crypto=self.crypto, api=self.api)._get_head_flat_map(directory)

    def sparse_ls(self, directory: str, path: str = None) -> list:
        return Vault__Sync__Sparse(crypto=self.crypto, api=self.api).sparse_ls(directory, path)

    def sparse_fetch(self, directory: str, path: str = None,
                     on_progress: callable = None) -> dict:
        return Vault__Sync__Sparse(crypto=self.crypto, api=self.api).sparse_fetch(
            directory, path, on_progress)

    def sparse_cat(self, directory: str, path: str) -> bytes:
        return Vault__Sync__Sparse(crypto=self.crypto, api=self.api).sparse_cat(directory, path)

    def fsck(self, directory: str, repair: bool = False, on_progress: callable = None) -> dict:
        return Vault__Sync__Fsck(crypto=self.crypto, api=self.api).fsck(
            directory, repair, on_progress)

    def _repair_object(self, object_id: str, vault_id: str, sg_dir: str) -> bool:
        return Vault__Sync__Fsck(crypto=self.crypto, api=self.api)._repair_object(
            object_id, vault_id, sg_dir)
