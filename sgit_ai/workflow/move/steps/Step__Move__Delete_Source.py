"""Step 8 — Atomic local rename (8a) then server delete (8b).

CRITICAL ORDER: local rename FIRST, server delete SECOND.
The server tombstone is permanent; if the rename fails before it, the vault
is unrecoverable without admin intervention.
"""
import os
import shutil
import sys

from sgit_ai.safe_types.Safe_Str__ISO_Timestamp import Safe_Str__ISO_Timestamp
from sgit_ai.safe_types.Safe_Str__Step_Name     import Safe_Str__Step_Name
from sgit_ai.schemas.workflow.move.Schema__Move__State import Schema__Move__State
from sgit_ai.workflow.Step                      import Step

SG_VAULT     = '.sg_vault'
SG_VAULT_NEW = '.sg_vault_new'


class Step__Move__Delete_Source(Step):
    name          = Safe_Str__Step_Name('delete-source')
    input_schema  = Schema__Move__State
    output_schema = Schema__Move__State

    def execute(self, input: Schema__Move__State, workspace) -> Schema__Move__State:
        from datetime import datetime, timezone
        from sgit_ai.crypto.Vault__Crypto   import Vault__Crypto
        from sgit_ai.network.api.Vault__API import Vault__API

        if input.dry_run:
            now_iso    = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            state_dict = input.json()
            state_dict['renamed_at']     = now_iso
            state_dict['server_deleted'] = True
            return Schema__Move__State.from_json(state_dict)

        directory    = str(input.directory)
        old_vault_id = str(input.old_vault_id) if input.old_vault_id else ''
        old_api_url  = str(input.old_api_url) if input.old_api_url else None

        sg_vault_dir = os.path.join(directory, SG_VAULT)
        new_sg_dir   = os.path.join(directory, SG_VAULT_NEW)
        now_ts       = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        old_backup   = os.path.join(directory, f'.sg_vault_old_{now_ts}')

        # ── 8a: atomic local rename (MUST happen before server delete) ──
        os.rename(sg_vault_dir, old_backup)
        try:
            os.rename(new_sg_dir, sg_vault_dir)
        except Exception as rename_err:
            # rename of new→current failed; roll back by restoring old
            try:
                os.rename(old_backup, sg_vault_dir)
            except Exception:
                pass
            raise RuntimeError(
                f'Local rename failed: {rename_err}. '
                f'Both .sg_vault/ and .sg_vault_new/ are intact. '
                f'Run `sgit vault move --cleanup` to retry.'
            ) from rename_err

        now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        # ── 8b: server delete (after local rename succeeds, BEFORE removing backup) ──
        server_deleted = False
        old_vault_key_path = os.path.join(old_backup, 'local', 'vault_key')
        if old_vault_id and os.path.isfile(old_vault_key_path):
            try:
                crypto    = Vault__Crypto()
                with open(old_vault_key_path) as f:
                    old_vault_key = f.read().strip()
                old_keys  = crypto.derive_keys_from_vault_key(old_vault_key)
                write_key = old_keys['write_key']

                if getattr(workspace, 'api', None) is not None:
                    api = workspace.api
                elif old_api_url:
                    api = Vault__API(base_url=old_api_url)
                else:
                    api = Vault__API()

                result    = api.delete_vault(old_vault_id, write_key)
                server_deleted = result.get('status') == 'deleted'

            except RuntimeError as e:
                if '403' in str(e):
                    server_deleted = True  # tombstone = already cleaned up
                else:
                    print(
                        f'Warning: server delete of old vault {old_vault_id} failed: {e}\n'
                        f'Old vault may still be live on server. '
                        f'Run `sgit vault move --cleanup` to retry.',
                        file=sys.stderr
                    )
            except Exception as e:
                print(
                    f'Warning: could not delete old vault from server: {e}\n'
                    f'Run `sgit vault move --cleanup` to complete cleanup.',
                    file=sys.stderr
                )
        elif old_vault_id:
            print(f'Warning: old vault key not found at {old_vault_key_path}; skipping server delete.',
                  file=sys.stderr)

        # Remove old backup dir (after server delete attempt)
        try:
            shutil.rmtree(old_backup)
        except Exception:
            pass

        state_dict = input.json()
        state_dict['renamed_at']     = now_iso
        state_dict['server_deleted'] = server_deleted
        return Schema__Move__State.from_json(state_dict)
