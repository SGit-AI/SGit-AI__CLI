import base64
import hashlib
import math
from   urllib.request                                import Request, urlopen
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sgit_ai.network.api.Vault__API                    import Vault__API, LARGE_BLOB_THRESHOLD, MAX_BATCH_OPS
from   sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from   sgit_ai.storage.Vault__Object_Store       import Vault__Object_Store
from   sgit_ai.storage.Vault__Ref_Manager        import Vault__Ref_Manager
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
                              write_key: str = None,
                              on_progress: callable = None,
                              force: bool = False,
                              skip_missing_trees: bool = False) -> tuple:
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
                                              ciphertext, write_key, on_progress)
                if uploaded:
                    uploaded_ids.add(blob_id)
                    large_uploaded += 1
                    continue
            operations.append(dict(op      = Enum__Batch_Op.WRITE.value,
                                   file_id = f'bare/data/{blob_id}',
                                   data    = base64.b64encode(ciphertext).decode('ascii')))
            uploaded_ids.add(blob_id)

        from sgit_ai.storage.Vault__Commit import Vault__Commit
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
                                       operations, uploaded_ids, skip_missing=skip_missing_trees)

        # Update named branch ref — unconditional write for force push, CAS otherwise
        ref_ciphertext = ref_manager.encrypt_ref_value(clone_commit_id, read_key)
        if force:
            ref_op = dict(op      = Enum__Batch_Op.WRITE.value,
                          file_id = f'bare/refs/{named_ref_id}',
                          data    = base64.b64encode(ref_ciphertext).decode('ascii'))
        elif expected_ref_hash:
            ref_op = dict(op      = Enum__Batch_Op.WRITE_IF_MATCH.value,
                          file_id = f'bare/refs/{named_ref_id}',
                          data    = base64.b64encode(ref_ciphertext).decode('ascii'),
                          match   = expected_ref_hash)
        else:                                                        # no ref on the server yet (a new branch, a first push)
            ref_op = dict(op      = Enum__Batch_Op.WRITE.value,
                          file_id = f'bare/refs/{named_ref_id}',
                          data    = base64.b64encode(ref_ciphertext).decode('ascii'))
        operations.append(ref_op)

        return operations, large_uploaded

    def _upload_large(self, vault_id: str, file_id: str,
                      ciphertext: bytes, write_key: str,
                      on_progress: callable = None) -> bool:
        """Upload a large blob via S3 presigned multipart.

        Returns True on success, False if presigned is not available
        (caller falls back to including the blob in the normal batch).
        """
        _p        = on_progress or (lambda *a, **k: None)
        num_parts = max(1, math.ceil(len(ciphertext) / LARGE_PART_SIZE))
        size_mb   = len(ciphertext) / (1024 * 1024)
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

        total_parts = len(part_urls)
        debug_log   = getattr(self.api, 'debug_log', None)

        def _put_part(part_info):
            part_num = part_info['part_number']
            start    = (part_num - 1) * part_size
            chunk    = ciphertext[start : start + part_size]
            _p('step', f'Uploading large blob ({size_mb:.1f} MB) part {part_num}/{total_parts}')
            self.api.check_presigned_url(part_info['upload_url'])     # never PUT our ciphertext to a non-https URL
            req = Request(part_info['upload_url'], data=chunk, method='PUT')
            req.add_header('Content-Type', 'application/octet-stream')
            entry = debug_log.log_request('PUT', part_info['upload_url'], len(chunk)) if debug_log else None
            with urlopen(req, timeout=300) as resp:
                etag      = resp.headers.get('ETag', '')
                resp_body = resp.read()
                if entry:
                    debug_log.log_response(entry, resp.status, len(resp_body))
            return {'part_number': part_num, 'etag': etag}

        completed_parts = []
        try:
            if total_parts > 1:
                from concurrent.futures import ThreadPoolExecutor, as_completed
                with ThreadPoolExecutor(max_workers=total_parts) as executor:
                    futures = {executor.submit(_put_part, pi): pi for pi in part_urls}
                    for future in as_completed(futures):
                        completed_parts.append(future.result())
                completed_parts.sort(key=lambda p: p['part_number'])
            else:
                completed_parts.append(_put_part(part_urls[0]))

            self.api.presigned_complete(vault_id, file_id, upload_id,
                                        completed_parts, write_key)
            return True
        except Exception:
            try:
                self.api.presigned_cancel(vault_id, upload_id, file_id, write_key)
            except Exception:
                pass
            raise

    def collect_chain_blob_entries(self, commit_chain: list, named_commit_id: str,
                                   obj_store: Vault__Object_Store, read_key: bytes,
                                   skip_missing_trees: bool = False) -> list:
        """Every blob referenced by ANY commit being pushed, as [{'blob_id': …}].

        Push used to upload only the blobs in the clone HEAD tree that the remote
        HEAD tree lacked. A file created in one commit and changed in the next
        before pushing left its first version referenced by a tree on the server
        but never uploaded: 41 such objects on the DC vault after four days of
        agents committing several times per run, every one an older version of a
        file. The trees were uploaded (per commit, below); the blobs were not.
        Each tree is decrypted once however many commits share it."""
        import json
        from sgit_ai.storage.Vault__Commit import Vault__Commit
        from sgit_ai.crypto.PKI__Crypto   import PKI__Crypto
        vault_commit  = Vault__Commit(crypto=self.crypto, pki=PKI__Crypto(),
                                      object_store=obj_store, ref_manager=None)
        visited_trees = set()
        blob_ids      = []
        seen_blobs    = set()

        def walk(tree_id):
            if not tree_id or tree_id in visited_trees:
                return
            visited_trees.add(tree_id)
            if skip_missing_trees and not obj_store.exists(tree_id):
                return                                 # a scoped clone's sibling folder: unchanged, already on the server
            tree = json.loads(self.crypto.decrypt(read_key, obj_store.load(tree_id)))
            for entry in tree.get('entries', []):
                bid = entry.get('blob_id')
                if bid and bid not in seen_blobs:
                    if not obj_store.exists(bid):
                        continue                       # not local (sparse, scoped sibling, pulled history): it came from the server, so it is there
                    seen_blobs.add(bid)
                    blob_ids.append(bid)
                walk(entry.get('tree_id'))

        for cid in commit_chain:
            if not cid or cid == named_commit_id:
                continue
            try:
                walk(str(vault_commit.load_commit(cid, read_key).tree_id))
            except Exception:
                continue                               # an absent commit object: nothing of it to push
        return [dict(blob_id=bid) for bid in blob_ids]

    def _collect_tree_objects(self, tree_id: str, obj_store: Vault__Object_Store,
                              read_key: bytes, operations: list, uploaded_ids: set,
                              skip_missing: bool = False) -> None:
        """Recursively collect all tree objects (root + sub-trees) for upload.
        skip_missing: a scoped clone holds only its folders' trees; a tree it
        never fetched is unchanged and already on the server."""
        if tree_id in uploaded_ids:
            return
        if skip_missing and not obj_store.exists(tree_id):
            uploaded_ids.add(tree_id)
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
                                           operations, uploaded_ids, skip_missing=skip_missing)

    def execute_batch(self, vault_id: str, write_key: str, operations: list) -> dict:
        """Execute a batch of operations via the API, splitting into chunks if needed.

        Two limits apply:
          - Lambda body limit: ~6 MB per request → cap base64 data at 4 MB per chunk
          - Server operation limit: 100 ops per batch → cap at MAX_BATCH_OPS per chunk

        Returns the last chunk's API response. Raises on CAS conflict.
        """
        MAX_B64_BYTES = 4 * 1024 * 1024  # 4 MB base64 budget per chunk

        # Fast path: fits in one shot (data budget AND op count both within limits)
        total_b64 = sum(len(op.get('data', '')) for op in operations)
        if total_b64 <= MAX_B64_BYTES and len(operations) <= MAX_BATCH_OPS:
            return self._checked(self.api.batch(vault_id, write_key, operations))

        # Split into chunks respecting both the data budget and the op-count limit
        chunks        = []
        current_chunk = []
        current_size  = 0
        for op in operations:
            op_size = len(op.get('data', ''))
            if current_chunk and (current_size + op_size > MAX_B64_BYTES or
                                  len(current_chunk) >= MAX_BATCH_OPS):
                chunks.append(current_chunk)
                current_chunk = [op]
                current_size  = op_size
            else:
                current_chunk.append(op)
                current_size += op_size
        if current_chunk:
            chunks.append(current_chunk)

        # Plain-write chunks are independent — send in parallel.
        # WRITE_IF_MATCH (CAS ref update) must be last to preserve atomicity.
        cas_value    = Enum__Batch_Op.WRITE_IF_MATCH.value
        last         = lambda op: op['op'] == cas_value or str(op.get('file_id', '')).startswith('bare/refs/')   # a ref only after its objects
        plain_chunks = [c for c in chunks if not any(last(op) for op in c)]
        cas_chunks   = [c for c in chunks if     any(last(op) for op in c)]

        result = {}
        if len(plain_chunks) > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=len(plain_chunks)) as executor:
                futures = {executor.submit(self.api.batch, vault_id, write_key, c): c
                           for c in plain_chunks}
                for future in as_completed(futures):
                    result = self._checked(future.result())   # raises on error, and on any op not 'ok'
        elif plain_chunks:
            result = self._checked(self.api.batch(vault_id, write_key, plain_chunks[0]))

        for chunk in cas_chunks:
            result = self._checked(self.api.batch(vault_id, write_key, chunk))
        return result

    def _checked(self, result) -> dict:
        """Raise Vault__Push_Conflict_Error when the server reports a compare-and-swap
        miss: the in-memory API at the top level, the live server on the operation
        itself inside an HTTP 200 (`results[i].status == 'conflict'`)."""
        result = result or {}
        conflicted = str(result.get('status', 'ok')) == 'conflict' or any(
            isinstance(r, dict) and str(r.get('status', 'ok')) == 'conflict' for r in (result.get('results') or []))
        if conflicted:
            from sgit_ai.core.Vault__Errors import Vault__Push_Conflict_Error
            raise Vault__Push_Conflict_Error(
                'the branch moved on the server while this push was in flight (a teammate pushed first); '
                'nothing was overwritten and nothing of yours is lost. Run: sgit pull, then sgit push again.')
        failed = [r for r in (result.get('results') or [])                      # any other op that is not 'ok' is a
                  if isinstance(r, dict) and str(r.get('status', 'ok')) != 'ok']  # failed push, never a silent success
        if failed or str(result.get('status', 'ok')) not in ('ok', ''):
            first = failed[0] if failed else result
            raise RuntimeError(f'the server did not accept part of the push '
                               f'({first.get("file_id", "batch")}: {first.get("status")} {first.get("message", "")}'.rstrip() + ')')
        return result

    def execute_individually(self, vault_id: str, write_key: str, operations: list) -> dict:
        """Fallback: execute operations one-by-one via individual API calls.

        Used when the batch endpoint is not available (e.g. older servers).
        The batch format uses paths like 'bare/data/obj-xxx' for file_id,
        and individual API calls must use the same full path so objects are
        stored at the correct location (e.g. under bare/data/, bare/refs/).
        Returns a summary dict.
        """
        for op in operations:                                          # compare first: a lost race uploads nothing
            if op['op'] == Enum__Batch_Op.WRITE_IF_MATCH.value and op.get('match'):
                self._require_current(vault_id, op['file_id'], op['match'])
        results = []
        for op in operations:
            op_type = op['op']
            file_id = op['file_id']

            if op_type == Enum__Batch_Op.WRITE_IF_MATCH.value and op.get('match'):
                self._require_current(vault_id, file_id, op['match'])     # and again just before: one-by-one is not atomic
            if op_type in (Enum__Batch_Op.WRITE.value, Enum__Batch_Op.WRITE_IF_MATCH.value):
                payload = base64.b64decode(op['data'])
                self.api.write(vault_id, file_id, write_key, payload)
                results.append(dict(file_id=file_id, status='ok'))
            elif op_type == Enum__Batch_Op.DELETE.value:
                self.api.delete(vault_id, file_id, write_key)
                results.append(dict(file_id=file_id, status='ok'))

        return dict(status='ok', results=results)

    def _require_current(self, vault_id: str, file_id: str, match_b64: str) -> None:
        """The fallback's compare step: the file must still hold the bytes the
        compare-and-swap expected, else this push lost a race."""
        from sgit_ai.core.Vault__Errors import Vault__Push_Conflict_Error
        try:
            found   = self.api.batch_read(vault_id, [file_id]) or {}
        except Exception as error:                                     # cannot compare: say so, not "a teammate pushed"
            raise RuntimeError(f'could not read {file_id} from the server to compare it ({error}); '
                               f'nothing was overwritten. Try again.') from error
        current = found.get(file_id)
        if current is None or current != base64.b64decode(match_b64):
            raise Vault__Push_Conflict_Error(
                'the branch moved on the server while this push was in flight (a teammate pushed first); '
                'nothing was overwritten and nothing of yours is lost. Run: sgit pull, then sgit push again.')
