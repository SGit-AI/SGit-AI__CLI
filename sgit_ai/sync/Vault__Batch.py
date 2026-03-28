import base64
import hashlib
import math
from   urllib.request                                import Request, urlopen
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sgit_ai.api.Vault__API                    import Vault__API, LARGE_BLOB_THRESHOLD
from   sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from   sgit_ai.objects.Vault__Object_Store       import Vault__Object_Store
from   sgit_ai.objects.Vault__Ref_Manager        import Vault__Ref_Manager
from   sgit_ai.safe_types.Enum__Batch_Op         import Enum__Batch_Op

LARGE_PART_SIZE = 10 * 1024 * 1024   # 10 MB per part (server max)


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
                              expected_ref_hash: str = None,
                              vault_id: str = None,
                              write_key: str = None) -> tuple:
        """Build the list of batch operations for a push.

        Large blobs (encrypted size > LARGE_BLOB_THRESHOLD) are uploaded
        immediately via the presigned multipart S3 path when write_key is
        provided and the API supports it.  They are excluded from the returned
        batch operations list.

        Returns (operations, large_uploaded_count).
        """
        operations       = []
        uploaded_ids     = set()
        large_uploaded   = 0

        # Upload new blobs (files not in the named branch)
        for entry in clone_tree_entries:
            blob_id = entry.get('blob_id') if isinstance(entry, dict) else (str(entry.blob_id) if entry.blob_id else None)
            if not blob_id or blob_id in named_blob_ids or blob_id in uploaded_ids:
                continue
            ciphertext = obj_store.load(blob_id)
            if vault_id and write_key and len(ciphertext) > LARGE_BLOB_THRESHOLD:
                uploaded = self._upload_large(vault_id, f'bare/data/{blob_id}',
                                              ciphertext, write_key)
                if uploaded:
                    uploaded_ids.add(blob_id)
                    large_uploaded += 1
                    continue
            operations.append(dict(op      = Enum__Batch_Op.WRITE.value,
                                   file_id = f'bare/data/{blob_id}',
                                   data    = base64.b64encode(ciphertext).decode('ascii')))
            uploaded_ids.add(blob_id)

        from sgit_ai.objects.Vault__Commit import Vault__Commit
        from sgit_ai.crypto.PKI__Crypto   import PKI__Crypto
        pki          = PKI__Crypto()
        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                      object_store=obj_store, ref_manager=ref_manager)

        # Upload commits and ALL tree objects (root + sub-trees)
        for cid in commit_chain:
            if cid == named_commit_id:
                continue

            # Upload commit object
            if cid not in uploaded_ids:
                commit_ciphertext = obj_store.load(cid)
                operations.append(dict(op      = Enum__Batch_Op.WRITE.value,
                                       file_id = f'bare/data/{cid}',
                                       data    = base64.b64encode(commit_ciphertext).decode('ascii')))
                uploaded_ids.add(cid)

            # Upload all tree objects reachable from this commit
            c       = vault_commit.load_commit(cid, read_key)
            tree_id = str(c.tree_id)
            self._collect_tree_objects(tree_id, obj_store, read_key,
                                       operations, uploaded_ids)

        # Update named branch ref (compare-and-swap)
        ref_ciphertext = ref_manager.encrypt_ref_value(clone_commit_id, read_key)
        ref_op = dict(op      = Enum__Batch_Op.WRITE_IF_MATCH.value,
                      file_id = f'bare/refs/{named_ref_id}',
                      data    = base64.b64encode(ref_ciphertext).decode('ascii'))
        if expected_ref_hash:
            ref_op['match'] = expected_ref_hash
        operations.append(ref_op)

        return operations, large_uploaded

    def _upload_large(self, vault_id: str, file_id: str,
                      ciphertext: bytes, write_key: str) -> bool:
        """Upload a large blob via S3 presigned multipart.

        Returns True on success, False if presigned is not available
        (caller falls back to including the blob in the normal batch).
        """
        num_parts = max(1, math.ceil(len(ciphertext) / LARGE_PART_SIZE))
        try:
            result    = self.api.presigned_initiate(vault_id, file_id,
                                                    len(ciphertext), num_parts, write_key)
            upload_id = result['upload_id']
            part_size = result.get('part_size', LARGE_PART_SIZE)
            part_urls = result['part_urls']
        except RuntimeError as e:
            if 'presigned_not_available' in str(e):
                return False
            raise

        completed_parts = []
        try:
            for part_info in part_urls:
                part_num  = part_info['part_number']
                start     = (part_num - 1) * part_size
                chunk     = ciphertext[start : start + part_size]
                req       = Request(part_info['upload_url'], data=chunk, method='PUT')
                req.add_header('Content-Type', 'application/octet-stream')
                with urlopen(req) as resp:
                    etag = resp.headers.get('ETag', '')
                completed_parts.append({'part_number': part_num, 'etag': etag})

            self.api.presigned_complete(vault_id, file_id, upload_id,
                                        completed_parts, write_key)
            return True
        except Exception:
            try:
                self.api.presigned_cancel(vault_id, upload_id, file_id, write_key)
            except Exception:
                pass
            raise

    def _collect_tree_objects(self, tree_id: str, obj_store: Vault__Object_Store,
                              read_key: bytes, operations: list, uploaded_ids: set) -> None:
        """Recursively collect all tree objects (root + sub-trees) for upload."""
        if tree_id in uploaded_ids:
            return

        tree_ciphertext = obj_store.load(tree_id)
        operations.append(dict(op      = Enum__Batch_Op.WRITE.value,
                               file_id = f'bare/data/{tree_id}',
                               data    = base64.b64encode(tree_ciphertext).decode('ascii')))
        uploaded_ids.add(tree_id)

        # Decrypt tree to find sub-tree references
        import json
        tree_data = self.crypto.decrypt(read_key, tree_ciphertext)
        tree_dict = json.loads(tree_data)
        for entry in tree_dict.get('entries', []):
            sub_tree_id = entry.get('tree_id', '')
            if sub_tree_id and sub_tree_id not in uploaded_ids:
                self._collect_tree_objects(sub_tree_id, obj_store, read_key,
                                           operations, uploaded_ids)

    def execute_batch(self, vault_id: str, write_key: str, operations: list) -> dict:
        """Execute a batch of operations via the API.

        Returns the API response. Raises on CAS conflict.
        """
        return self.api.batch(vault_id, write_key, operations)

    def execute_individually(self, vault_id: str, write_key: str, operations: list) -> dict:
        """Fallback: execute operations one-by-one via individual API calls.

        Used when the batch endpoint is not available (e.g. older servers).
        The batch format uses paths like 'bare/data/obj-xxx' for file_id,
        and individual API calls must use the same full path so objects are
        stored at the correct location (e.g. under bare/data/, bare/refs/).
        Returns a summary dict.
        """
        results = []
        for op in operations:
            op_type = op['op']
            file_id = op['file_id']

            if op_type in (Enum__Batch_Op.WRITE.value, Enum__Batch_Op.WRITE_IF_MATCH.value):
                payload = base64.b64decode(op['data'])
                self.api.write(vault_id, file_id, write_key, payload)
                results.append(dict(file_id=file_id, status='ok'))
            elif op_type == Enum__Batch_Op.DELETE.value:
                self.api.delete(vault_id, file_id, write_key)
                results.append(dict(file_id=file_id, status='ok'))

        return dict(status='ok', results=results)
