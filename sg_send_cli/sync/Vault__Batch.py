import base64
import hashlib
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sg_send_cli.api.Vault__API                    import Vault__API
from   sg_send_cli.crypto.Vault__Crypto              import Vault__Crypto
from   sg_send_cli.objects.Vault__Object_Store       import Vault__Object_Store
from   sg_send_cli.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from   sg_send_cli.safe_types.Enum__Batch_Op         import Enum__Batch_Op


class Vault__Batch(Type_Safe):
    crypto : Vault__Crypto
    api    : Vault__API

    def build_push_operations(self, obj_store: Vault__Object_Store,
                              ref_manager: Vault__Ref_Manager,
                              clone_tree_entries: list,
                              named_blob_ids: set,
                              commit_chain: list,
                              named_commit_id: str,
                              read_key: bytes,
                              named_ref_id: str,
                              clone_commit_id: str,
                              expected_ref_hash: str = None) -> list:
        """Build the list of batch operations for a push.

        Returns a list of operation dicts ready for the batch API.
        """
        operations = []

        for entry in clone_tree_entries:
            blob_id = str(entry.blob_id) if entry.blob_id else None
            if not blob_id or blob_id in named_blob_ids:
                continue
            ciphertext = obj_store.load(blob_id)
            operations.append(dict(op      = Enum__Batch_Op.WRITE.value,
                                   file_id = f'bare/data/{blob_id}',
                                   data    = base64.b64encode(ciphertext).decode('ascii')))

        from sg_send_cli.objects.Vault__Commit import Vault__Commit
        from sg_send_cli.crypto.PKI__Crypto   import PKI__Crypto
        pki          = PKI__Crypto()
        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                      object_store=obj_store, ref_manager=ref_manager)

        for cid in commit_chain:
            if cid == named_commit_id:
                continue
            commit_ciphertext = obj_store.load(cid)
            operations.append(dict(op      = Enum__Batch_Op.WRITE.value,
                                   file_id = f'bare/data/{cid}',
                                   data    = base64.b64encode(commit_ciphertext).decode('ascii')))
            c       = vault_commit.load_commit(cid, read_key)
            tree_id = str(c.tree_id)
            tree_ciphertext = obj_store.load(tree_id)
            operations.append(dict(op      = Enum__Batch_Op.WRITE.value,
                                   file_id = f'bare/data/{tree_id}',
                                   data    = base64.b64encode(tree_ciphertext).decode('ascii')))

        ref_ciphertext = ref_manager.encrypt_ref_value(clone_commit_id, read_key)
        ref_op = dict(op      = Enum__Batch_Op.WRITE_IF_MATCH.value,
                      file_id = f'bare/refs/{named_ref_id}',
                      data    = base64.b64encode(ref_ciphertext).decode('ascii'))
        if expected_ref_hash:
            ref_op['match'] = expected_ref_hash
        operations.append(ref_op)

        return operations

    def execute_batch(self, vault_id: str, write_key: str, operations: list) -> dict:
        """Execute a batch of operations via the API.

        Returns the API response. Raises on CAS conflict.
        """
        return self.api.batch(vault_id, write_key, operations)

    def execute_individually(self, vault_id: str, write_key: str, operations: list) -> dict:
        """Fallback: execute operations one-by-one via individual API calls.

        Used when the batch endpoint is not available (e.g. older servers).
        The batch format uses paths like 'bare/data/obj-xxx' for file_id,
        but individual API calls use just the filename portion.
        Returns a summary dict.
        """
        results = []
        for op in operations:
            op_type = op['op']
            file_id = op['file_id']
            api_file_id = file_id.split('/')[-1] if '/' in file_id else file_id

            if op_type in (Enum__Batch_Op.WRITE.value, Enum__Batch_Op.WRITE_IF_MATCH.value):
                payload = base64.b64decode(op['data'])
                self.api.write(vault_id, api_file_id, write_key, payload)
                results.append(dict(file_id=file_id, status='ok'))
            elif op_type == Enum__Batch_Op.DELETE.value:
                self.api.delete(vault_id, api_file_id, write_key)
                results.append(dict(file_id=file_id, status='ok'))

        return dict(status='ok', results=results)
