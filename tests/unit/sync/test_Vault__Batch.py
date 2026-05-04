import base64
import hashlib
import os
import tempfile
import shutil

from sgit_ai.crypto.Vault__Crypto             import Vault__Crypto
from sgit_ai.api.Vault__API__In_Memory        import Vault__API__In_Memory
from sgit_ai.core.actions.push.Vault__Batch                import Vault__Batch
from sgit_ai.sync.Vault__Sync                 import Vault__Sync
from sgit_ai.safe_types.Enum__Batch_Op        import Enum__Batch_Op
from tests.unit.sync.vault_test_env           import Vault__Test_Env


class Test_Vault__Batch:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'init.txt': 'init'})

    def setup_method(self):
        self.env      = self._env.restore()
        self.crypto   = self.env.crypto
        self.api      = self.env.api
        self.sync     = self.env.sync
        self.tmp_dir  = self.env.tmp_dir
        # vault directory from the snapshot
        self._vault_dir_path = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()

    def _get_vault(self):
        """Return the pre-initialised vault directory."""
        return self._vault_dir_path

    def test_push_uses_batch_api(self):
        directory = self._get_vault()
        batch_count_after_init = self.api._batch_count
        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('content')
        self.sync.commit(directory, message='add file')

        result = self.sync.push(directory)
        assert result['status']  == 'pushed'
        # Phase A (blobs) + Phase B (commits/trees/ref) each make at least one batch call
        assert self.api._batch_count >= batch_count_after_init + 1

    def test_push_batch_includes_write_if_match(self):
        directory = self._get_vault()
        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('content')
        self.sync.commit(directory, message='add file')

        batch_obj  = Vault__Batch(crypto=self.crypto, api=self.api)
        result     = self.sync.push(directory)
        assert result['status'] == 'pushed'

    def test_push_fallback_to_individual_when_batch_fails(self):
        directory = self._get_vault()
        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('content')
        self.sync.commit(directory, message='add file')

        original_batch = self.api.batch
        def failing_batch(*args, **kwargs):
            raise RuntimeError('Batch not supported')
        self.api.batch = failing_batch

        result = self.sync.push(directory)
        assert result['status'] == 'pushed'
        assert self.api._write_count > 0

        self.api.batch = original_batch

    def test_push_uses_individual_when_use_batch_false(self):
        directory = self._get_vault()
        batch_count_after_init = self.api._batch_count
        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('content')
        self.sync.commit(directory, message='add file')

        result = self.sync.push(directory, use_batch=False)
        assert result['status']     == 'pushed'
        assert self.api._batch_count == batch_count_after_init
        assert self.api._write_count > 0

    def test_batch_execute_individually(self):
        batch = Vault__Batch(crypto=self.crypto, api=self.api)
        operations = [
            dict(op=Enum__Batch_Op.WRITE.value,
                 file_id='bare/data/obj-aaa',
                 data=base64.b64encode(b'hello').decode()),
            dict(op=Enum__Batch_Op.DELETE.value,
                 file_id='bare/data/obj-bbb'),
        ]
        result = batch.execute_individually('test-vault', 'write-key', operations)
        assert result['status'] == 'ok'
        assert len(result['results']) == 2
        assert self.api._store['test-vault/bare/data/obj-aaa'] == b'hello'

    def test_batch_cas_conflict_detection(self):
        self.api._store['vault1/bare/refs/ref-named'] = b'old-ref-value'

        operations = [
            dict(op='write-if-match',
                 file_id='bare/refs/ref-named',
                 data=base64.b64encode(b'new-ref-value').decode(),
                 match=base64.b64encode(b'wrong-value').decode())
        ]
        result = self.api.batch('vault1', 'write-key', operations)
        assert result['status'] == 'conflict'

    def test_batch_cas_success(self):
        old_value = b'old-ref-value'
        self.api._store['vault1/bare/refs/ref-named'] = old_value

        operations = [
            dict(op='write-if-match',
                 file_id='bare/refs/ref-named',
                 data=base64.b64encode(b'new-ref-value').decode(),
                 match=base64.b64encode(old_value).decode())
        ]
        result = self.api.batch('vault1', 'write-key', operations)
        assert result['status'] == 'ok'
        assert self.api._store['vault1/bare/refs/ref-named'] == b'new-ref-value'

    def test_second_push_is_delta_only(self):
        directory = self._get_vault()

        with open(os.path.join(directory, 'first.txt'), 'w') as f:
            f.write('first')
        self.sync.commit(directory, message='first')
        self.sync.push(directory)

        first_batch_count = self.api._batch_count
        first_write_count = self.api._write_count

        with open(os.path.join(directory, 'second.txt'), 'w') as f:
            f.write('second')
        self.sync.commit(directory, message='second')
        result = self.sync.push(directory)

        assert result['status'] == 'pushed'
        assert result['objects_uploaded'] == 1
        # Phase A (blob batch) + Phase B (commits/trees/ref batch) = at least 2 batch calls
        assert self.api._batch_count >= first_batch_count + 1
