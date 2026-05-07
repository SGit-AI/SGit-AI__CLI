"""Step 4 — Append sentinel commit to each active named branch in .sg_vault_new/."""
import json
import os

from sgit_ai.safe_types.Safe_Str__File_Path  import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Step_Name  import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.move.Schema__Move__State import Schema__Move__State
from sgit_ai.workflow.Step                   import Step


class Step__Move__Write_Sentinel_Commits(Step):
    name          = Safe_Str__Step_Name('write-sentinel-commits')
    input_schema  = Schema__Move__State
    output_schema = Schema__Move__State

    def execute(self, input: Schema__Move__State, workspace) -> Schema__Move__State:
        from datetime import datetime, timezone
        from sgit_ai.crypto.Vault__Crypto          import Vault__Crypto
        from sgit_ai.crypto.PKI__Crypto            import PKI__Crypto
        from sgit_ai.crypto.Vault__Key_Manager     import Vault__Key_Manager
        from sgit_ai.storage.Vault__Object_Store   import Vault__Object_Store
        from sgit_ai.storage.Vault__Ref_Manager    import Vault__Ref_Manager
        from sgit_ai.storage.Vault__Branch_Manager import Vault__Branch_Manager
        from sgit_ai.storage.Vault__Commit         import Vault__Commit
        from sgit_ai.storage.Vault__Storage        import Vault__Storage
        from sgit_ai.safe_types.Enum__Branch_Type  import Enum__Branch_Type
        from sgit_ai.schemas.Schema__Branch_Index  import Schema__Branch_Index

        if input.dry_run:
            state_dict = input.json()
            state_dict['sentinel_commit_id'] = 'dry-run-sentinel'
            return Schema__Move__State.from_json(state_dict)

        new_sg_dir    = str(input.temp_vault_dir)
        new_vault_key = str(input.new_vault_key)
        new_vault_id  = str(input.new_vault_id) if input.new_vault_id else ''
        old_vault_id  = str(input.old_vault_id) if input.old_vault_id else ''
        reason        = str(input.reason) if input.reason else ''
        key_gen       = int(input.key_generation) if input.key_generation else 1

        crypto   = Vault__Crypto()
        pki      = PKI__Crypto()
        keys     = crypto.derive_keys_from_vault_key(new_vault_key)
        read_key = keys['read_key_bytes']

        storage        = Vault__Storage()
        obj_store      = Vault__Object_Store(vault_path=new_sg_dir, crypto=crypto)
        ref_manager    = Vault__Ref_Manager(vault_path=new_sg_dir, crypto=crypto)
        key_manager    = Vault__Key_Manager(vault_path=new_sg_dir, crypto=crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(
            vault_path  = new_sg_dir,
            crypto      = crypto,
            key_manager = key_manager,
            ref_manager = ref_manager,
            storage     = storage,
        )
        vc = Vault__Commit(crypto=crypto, pki=pki,
                           object_store=obj_store, ref_manager=ref_manager)

        index_id  = keys.get('branch_index_file_id', '')
        if not index_id:
            state_dict = input.json()
            return Schema__Move__State.from_json(state_dict)

        try:
            idx_path = os.path.join(new_sg_dir, 'bare', 'indexes', index_id)
            with open(idx_path, 'rb') as _f:
                _ciphertext = _f.read()
            index = Schema__Branch_Index.from_json(
                json.loads(crypto.decrypt(read_key, _ciphertext))
            )
        except Exception:
            state_dict = input.json()
            return Schema__Move__State.from_json(state_dict)

        now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        sentinel_msg = (
            f'vault-move: rotated to vault-id {new_vault_id} at {now_iso}\n'
            f'  reason: {reason}\n'
            f'  from-vault-id: {old_vault_id}\n'
            f'  to-vault-id: {new_vault_id}\n'
            f'  key-generation: {key_gen}'
        )

        first_sentinel_id = ''
        for branch in index.branches:
            if str(branch.branch_type) != str(Enum__Branch_Type.NAMED):
                continue

            head_ref_id = str(branch.head_ref_id) if branch.head_ref_id else ''
            if not head_ref_id:
                continue

            try:
                parent_commit_id = ref_manager.read_ref(head_ref_id, read_key)
            except Exception:
                parent_commit_id = ''

            if not parent_commit_id:
                continue

            try:
                parent_commit = vc.load_commit(parent_commit_id, read_key)
                tree_id       = str(parent_commit.tree_id)
            except Exception:
                continue

            priv_key_id = str(branch.private_key_id) if branch.private_key_id else ''
            signing_key = None
            if priv_key_id:
                try:
                    signing_key = key_manager.load_private_key(priv_key_id, read_key)
                except Exception:
                    pass

            sentinel_id = vc.create_commit(
                read_key    = read_key,
                tree_id     = tree_id,
                parent_ids  = [parent_commit_id],
                message     = sentinel_msg,
                branch_id   = str(branch.branch_id),
                signing_key = signing_key,
            )
            ref_manager.write_ref(head_ref_id, sentinel_id, read_key)

            if not first_sentinel_id:
                first_sentinel_id = sentinel_id

        state_dict = input.json()
        state_dict['sentinel_commit_id'] = first_sentinel_id
        return Schema__Move__State.from_json(state_dict)
