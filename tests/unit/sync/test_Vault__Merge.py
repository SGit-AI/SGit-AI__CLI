import os
import tempfile
import shutil
from sgit_ai.sync.Vault__Merge                 import Vault__Merge
from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from sgit_ai.objects.Vault__Object_Store       import Vault__Object_Store


class Test_Vault__Merge:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.merger = Vault__Merge(crypto=self.crypto)

    def _make_map(self, entries_dict: dict) -> dict:
        """Create a flat {path: {'blob_id': str}} map for merge."""
        result = {}
        for path, blob_id in entries_dict.items():
            if not blob_id.startswith('obj-cas-imm-'):
                blob_id = f'obj-cas-imm-{blob_id}'
            result[path] = {'blob_id': blob_id, 'size': 10, 'content_hash': ''}
        return result

    def test_identical_trees_no_changes(self):
        base   = self._make_map({'a.txt': 'aabbccddeeff'})
        ours   = self._make_map({'a.txt': 'aabbccddeeff'})
        theirs = self._make_map({'a.txt': 'aabbccddeeff'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert result['conflicts'] == []
        assert result['added']     == []
        assert result['modified']  == []
        assert result['deleted']   == []

    def test_theirs_adds_file(self):
        base   = self._make_map({'a.txt': 'aabbccddeeff'})
        ours   = self._make_map({'a.txt': 'aabbccddeeff'})
        theirs = self._make_map({'a.txt': 'aabbccddeeff', 'b.txt': '112233445566'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert result['added'] == ['b.txt']
        assert 'b.txt' in result['merged_map']

    def test_theirs_modifies_file(self):
        base   = self._make_map({'a.txt': 'aabbccddeeff'})
        ours   = self._make_map({'a.txt': 'aabbccddeeff'})
        theirs = self._make_map({'a.txt': '112233445566'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert result['modified'] == ['a.txt']
        entry  = result['merged_map']['a.txt']
        assert entry['blob_id'] == 'obj-cas-imm-112233445566'

    def test_ours_modifies_theirs_unchanged(self):
        base   = self._make_map({'a.txt': 'aabbccddeeff'})
        ours   = self._make_map({'a.txt': '112233445566'})
        theirs = self._make_map({'a.txt': 'aabbccddeeff'})
        result = self.merger.three_way_merge(base, ours, theirs)
        entry  = result['merged_map']['a.txt']
        assert entry['blob_id'] == 'obj-cas-imm-112233445566'

    def test_both_modify_same_content_no_conflict(self):
        base   = self._make_map({'a.txt': 'aabbccddeeff'})
        ours   = self._make_map({'a.txt': '112233445566'})
        theirs = self._make_map({'a.txt': '112233445566'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert result['conflicts'] == []

    def test_both_modify_different_content_conflict(self):
        base   = self._make_map({'a.txt': 'aabbccddeeff'})
        ours   = self._make_map({'a.txt': '112233445566'})
        theirs = self._make_map({'a.txt': 'ffeeddccbbaa'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert result['conflicts'] == ['a.txt']

    def test_theirs_deletes_unchanged_file(self):
        base   = self._make_map({'a.txt': 'aabbccddeeff', 'b.txt': '112233445566'})
        ours   = self._make_map({'a.txt': 'aabbccddeeff', 'b.txt': '112233445566'})
        theirs = self._make_map({'a.txt': 'aabbccddeeff'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert 'b.txt' in result['deleted']

    def test_theirs_deletes_modified_file_conflict(self):
        base   = self._make_map({'a.txt': 'aabbccddeeff'})
        ours   = self._make_map({'a.txt': '112233445566'})
        theirs = self._make_map({})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert 'a.txt' in result['conflicts']

    def test_both_add_same_file_different_content_conflict(self):
        base   = self._make_map({})
        ours   = self._make_map({'new.txt': 'aabbccddeeff'})
        theirs = self._make_map({'new.txt': '112233445566'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert 'new.txt' in result['conflicts']

    def test_both_add_same_file_same_content_no_conflict(self):
        base   = self._make_map({})
        ours   = self._make_map({'new.txt': 'aabbccddeeff'})
        theirs = self._make_map({'new.txt': 'aabbccddeeff'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert result['conflicts'] == []

    def test_both_delete_same_file(self):
        base   = self._make_map({'a.txt': 'aabbccddeeff'})
        ours   = self._make_map({})
        theirs = self._make_map({})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert 'a.txt' in result['deleted']

    def test_complex_merge(self):
        base   = self._make_map({'a.txt': 'aabbccddeeff', 'b.txt': '112233445566', 'c.txt': 'ffeeddccbbaa'})
        ours   = self._make_map({'a.txt': 'aabbccddeeff', 'b.txt': 'aaaa11112222', 'd.txt': '999888777666'})
        theirs = self._make_map({'a.txt': '000000000000', 'c.txt': 'ffeeddccbbaa', 'e.txt': '555444333222'})
        result = self.merger.three_way_merge(base, ours, theirs)
        # a: ours unchanged, theirs modified → take theirs (modified, not conflict)
        assert 'a.txt' in result['modified']
        # b: ours modified, theirs deleted → conflict
        assert 'b.txt' in result['conflicts']
        # d: added only by ours → in merged
        assert 'd.txt' in result['merged_map']
        # e: added only by theirs → in merged
        assert 'e.txt' in result['merged_map']

    def test_empty_trees(self):
        result = self.merger.three_way_merge({}, {}, {})
        assert result['merged_map'] == {}
        assert result['conflicts']  == []

    def test_ours_deletes_theirs_modifies_conflict(self):
        base   = self._make_map({'a.txt': 'aabbccddeeff'})
        ours   = self._make_map({})
        theirs = self._make_map({'a.txt': '112233445566'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert 'a.txt' in result['conflicts']

    def test_ours_deletes_theirs_unchanged(self):
        base   = self._make_map({'a.txt': 'aabbccddeeff'})
        ours   = self._make_map({})
        theirs = self._make_map({'a.txt': 'aabbccddeeff'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert result['conflicts'] == []


class Test_Vault__Merge__Conflict_Files:

    def setup_method(self):
        self.tmp_dir  = tempfile.mkdtemp()
        self.crypto   = Vault__Crypto()
        self.merger   = Vault__Merge(crypto=self.crypto)
        self.read_key = os.urandom(32)
        sg_dir        = os.path.join(self.tmp_dir, '.sg_vault')
        os.makedirs(os.path.join(sg_dir, 'bare', 'data'), exist_ok=True)
        self.store    = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_write_conflict_files_creates_files(self):
        content   = b'theirs version content'
        encrypted = self.crypto.encrypt(self.read_key, content)
        blob_id   = self.store.store(encrypted)

        theirs_map = {'a.txt': {'blob_id': blob_id}}
        written    = self.merger.write_conflict_files(self.tmp_dir, ['a.txt'],
                                                      theirs_map, self.store, self.read_key)
        assert len(written) == 1
        assert written[0] == 'a.txt.conflict'
        with open(os.path.join(self.tmp_dir, 'a.txt.conflict'), 'rb') as f:
            assert f.read() == content

    def test_write_conflict_files_skips_missing_entry(self):
        theirs_map = {}
        written    = self.merger.write_conflict_files(self.tmp_dir, ['missing.txt'],
                                                      theirs_map, self.store, self.read_key)
        assert written == []

    def test_remove_conflict_files(self):
        conflict_path = os.path.join(self.tmp_dir, 'a.txt.conflict')
        with open(conflict_path, 'w') as f:
            f.write('conflict')
        removed = self.merger.remove_conflict_files(self.tmp_dir)
        assert 'a.txt.conflict' in removed
        assert not os.path.exists(conflict_path)

    def test_has_conflicts(self):
        assert self.merger.has_conflicts(self.tmp_dir) is False
        with open(os.path.join(self.tmp_dir, 'x.conflict'), 'w') as f:
            f.write('c')
        assert self.merger.has_conflicts(self.tmp_dir) is True
