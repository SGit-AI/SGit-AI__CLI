"""Step 5 — Push .sg_vault_new/ to the target API server."""
import base64
import os

from sgit_ai.safe_types.Safe_Str__Step_Name  import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.move.Schema__Move__State import Schema__Move__State
from sgit_ai.workflow.Step                   import Step


class Step__Move__Push_To_Target(Step):
    name          = Safe_Str__Step_Name('push-to-target')
    input_schema  = Schema__Move__State
    output_schema = Schema__Move__State

    def execute(self, input: Schema__Move__State, workspace) -> Schema__Move__State:
        from sgit_ai.network.api.Vault__API            import Vault__API
        from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
        from sgit_ai.core.actions.push.Vault__Batch    import Vault__Batch
        from sgit_ai.network.api.Vault__API            import LARGE_BLOB_THRESHOLD
        import sys

        if input.dry_run:
            state_dict = input.json()
            state_dict['push_completed'] = True
            return Schema__Move__State.from_json(state_dict)

        new_sg_dir    = str(input.temp_vault_dir)
        new_vault_key = str(input.new_vault_key)
        target_api_url = str(input.target_api_url) if input.target_api_url else None
        old_api_url    = str(input.old_api_url) if input.old_api_url else None

        crypto = Vault__Crypto()
        keys   = crypto.derive_keys_from_vault_key(new_vault_key)
        vault_id  = keys['vault_id']
        write_key = keys['write_key']

        effective_url = target_api_url or old_api_url
        api = Vault__API(base_url=effective_url) if effective_url else Vault__API()

        bare_dir = os.path.join(new_sg_dir, 'bare')
        if not os.path.isdir(bare_dir):
            state_dict = input.json()
            state_dict['push_completed'] = True
            return Schema__Move__State.from_json(state_dict)

        batch_ops   = []
        large_files = []
        for root, _, files in os.walk(bare_dir):
            for filename in sorted(files):
                full_path = os.path.join(root, filename)
                rel_path  = os.path.relpath(full_path, new_sg_dir)
                rel_path  = rel_path.replace(os.sep, '/')
                with open(full_path, 'rb') as f:
                    data = f.read()
                if len(data) > LARGE_BLOB_THRESHOLD:
                    large_files.append((rel_path, data))
                else:
                    batch_ops.append(dict(
                        op      = 'write',
                        file_id = rel_path,
                        data    = base64.b64encode(data).decode('ascii'),
                    ))

        batch = Vault__Batch(crypto=crypto, api=api)
        for file_id, data in large_files:
            if not batch._upload_large(vault_id, file_id, data, write_key):
                batch_ops.append(dict(
                    op      = 'write',
                    file_id = file_id,
                    data    = base64.b64encode(data).decode('ascii'),
                ))

        if batch_ops:
            try:
                batch.execute_batch(vault_id, write_key, batch_ops)
            except Exception as e:
                print(f'Warning: batch upload failed ({e}), falling back to individual uploads',
                      file=sys.stderr)
                batch.execute_individually(vault_id, write_key, batch_ops)

        state_dict = input.json()
        state_dict['push_completed'] = True
        return Schema__Move__State.from_json(state_dict)
