"""Vault__Sync__Upload_Objects — upload specific local objects to the server.

Used for recovery: Session A (full vault) runs this after Session B (gap vault)
identifies missing blob IDs via `sgit check fsck --verbose`.

Since both sessions share the same vault key, the blob IDs are identical —
the local bare/data/ files can be uploaded directly without re-encryption.
"""
import base64
import os
from sgit_ai.storage.Vault__Storage  import SG_VAULT_DIR
from sgit_ai.core.Vault__Sync__Base  import Vault__Sync__Base

UPLOAD_CHUNK = 20   # objects per batch request


class Vault__Sync__Upload_Objects(Vault__Sync__Base):

    def upload_objects(self, directory: str, object_ids: list[str],
                       on_progress: callable = None) -> dict:
        """Upload specific local object files to the server.

        Reads each object from bare/data/, verifies it exists locally, then
        uploads via the existing batch write API. Returns a summary dict.
        """
        _p     = on_progress or (lambda *a, **k: None)
        result = dict(ok=True, uploaded=[], missing_locally=[], errors=[])

        sg_dir   = os.path.join(directory, SG_VAULT_DIR)
        data_dir = os.path.join(sg_dir, 'bare', 'data')

        if not os.path.isdir(sg_dir):
            result['ok'] = False
            result['errors'].append(f'Not a vault: {directory}')
            return result

        _p('step', 'Reading vault configuration')
        try:
            c = self._init_components(directory)
        except Exception as e:
            result['ok'] = False
            result['errors'].append(f'Cannot read vault config: {e}')
            return result

        vault_id  = c.vault_id
        write_key = c.write_key
        if not write_key:
            result['ok'] = False
            result['errors'].append('No write key — cannot upload (read-only clone)')
            return result

        # Partition: which objects exist locally?
        to_upload = []
        for oid in object_ids:
            local_path = os.path.join(data_dir, oid)
            if os.path.isfile(local_path):
                to_upload.append(oid)
            else:
                result['missing_locally'].append(oid)

        if result['missing_locally']:
            result['ok'] = False
            result['errors'].append(
                f'{len(result["missing_locally"])} object(s) not found in local bare/data/ '
                f'— this vault does not have them either'
            )

        _p('step', f'Uploading {len(to_upload)} object(s) in chunks of {UPLOAD_CHUNK}')

        for chunk_start in range(0, len(to_upload), UPLOAD_CHUNK):
            chunk = to_upload[chunk_start:chunk_start + UPLOAD_CHUNK]
            ops   = []
            for oid in chunk:
                local_path = os.path.join(data_dir, oid)
                with open(local_path, 'rb') as f:
                    raw = f.read()
                ops.append(dict(
                    op      = 'write',
                    file_id = f'bare/data/{oid}',
                    data    = base64.b64encode(raw).decode('ascii'),
                ))
            try:
                self.api.batch(vault_id, write_key, ops)
                result['uploaded'].extend(chunk)
                _p('upload', f'Uploaded {len(result["uploaded"])}/{len(to_upload)}',
                   f'{len(chunk)} objects')
            except Exception as e:
                result['ok'] = False
                result['errors'].append(f'Batch upload failed for chunk starting {chunk[0]}: {e}')

        if result['uploaded']:
            _p('step', f'Uploaded {len(result["uploaded"])} object(s)')

        return result
