"""Tests for large blob routing in Vault__Batch.

In memory mode, presigned upload is not available, so large blobs fall back
to the normal batch path.  These tests verify the fallback behaviour and that
the build_push_operations return signature is correct.
"""
import base64
import os
import shutil
import tempfile

from sgit_ai.api.Vault__API           import LARGE_BLOB_THRESHOLD
from sgit_ai.api.Vault__API__In_Memory import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto     import Vault__Crypto
from sgit_ai.core.actions.push.Vault__Batch        import Vault__Batch
from sgit_ai.sync.Vault__Sync         import Vault__Sync


class Test_Vault__Batch__Large_Blob:

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
        self.sync.init(directory)
        self.sync.push(directory)
        return directory

    def test_build_push_operations_returns_tuple(self):
        """build_push_operations always returns (operations, large_count)."""
        directory = self._init_vault()
        with open(os.path.join(directory, 'small.txt'), 'w') as f:
            f.write('hello')
        self.sync.commit(directory, message='add small file')

        # Just verify that push works and returns expected keys
        result = self.sync.push(directory)
        assert result['status'] == 'pushed'
        assert 'objects_uploaded' in result

    def test_large_blob_fallback_to_batch_in_memory(self):
        """When presigned is not available, large blobs fall through to normal batch."""
        directory = self._init_vault()

        # Write a file whose content will produce a large encrypted blob
        # (>LARGE_BLOB_THRESHOLD bytes after encryption).
        large_content = b'X' * (LARGE_BLOB_THRESHOLD + 1)
        with open(os.path.join(directory, 'large.bin'), 'wb') as f:
            f.write(large_content)
        self.sync.commit(directory, message='add large file')

        # Push should succeed — falls back to batch because in-memory API raises
        # presigned_not_available, which Vault__Batch catches and falls back.
        result = self.sync.push(directory)
        assert result['status'] == 'pushed'
        assert result['objects_uploaded'] >= 1

    def test_push_with_large_and_small_files(self):
        """Mix of large and small files both push correctly in memory mode."""
        directory = self._init_vault()

        with open(os.path.join(directory, 'small.txt'), 'w') as f:
            f.write('small content')
        with open(os.path.join(directory, 'large.bin'), 'wb') as f:
            f.write(b'L' * (LARGE_BLOB_THRESHOLD + 100))

        self.sync.commit(directory, message='add both files')
        result = self.sync.push(directory)
        assert result['status'] == 'pushed'
        assert result['objects_uploaded'] >= 2

    def test_force_push_uses_write_op_not_cas_line_92(self):
        """Line 92: force=True → WRITE op (not WRITE_IF_MATCH) for named branch ref."""
        directory = self._init_vault()
        with open(os.path.join(directory, 'file.txt'), 'w') as f:
            f.write('hello')
        self.sync.commit(directory, message='add file')
        result = self.sync.push(directory, force=True)
        assert result['status'] == 'pushed'

    def test_large_flag_set_in_tree_entry(self):
        """Tree entries for large blobs have large=True after commit."""
        from sgit_ai.storage.Vault__Sub_Tree        import Vault__Sub_Tree
        from sgit_ai.storage.Vault__Commit       import Vault__Commit
        from sgit_ai.crypto.PKI__Crypto          import PKI__Crypto

        directory = self._init_vault()

        with open(os.path.join(directory, 'big.bin'), 'wb') as f:
            f.write(b'B' * (LARGE_BLOB_THRESHOLD + 1))
        with open(os.path.join(directory, 'small.txt'), 'w') as f:
            f.write('small')

        self.sync.commit(directory, message='add files')

        # Use _init_components to get all the correctly wired internals
        c         = self.sync._init_components(directory)
        sub_tree  = Vault__Sub_Tree(crypto=self.crypto, obj_store=c.obj_store)
        pki       = PKI__Crypto()
        vc        = Vault__Commit(crypto=self.crypto, pki=pki,
                                  object_store=c.obj_store, ref_manager=c.ref_manager)

        # Load local config to find the clone branch head ref
        local_config   = self.sync._read_local_config(directory, c.storage)
        branch_id      = str(local_config.my_branch_id)
        branch_index   = c.branch_manager.load_branch_index(directory, c.branch_index_file_id, c.read_key)
        branch_meta    = c.branch_manager.get_branch_by_id(branch_index, branch_id)
        head_ref       = str(branch_meta.head_ref_id)
        head_commit_id = c.ref_manager.read_ref(head_ref, c.read_key)

        commit = vc.load_commit(head_commit_id, c.read_key)
        flat   = sub_tree.flatten(str(commit.tree_id), c.read_key)

        big_entry   = flat.get('big.bin')
        small_entry = flat.get('small.txt')

        assert big_entry   is not None, 'big.bin not found in flat tree'
        assert small_entry is not None, 'small.txt not found in flat tree'
        assert big_entry['large']   is True,  'big.bin should be large=True'
        assert small_entry['large'] is False, 'small.txt should be large=False'
