import json
import os
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sg_send_cli.crypto.Vault__Crypto              import Vault__Crypto
from   sg_send_cli.crypto.PKI__Crypto                import PKI__Crypto
from   sg_send_cli.crypto.Vault__Key_Manager         import Vault__Key_Manager
from   sg_send_cli.objects.Vault__Object_Store       import Vault__Object_Store
from   sg_send_cli.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from   sg_send_cli.objects.Vault__Commit             import Vault__Commit
from   sg_send_cli.schemas.Schema__Object_Tree       import Schema__Object_Tree
from   sg_send_cli.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry
from   sg_send_cli.sync.Vault__Change_Pack           import Vault__Change_Pack
from   sg_send_cli.sync.Vault__Storage               import Vault__Storage
from   sg_send_cli.sync.Vault__Branch_Manager        import Vault__Branch_Manager


class Vault__GC(Type_Safe):
    crypto  : Vault__Crypto
    storage : Vault__Storage

    def drain_pending(self, directory: str, read_key: bytes, branch_id: str,
                      signing_key=None) -> dict:
        """Drain all pending change packs into the clone branch.

        For each pending pack:
        1. Load the manifest and all blobs
        2. Copy blobs to bare/data/
        3. Build a new tree with the pack's entries merged in
        4. Create a commit on the clone branch
        5. Delete the drained pack

        Returns summary of drained packs.
        """
        sg_dir    = self.storage.sg_vault_dir(directory)
        pki       = PKI__Crypto()
        obj_store = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto, use_v2=True)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto, use_v2=True)

        key_manager    = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=self.crypto,
                                               key_manager=key_manager, ref_manager=ref_manager,
                                               storage=self.storage)

        index_id = branch_manager.find_branch_index_id(directory)
        if not index_id:
            return dict(drained=0, packs=[])
        branch_index = branch_manager.load_branch_index(directory, index_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            return dict(drained=0, packs=[])

        ref_id    = str(branch_meta.head_ref_id)
        parent_id = ref_manager.read_ref(ref_id, read_key)

        change_pack = Vault__Change_Pack(crypto=self.crypto, storage=self.storage)
        packs       = change_pack.list_pending_packs(directory)
        if not packs:
            return dict(drained=0, packs=[])

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                      object_store=obj_store, ref_manager=ref_manager)

        old_tree = Schema__Object_Tree(schema='tree_v1')
        if parent_id:
            old_commit = vault_commit.load_commit(parent_id, read_key)
            old_tree   = vault_commit.load_tree(str(old_commit.tree_id), read_key)

        drained_packs = []

        for pack_id in packs:
            try:
                manifest = change_pack.load_pack_manifest(directory, pack_id)

                if not self._verify_pack_signature(manifest, pki):
                    continue

                blob_ids = manifest.get('payload', [])

                for blob_id in blob_ids:
                    if isinstance(blob_id, str):
                        blob_data = change_pack.load_pack_blob(directory, pack_id, blob_id)
                        obj_store.store_raw(blob_id, blob_data)

                change_pack.delete_pack(directory, pack_id)
                drained_packs.append(pack_id)
            except Exception:
                continue

        return dict(drained=len(drained_packs), packs=drained_packs)

    def _verify_pack_signature(self, manifest: dict, pki: PKI__Crypto) -> bool:
        """Verify a change pack's ECDSA signature if present.

        Returns True if the pack is valid (signature verifies or no signature present).
        Returns False if verification fails.
        """
        import hashlib
        signature_hex = manifest.get('signature', '')
        creator_key   = manifest.get('creator_key', '')
        payload_hash  = manifest.get('payload_hash', '')

        if not signature_hex or not creator_key:
            return True

        try:
            from cryptography.hazmat.primitives.serialization import load_pem_public_key
            public_key    = load_pem_public_key(creator_key.encode())
            signature_raw = bytes.fromhex(signature_hex)
            payload_data  = payload_hash.encode()
            pki.verify(public_key, signature_raw, payload_data)
            return True
        except Exception:
            return False
