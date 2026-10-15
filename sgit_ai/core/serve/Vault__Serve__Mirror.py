"""Vault__Serve__Mirror — moving a clone's work to and from the local server `sgit serve` runs.

The local server is a working copy of the vault for the browser, not a second remote: the
clone's remote-tracking state (its copy of the server's named ref, the accepted-head
baselines that rewind detection relies on) belongs to the vault's real server and is never
touched here. So:

  * push (clone -> local server): uploads every object the server lacks, and moves the
    server's named ref to this clone's head, only forward (compare-and-swap; the server's
    head must be in this clone's history), so nothing made in the browser is lost;
  * pull (local server -> clone): fetches the server's head and its objects (verified
    before write), checks the signature policy, and fast-forwards this clone's own branch
    to it, files checked out, exactly like `sgit history reset` to a newer commit. Then a
    plain `sgit push` sends that work to the real server.

Diverged histories are refused with what to do, never merged silently.
"""
import base64
import json
import os
from   sgit_ai.core.Vault__Sync__Base                       import Vault__Sync__Base
from   sgit_ai.core.Vault__Errors                           import Vault__Serve_Error

MAX_OPS_PER_BATCH   = 50
MAX_BYTES_PER_BATCH = 4 * 1024 * 1024


class Vault__Serve__Mirror(Vault__Sync__Base):

    # ------------------------------------------------------------ helpers
    def _heads(self, directory: str) -> dict:
        c       = self._init_components(directory)
        index   = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        config  = self._read_local_config(directory, c.storage)
        clone   = c.branch_manager.get_branch_by_id(index, str(config.my_branch_id))
        named   = c.branch_manager.tracked_named_branch(index, str(config.my_branch_id))
        if clone is None or named is None:
            raise Vault__Serve_Error('this clone has no branch to serve (is it a read-only clone?)')
        head = c.ref_manager.read_ref(str(clone.head_ref_id), c.read_key) or ''
        return dict(c=c, head=head, named_ref_file=f'bare/refs/{named.head_ref_id}', clone_ref_id=str(clone.head_ref_id))

    def _server_head(self, c, named_ref_file: str) -> tuple:
        """(raw bytes or None, commit id or '')."""
        raw = (self.api.batch_read(str(c.vault_id), [named_ref_file]) or {}).get(named_ref_file)
        if not raw:
            return None, ''
        commit = self._parse_ref_bytes(c, raw)
        if not commit:
            raise Vault__Serve_Error(f'the local server\'s ref {named_ref_file} does not decrypt with this vault\'s key')
        return raw, commit

    def _parse_ref_bytes(self, c, raw: bytes) -> str:
        import json
        try:
            return json.loads(self.crypto.decrypt(c.read_key, raw)).get('commit_id') or ''
        except Exception:
            return ''

    def _is_ancestor(self, c, ancestor: str, descendant: str) -> bool:
        from sgit_ai.core.actions.pull.Vault__Ref_Guard import Vault__Ref_Guard
        return ancestor == descendant or Vault__Ref_Guard(crypto=self.crypto).is_ancestor(c, c.read_key, ancestor, descendant)

    def _write_batches(self, c, ops: list) -> None:
        from sgit_ai.core.actions.index.Vault__Index_Sync import Vault__Index_Sync
        checker = Vault__Index_Sync(crypto=self.crypto, api=self.api)
        batch, size = [], 0
        for op in ops + [None]:
            if op is None or len(batch) >= MAX_OPS_PER_BATCH or size + len(op['data']) > MAX_BYTES_PER_BATCH:
                if batch:
                    checker.require_written(self.api.batch(str(c.vault_id), str(c.write_key), batch), 'objects')
                batch, size = [], 0
            if op is not None:
                batch.append(op)
                size += len(op['data'])

    # -------------------------------------------------------------- push
    def sent_record(self, record_path: str) -> set:
        try:
            with open(record_path) as f:
                return set(json.load(f))
        except (OSError, ValueError, TypeError):
            return set()

    def save_sent(self, record_path: str, sent: set) -> None:
        if not record_path:
            return
        os.makedirs(os.path.dirname(record_path), exist_ok=True)
        with open(record_path + '.tmp', 'w') as f:
            json.dump(sorted(sent), f)
        os.replace(record_path + '.tmp', record_path)

    def push(self, directory: str, force: bool = False, record_path: str = '') -> dict:
        """Clone -> local server. Returns dict(uploaded, head, moved). Objects are immutable,
        so the ones already sent are remembered in `record_path` (the server's list endpoint
        returned nothing in disk mode on SG/Send v0.34.0, so it is only a hint)."""
        heads   = self._heads(directory)
        c       = heads['c']
        bare    = os.path.join(c.sg_dir, 'bare')
        try:
            listed = set(self.api.list_files(str(c.vault_id), 'bare/') or [])
        except Exception:
            listed = set()
        sent      = self.sent_record(record_path)
        on_server = listed | sent
        ops, refs = [], []
        for root, _, files in os.walk(bare):
            for name in files:
                full    = os.path.join(root, name)
                file_id = os.path.relpath(full, c.sg_dir).replace(os.sep, '/')
                if file_id.startswith('bare/refs/'):
                    refs.append((file_id, full))
                    continue
                if file_id in on_server and not file_id.startswith('bare/indexes/'):   # the index changes: resend
                    continue
                with open(full, 'rb') as f:
                    ops.append(dict(op='write', file_id=file_id, data=base64.b64encode(f.read()).decode('ascii')))
        self._write_batches(c, ops)
        self.save_sent(record_path, sent | {op['file_id'] for op in ops if not op['file_id'].startswith('bare/indexes/')})

        others  = [(file_id, full) for file_id, full in refs if file_id != heads['named_ref_file']]
        present = self.api.batch_read(str(c.vault_id), [file_id for file_id, _ in others]) if others else {}
        ref_ops = []
        for file_id, full in others:                             # other refs: create when missing, never overwrite
            if (present or {}).get(file_id):
                continue
            with open(full, 'rb') as f:
                ref_ops.append(dict(op='write-if-match', file_id=file_id, match=None,
                                    data=base64.b64encode(f.read()).decode('ascii')))
        moved = self._move_server_head(c, heads, force, ref_ops)
        objects = [op for op in ops if not op['file_id'].startswith('bare/indexes/')]
        return dict(uploaded=len(objects), head=heads['head'], moved=moved)

    def _move_server_head(self, c, heads: dict, force: bool, ref_ops: list) -> bool:
        head = heads['head']
        raw, server_head = self._server_head(c, heads['named_ref_file'])
        if head and server_head != head:
            if server_head and not force and not self._is_ancestor(c, server_head, head):
                raise Vault__Serve_Error(
                    f'the local server has commits this clone does not ({server_head[:24]}…, probably made in the '
                    f'browser): bring them in first with `sgit serve pull`, then run this again. '
                    f'(`sgit serve push --force` discards them.)')
            data = c.ref_manager.encrypt_ref_value(head, c.read_key)
            ref_ops.append(dict(op='write-if-match', file_id=heads['named_ref_file'],
                                match=base64.b64encode(raw).decode('ascii') if raw else None,
                                data=base64.b64encode(data).decode('ascii')))
        if not ref_ops:
            return False
        from sgit_ai.core.actions.index.Vault__Index_Sync import Vault__Index_Sync
        result = self.api.batch(str(c.vault_id), str(c.write_key), ref_ops)
        if Vault__Index_Sync(crypto=self.crypto, api=self.api)._cas_conflict(result)[0]:   # both reply shapes
            raise Vault__Serve_Error('the local server\'s head changed while it was being updated (an edit in the '
                                     'browser?); run the command again')
        return any(op['file_id'] == heads['named_ref_file'] for op in ref_ops)

    # -------------------------------------------------------------- pull
    def pull(self, directory: str) -> dict:
        """Local server -> clone (fast-forward only). Returns dict(status, from, to)."""
        heads = self._heads(directory)
        c     = heads['c']
        _, server_head = self._server_head(c, heads['named_ref_file'])
        head  = heads['head']
        if not server_head or server_head == head:
            return dict(status='up_to_date', head=head)
        from sgit_ai.core.actions.status.Vault__Sync__Status import Vault__Sync__Status
        if not Vault__Sync__Status(crypto=self.crypto, api=None).status(directory).get('clean', True):
            raise Vault__Serve_Error('this clone has uncommitted changes: commit or stash them, then run '
                                     '`sgit serve pull` again; nothing was changed')
        from sgit_ai.core.actions.pull.Vault__Sync__Pull import Vault__Sync__Pull
        puller = Vault__Sync__Pull(crypto=self.crypto, api=self.api)
        puller._fetch_missing_objects(str(c.vault_id), server_head, c.obj_store, c.read_key, c.sg_dir)  # verified before write
        if head and not self._is_ancestor(c, head, server_head):
            raise Vault__Serve_Error(
                'this clone and the local server both have new commits (diverged). Push this clone\'s work to the '
                'real server first (`sgit push`), then `sgit serve push --force` to restart the local server from '
                'it, or keep the browser\'s work by moving yours aside; nothing was changed')
        from sgit_ai.core.actions.pull.Vault__Incoming_Check import Vault__Incoming_Check
        Vault__Incoming_Check(crypto=self.crypto, api=self.api).require_signatures(directory, c, c.read_key,
                                                                                   server_head, head)
        puller.reset(directory, server_head)
        return dict(status='updated', **{'from': head, 'to': server_head})
