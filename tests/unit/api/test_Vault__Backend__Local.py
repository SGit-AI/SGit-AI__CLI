import os
import tempfile
import shutil

from sg_send_cli.api.Vault__Backend__Local import Vault__Backend__Local


class Test_Vault__Backend__Local:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.backend = Vault__Backend__Local(root_path=self.tmp_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_write_and_read(self):
        self.backend.write('bare/data/obj-abc123', b'hello world')
        data = self.backend.read('bare/data/obj-abc123')
        assert data == b'hello world'

    def test_read_nonexistent_raises(self):
        import pytest
        with pytest.raises(FileNotFoundError):
            self.backend.read('nonexistent')

    def test_delete(self):
        self.backend.write('test-file', b'data')
        assert self.backend.exists('test-file')
        self.backend.delete('test-file')
        assert not self.backend.exists('test-file')

    def test_delete_nonexistent_no_error(self):
        result = self.backend.delete('nonexistent')
        assert result['status'] == 'ok'

    def test_list_files_empty(self):
        files = self.backend.list_files()
        assert files == []

    def test_list_files_with_prefix(self):
        self.backend.write('bare/data/obj-aaa', b'a')
        self.backend.write('bare/data/obj-bbb', b'b')
        self.backend.write('bare/refs/ref-ccc', b'c')

        data_files = self.backend.list_files('bare/data')
        assert len(data_files) == 2
        assert 'bare/data/obj-aaa' in data_files
        assert 'bare/data/obj-bbb' in data_files

        ref_files = self.backend.list_files('bare/refs')
        assert len(ref_files) == 1
        assert 'bare/refs/ref-ccc' in ref_files

    def test_list_files_all(self):
        self.backend.write('file1', b'a')
        self.backend.write('sub/file2', b'b')
        files = self.backend.list_files()
        assert len(files) == 2

    def test_exists(self):
        assert not self.backend.exists('missing')
        self.backend.write('present', b'data')
        assert self.backend.exists('present')

    def test_write_creates_subdirectories(self):
        self.backend.write('deep/nested/path/file.bin', b'data')
        assert self.backend.exists('deep/nested/path/file.bin')
        data = self.backend.read('deep/nested/path/file.bin')
        assert data == b'data'

    def test_overwrite(self):
        self.backend.write('file', b'version1')
        self.backend.write('file', b'version2')
        assert self.backend.read('file') == b'version2'

    def test_batch_write_and_delete(self):
        import base64
        ops = [
            dict(op='write', file_id='file1', data=base64.b64encode(b'data1').decode()),
            dict(op='write', file_id='file2', data=base64.b64encode(b'data2').decode()),
        ]
        result = self.backend.batch(ops)
        assert result['status'] == 'ok'
        assert self.backend.read('file1') == b'data1'
        assert self.backend.read('file2') == b'data2'

        ops2 = [dict(op='delete', file_id='file1')]
        self.backend.batch(ops2)
        assert not self.backend.exists('file1')
        assert self.backend.exists('file2')
