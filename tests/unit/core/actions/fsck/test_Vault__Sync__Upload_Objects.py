"""Tests for Vault__Sync__Upload_Objects — re-uploading local bare/data/ objects to the
server (the recovery half of `sgit check fsck`). Driven through Vault__Sync.upload_objects
against a real vault and the in-memory host; nothing is mocked."""
import os
import shutil
import tempfile

from sgit_ai.core.actions.fsck.Vault__Sync__Upload_Objects import UPLOAD_CHUNK, Vault__Sync__Upload_Objects
from sgit_ai.core.Vault__Sync                             import Vault__Sync
from sgit_ai.network.api.Vault__API                       import Vault__API
from sgit_ai.storage.Vault__Storage                       import SG_VAULT_DIR
from tests._helpers.vault_test_env                        import Vault__Test_Env


class Test_Vault__Sync__Upload_Objects:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'alpha', 'docs/b.md': 'bravo', 'docs/sub/c.md': 'charlie'})

    @classmethod
    def teardown_class(cls):
        if cls._env:
            cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env      = self._env.restore()
        self.sync     = self.env.sync
        self.api      = self.env.api
        self.d        = self.env.vault_dir
        self.data_dir = os.path.join(self.d, SG_VAULT_DIR, 'bare', 'data')
        self.vault_id = self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)['vault_id']

    def teardown_method(self):
        self.env.cleanup()

    # ── helpers ─────────────────────────────────────────────────────────
    def local_object_ids(self) -> list:
        return sorted(os.listdir(self.data_dir))

    def server_key(self, oid: str) -> str:
        return f'{self.vault_id}/bare/data/{oid}'

    # ── facade ──────────────────────────────────────────────────────────
    def test_facade_delegates_to_upload_objects(self):
        """Vault__Sync.upload_objects builds a Vault__Sync__Upload_Objects with the same
        crypto and api and returns its summary dict unchanged (ok/uploaded/missing_locally/errors)."""
        assert isinstance(self.sync, Vault__Sync)
        direct = Vault__Sync__Upload_Objects(crypto=self.env.crypto, api=self.api).upload_objects(self.d, [])
        via    = self.sync.upload_objects(self.d, [])
        assert direct == via == dict(ok=True, uploaded=[], missing_locally=[], errors=[])

    # ── guards ──────────────────────────────────────────────────────────
    def test_not_a_vault_directory_fails_before_touching_the_server(self):
        """A directory with no .sg_vault/ returns ok=False with a 'Not a vault' error and
        makes no server request."""
        plain = tempfile.mkdtemp()
        try:
            before = self.api._batch_count
            result = self.sync.upload_objects(plain, ['deadbeef'])
            assert result['ok'] is False
            assert result['uploaded'] == [] and result['missing_locally'] == []
            assert result['errors'] == [f'Not a vault: {plain}']
            assert self.api._batch_count == before
        finally:
            shutil.rmtree(plain, ignore_errors=True)

    def test_unreadable_vault_config_is_reported_not_raised(self):
        """When the vault's local/ (key material + config) is gone, the components cannot be
        built: the error is wrapped as 'Cannot read vault config: ...' and ok=False, nothing raised."""
        shutil.rmtree(os.path.join(self.d, SG_VAULT_DIR, 'local'))
        events = []
        result = self.sync.upload_objects(self.d, self.local_object_ids()[:1],
                                          on_progress=lambda ev, msg, *a: events.append((ev, msg)))
        assert result['ok'] is False
        assert result['uploaded'] == []
        assert len(result['errors']) == 1
        assert result['errors'][0].startswith('Cannot read vault config: ')
        assert events == [('step', 'Reading vault configuration')]

    def test_read_only_clone_has_no_write_key_and_refuses(self):
        """A read-only clone (read key only) cannot upload: ok=False with the read-only
        clone error, no batch request is sent."""
        keys     = self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)
        ro_dir   = os.path.join(self.env.tmp_dir, 'ro')
        self.sync.clone_read_only(vault_id=keys['vault_id'], read_key_hex=keys['read_key'], directory=ro_dir)
        oid      = sorted(os.listdir(os.path.join(ro_dir, SG_VAULT_DIR, 'bare', 'data')))[0]
        before   = self.api._batch_count
        result   = self.sync.upload_objects(ro_dir, [oid])
        assert result['ok'] is False
        assert result['errors'] == ['No write key — cannot upload (read-only clone)']
        assert result['uploaded'] == []
        assert self.api._batch_count == before

    # ── the happy path ──────────────────────────────────────────────────
    def test_uploads_local_objects_the_server_lost_byte_for_byte(self):
        """Objects deleted from the host are restored from the local bare/data/ copies in one
        batch; the server bytes equal the local file bytes (no re-encryption) and the
        progress callback reports step/upload/step in order."""
        oids = self.local_object_ids()[:3]
        for oid in oids:
            self.api._store.pop(self.server_key(oid))
        events = []
        result = self.sync.upload_objects(self.d, oids, on_progress=lambda ev, msg, *a: events.append((ev, msg, a)))
        assert result == dict(ok=True, uploaded=oids, missing_locally=[], errors=[])
        for oid in oids:
            with open(os.path.join(self.data_dir, oid), 'rb') as f:
                assert self.api._store[self.server_key(oid)] == f.read()
        assert events == [('step',   'Reading vault configuration',                              ()),
                          ('step',   f'Uploading 3 object(s) in chunks of {UPLOAD_CHUNK}',       ()),
                          ('upload', 'Uploaded 3/3',                                             ('3 objects',)),
                          ('step',   'Uploaded 3 object(s)',                                     ())]

    def test_empty_id_list_is_ok_and_sends_nothing(self):
        """No ids: ok=True, no batch request, and no final 'Uploaded N' step (only the
        two leading steps)."""
        before = self.api._batch_count
        events = []
        result = self.sync.upload_objects(self.d, [], on_progress=lambda ev, msg, *a: events.append(msg))
        assert result == dict(ok=True, uploaded=[], missing_locally=[], errors=[])
        assert self.api._batch_count == before
        assert events == ['Reading vault configuration', f'Uploading 0 object(s) in chunks of {UPLOAD_CHUNK}']

    def test_a_fresh_clone_sees_the_restored_objects(self):
        """End-to-end recovery: after the host loses every object of the vault, uploading
        them from this clone's bare/data/ lets a brand-new clone extract the working copy."""
        oids = self.local_object_ids()
        for oid in oids:
            self.api._store.pop(self.server_key(oid))
        result = self.sync.upload_objects(self.d, oids)
        assert result['ok'] is True and sorted(result['uploaded']) == oids
        fresh = os.path.join(self.env.tmp_dir, 'fresh')
        self.sync.clone(self.env.vault_key, fresh)
        with open(os.path.join(fresh, 'docs', 'sub', 'c.md')) as f:
            assert f.read() == 'charlie'

    # ── partial availability ────────────────────────────────────────────
    def test_ids_absent_locally_are_reported_and_the_rest_still_upload(self):
        """An id with no local file lands in missing_locally and flips ok to False with a
        count message, but the ids that do exist are still uploaded."""
        present = self.local_object_ids()[0]
        self.api._store.pop(self.server_key(present))
        result = self.sync.upload_objects(self.d, ['0' * 64, present, 'f' * 64])
        assert result['ok'] is False
        assert result['missing_locally'] == ['0' * 64, 'f' * 64]
        assert result['uploaded'] == [present]
        assert result['errors'] == ['2 object(s) not found in local bare/data/ — this vault does not have them either']
        assert self.server_key(present) in self.api._store

    # ── chunking ────────────────────────────────────────────────────────
    def test_uploads_in_chunks_of_twenty(self):
        """More than UPLOAD_CHUNK ids go out as ceil(n / 20) batch requests, each
        progress 'upload' event carrying the running total and the chunk size."""
        n = UPLOAD_CHUNK + 3
        for i in range(n):
            with open(os.path.join(self.data_dir, f'{i:064x}'), 'wb') as f:
                f.write(b'synthetic-object-%d' % i)
        oids   = [f'{i:064x}' for i in range(n)]
        before = self.api._batch_count
        events = []
        result = self.sync.upload_objects(self.d, oids, on_progress=lambda ev, msg, *a: events.append((ev, msg, a)))
        assert result['ok'] is True and result['uploaded'] == oids
        assert self.api._batch_count - before == 2
        uploads = [e for e in events if e[0] == 'upload']
        assert uploads == [('upload', f'Uploaded {UPLOAD_CHUNK}/{n}', (f'{UPLOAD_CHUNK} objects',)),
                           ('upload', f'Uploaded {n}/{n}',            ('3 objects',))]
        for oid in oids:
            assert self.api._store[self.server_key(oid)] == b'synthetic-object-%d' % int(oid, 16)

    # ── server failure ──────────────────────────────────────────────────
    def test_unreachable_server_is_collected_per_chunk_and_later_chunks_still_run(self):
        """A host that cannot be reached (a closed loopback port, the real offline case)
        produces one error per chunk naming the chunk's first id; ok=False, uploaded stays
        empty, and the loop does not stop at the first failing chunk."""
        n = UPLOAD_CHUNK + 1
        for i in range(n):
            with open(os.path.join(self.data_dir, f'{i:064x}'), 'wb') as f:
                f.write(b'x')
        oids    = [f'{i:064x}' for i in range(n)]
        offline = Vault__Sync(crypto=self.env.crypto, api=Vault__API(base_url='http://127.0.0.1:9'))
        result  = offline.upload_objects(self.d, oids)
        assert result['ok'] is False
        assert result['uploaded'] == []
        assert len(result['errors']) == 2
        assert result['errors'][0].startswith(f'Batch upload failed for chunk starting {oids[0]}: ')
        assert result['errors'][1].startswith(f'Batch upload failed for chunk starting {oids[UPLOAD_CHUNK]}: ')

    def test_vault_id_sent_to_the_host_is_a_safe_str_not_a_plain_str(self):
        """Pins what the code does today: the vault id handed to api.batch is the Safe_Str
        from Vault__Components, not str(). An f-string host (the HTTP client) does not care;
        a host keyed by plain str does — the in-memory host's tombstone set never matches
        it, so a tombstoned vault still accepts the upload here."""
        oid = self.local_object_ids()[0]
        self.api._tombstones.add(self.vault_id)
        assert self.api._tombstones == {self.vault_id}
        result = self.sync.upload_objects(self.d, [oid])
        assert result['ok'] is True and result['uploaded'] == [oid]
