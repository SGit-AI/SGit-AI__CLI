import base64
import hashlib
import os
import tempfile
import shutil

from sg_send_cli.crypto.Vault__Crypto             import Vault__Crypto
from sg_send_cli.api.Vault__API__In_Memory        import Vault__API__In_Memory
from sg_send_cli.sync.Vault__Batch                import Vault__Batch
from sg_send_cli.sync.Vault__Sync                 import Vault__Sync
from sg_send_cli.safe_types.Enum__Batch_Op        import Enum__Batch_Op


class Test_Vault__Batch:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _init_vault(self, name='test-vault'):
        directory = os.path.join(self.tmp_dir, name)
        result    = self.sync.init(directory)
        self.sync.push(directory)                    # upload bare structure to server
        return result, directory

    def test_push_uses_batch_api(self):
        _, directory = self._init_vault()
        batch_count_after_init = self.api._batch_count
        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('content')
        self.sync.commit(directory, message='add file')

        result = self.sync.push(directory)
        assert result['status']  == 'pushed'
        assert self.api._batch_count == batch_count_after_init + 1

    def test_push_batch_includes_write_if_match(self):
        _, directory = self._init_vault()
        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('content')
        self.sync.commit(directory, message='add file')

        batch_obj  = Vault__Batch(crypto=self.crypto, api=self.api)
        result     = self.sync.push(directory)
        assert result['status'] == 'pushed'

    def test_push_fallback_to_individual_when_batch_fails(self):
        _, directory = self._init_vault()
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
        _, directory = self._init_vault()
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
        assert self.api._store['test-vault/obj-aaa'] == b'hello'

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
        _, directory = self._init_vault()

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
        assert self.api._batch_count == first_batch_count + 1
