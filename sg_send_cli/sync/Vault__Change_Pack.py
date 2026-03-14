import base64
import hashlib
import json
import os
import time
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sg_send_cli.crypto.Vault__Crypto              import Vault__Crypto
from   sg_send_cli.crypto.PKI__Crypto                import PKI__Crypto
from   sg_send_cli.objects.Vault__Object_Store       import Vault__Object_Store
from   sg_send_cli.schemas.Schema__Change_Pack       import Schema__Change_Pack
from   sg_send_cli.sync.Vault__Storage               import Vault__Storage


class Vault__Change_Pack(Type_Safe):
    crypto  : Vault__Crypto
    storage : Vault__Storage

    def create_change_pack(self, directory: str, read_key: bytes,
                           files: dict, branch_id: str,
                           signing_key=None) -> dict:
        """Create a self-contained change pack from a dict of {path: content_bytes}.

        The change pack stores encrypted blobs in bare/pending/ and a manifest
        describing the pack contents. Returns the pack ID and manifest.
        """
        sg_dir    = self.storage.sg_vault_dir(directory)
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        pki       = PKI__Crypto()

        pending_dir = self.storage.bare_pending_dir(directory)
        os.makedirs(pending_dir, exist_ok=True)

        pack_id   = f'pack-{os.urandom(6).hex()}'
        pack_dir  = os.path.join(pending_dir, pack_id)
        os.makedirs(pack_dir, exist_ok=True)

        file_ids  = []
        entries   = []

        for path, content in files.items():
            if isinstance(content, str):
                content = content.encode('utf-8')
            encrypted = self.crypto.encrypt(read_key, content)
            blob_id   = hashlib.sha256(encrypted).hexdigest()[:12]
            blob_path = os.path.join(pack_dir, f'obj-{blob_id}')
            with open(blob_path, 'wb') as f:
                f.write(encrypted)
            file_ids.append(f'obj-{blob_id}')
            content_hash = self.crypto.content_hash(content)
            entries.append(dict(path=path, blob_id=f'obj-{blob_id}',
                                size=len(content), content_hash=content_hash))

        timestamp_ms = int(time.time() * 1000)

        payload_bytes = json.dumps(entries, sort_keys=True).encode()
        payload_hash  = hashlib.sha256(payload_bytes).hexdigest()

        signature = ''
        if signing_key:
            signature = pki.sign(signing_key, payload_hash.encode()).hex()

        manifest = Schema__Change_Pack(
            schema       = 'change_pack_v1',
            branch_id    = branch_id,
            created_at   = timestamp_ms,
            creator_key  = '',
            signature    = signature,
            payload_hash = payload_hash,
            payload      = file_ids)

        manifest_path = os.path.join(pack_dir, 'manifest.json')
        with open(manifest_path, 'w') as f:
            json.dump(manifest.json(), f, indent=2)

        return dict(pack_id   = pack_id,
                    file_ids  = file_ids,
                    entries   = entries,
                    pack_dir  = pack_dir)

    def list_pending_packs(self, directory: str) -> list:
        """List all pending change packs in bare/pending/."""
        pending_dir = self.storage.bare_pending_dir(directory)
        if not os.path.isdir(pending_dir):
            return []
        return sorted(d for d in os.listdir(pending_dir)
                      if os.path.isdir(os.path.join(pending_dir, d))
                      and d.startswith('pack-'))

    def load_pack_manifest(self, directory: str, pack_id: str) -> dict:
        """Load and parse a change pack's manifest."""
        pending_dir   = self.storage.bare_pending_dir(directory)
        manifest_path = os.path.join(pending_dir, pack_id, 'manifest.json')
        if not os.path.isfile(manifest_path):
            raise FileNotFoundError(f'Pack manifest not found: {pack_id}')
        with open(manifest_path, 'r') as f:
            return json.load(f)

    def load_pack_blob(self, directory: str, pack_id: str, blob_id: str) -> bytes:
        """Load raw blob data from a change pack."""
        pending_dir = self.storage.bare_pending_dir(directory)
        blob_path   = os.path.join(pending_dir, pack_id, blob_id)
        if not os.path.isfile(blob_path):
            raise FileNotFoundError(f'Blob not found: {pack_id}/{blob_id}')
        with open(blob_path, 'rb') as f:
            return f.read()

    def delete_pack(self, directory: str, pack_id: str) -> bool:
        """Remove a change pack after it has been drained."""
        import shutil
        pending_dir = self.storage.bare_pending_dir(directory)
        pack_dir    = os.path.join(pending_dir, pack_id)
        if os.path.isdir(pack_dir):
            shutil.rmtree(pack_dir)
            return True
        return False
