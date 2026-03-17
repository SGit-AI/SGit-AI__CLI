import os
import tempfile
import shutil
from sg_send_cli.sync.Vault__Merge                 import Vault__Merge
from sg_send_cli.crypto.Vault__Crypto              import Vault__Crypto
from sg_send_cli.objects.Vault__Object_Store       import Vault__Object_Store
from sg_send_cli.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sg_send_cli.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry


class Test_Vault__Merge:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.merger = Vault__Merge(crypto=self.crypto)

    def _make_tree(self, entries_dict: dict) -> Schema__Object_Tree:
        tree = Schema__Object_Tree(schema='tree_v1')
        for path, blob_id in entries_dict.items():
            tree.entries.append(Schema__Object_Tree_Entry(path=path, blob_id=blob_id, size=10))
        return tree

    def test_identical_trees_no_changes(self):
        base   = self._make_tree({'a.txt': 'aabbccddeeff'})
        ours   = self._make_tree({'a.txt': 'aabbccddeeff'})
        theirs = self._make_tree({'a.txt': 'aabbccddeeff'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert result['conflicts'] == []
        assert result['added']     == []
        assert result['modified']  == []
        assert result['deleted']   == []
        assert len(result['merged_tree'].entries) == 1

    def test_theirs_adds_file(self):
        base   = self._make_tree({'a.txt': 'aabbccddeeff'})
        ours   = self._make_tree({'a.txt': 'aabbccddeeff'})
        theirs = self._make_tree({'a.txt': 'aabbccddeeff', 'b.txt': '112233445566'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert 'b.txt' in result['added']
        assert result['conflicts'] == []
        paths = [str(e.path) for e in result['merged_tree'].entries]
        assert 'b.txt' in paths

    def test_theirs_modifies_file(self):
        base   = self._make_tree({'a.txt': 'aabbccddeeff'})
        ours   = self._make_tree({'a.txt': 'aabbccddeeff'})
        theirs = self._make_tree({'a.txt': '112233445566'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert 'a.txt' in result['modified']
        assert result['conflicts'] == []
        entry = result['merged_tree'].entries[0]
        assert str(entry.blob_id) == '112233445566'

    def test_ours_modifies_theirs_unchanged(self):
        base   = self._make_tree({'a.txt': 'aabbccddeeff'})
        ours   = self._make_tree({'a.txt': '112233445566'})
        theirs = self._make_tree({'a.txt': 'aabbccddeeff'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert result['conflicts'] == []
        entry = result['merged_tree'].entries[0]
        assert str(entry.blob_id) == '112233445566'

    def test_both_modify_same_content_no_conflict(self):
        base   = self._make_tree({'a.txt': 'aabbccddeeff'})
        ours   = self._make_tree({'a.txt': '112233445566'})
        theirs = self._make_tree({'a.txt': '112233445566'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert result['conflicts'] == []

    def test_both_modify_different_content_conflict(self):
        base   = self._make_tree({'a.txt': 'aabbccddeeff'})
        ours   = self._make_tree({'a.txt': '112233445566'})
        theirs = self._make_tree({'a.txt': 'ffeeddccbbaa'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert 'a.txt' in result['conflicts']

    def test_theirs_deletes_unchanged_file(self):
        base   = self._make_tree({'a.txt': 'aabbccddeeff', 'b.txt': '112233445566'})
        ours   = self._make_tree({'a.txt': 'aabbccddeeff', 'b.txt': '112233445566'})
        theirs = self._make_tree({'a.txt': 'aabbccddeeff'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert 'b.txt' in result['deleted']
        assert result['conflicts'] == []
        paths = [str(e.path) for e in result['merged_tree'].entries]
        assert 'b.txt' not in paths

    def test_theirs_deletes_modified_file_conflict(self):
        base   = self._make_tree({'a.txt': 'aabbccddeeff'})
        ours   = self._make_tree({'a.txt': '112233445566'})
        theirs = self._make_tree({})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert 'a.txt' in result['conflicts']

    def test_both_add_same_file_different_content_conflict(self):
        base   = self._make_tree({})
        ours   = self._make_tree({'new.txt': 'aabbccddeeff'})
        theirs = self._make_tree({'new.txt': '112233445566'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert 'new.txt' in result['conflicts']

    def test_both_add_same_file_same_content_no_conflict(self):
        base   = self._make_tree({})
        ours   = self._make_tree({'new.txt': 'aabbccddeeff'})
        theirs = self._make_tree({'new.txt': 'aabbccddeeff'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert result['conflicts'] == []

    def test_both_delete_same_file(self):
        base   = self._make_tree({'a.txt': 'aabbccddeeff'})
        ours   = self._make_tree({})
        theirs = self._make_tree({})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert 'a.txt' in result['deleted']
        assert result['conflicts'] == []

    def test_complex_merge(self):
        base   = self._make_tree({'a.txt': 'aabbccddeeff', 'b.txt': '112233445566', 'c.txt': 'ffeeddccbbaa'})
        ours   = self._make_tree({'a.txt': 'aabbccddeeff', 'b.txt': 'aaaa11112222', 'd.txt': '999888777666'})
        theirs = self._make_tree({'a.txt': '000000000000', 'c.txt': 'ffeeddccbbaa', 'e.txt': '555444333222'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert 'a.txt' in result['modified']       # theirs changed, ours didn't
        assert 'b.txt' in result['conflicts']      # ours modified, theirs deleted -> conflict
        paths = [str(e.path) for e in result['merged_tree'].entries]
        assert 'a.txt' in paths                     # theirs version
        assert 'b.txt' in paths                     # ours modified (kept in conflict)
        assert 'c.txt' not in paths                 # theirs deleted, ours unchanged
        assert 'd.txt' in paths                     # ours added
        assert 'e.txt' in paths                     # theirs added

    def test_empty_trees(self):
        base   = self._make_tree({})
        ours   = self._make_tree({})
        theirs = self._make_tree({})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert result['conflicts'] == []
        assert len(result['merged_tree'].entries) == 0

    def test_ours_deletes_theirs_modifies_conflict(self):
        base   = self._make_tree({'a.txt': 'aabbccddeeff'})
        ours   = self._make_tree({})
        theirs = self._make_tree({'a.txt': '112233445566'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert 'a.txt' in result['conflicts']
        paths = [str(e.path) for e in result['merged_tree'].entries]
        assert 'a.txt' in paths

    def test_ours_deletes_theirs_unchanged(self):
        base   = self._make_tree({'a.txt': 'aabbccddeeff'})
        ours   = self._make_tree({})
        theirs = self._make_tree({'a.txt': 'aabbccddeeff'})
        result = self.merger.three_way_merge(base, ours, theirs)
        assert result['conflicts'] == []
        paths = [str(e.path) for e in result['merged_tree'].entries]
        assert 'a.txt' not in paths


class Test_Vault__Merge__Conflict_Files:

    def setup_method(self):
        self.tmp_dir   = tempfile.mkdtemp()
        self.crypto    = Vault__Crypto()
        self.merger    = Vault__Merge(crypto=self.crypto)
        self.read_key  = os.urandom(32)

        sg_dir = os.path.join(self.tmp_dir, '.sg_vault', 'bare', 'data')
        os.makedirs(sg_dir, exist_ok=True)
        self.obj_store = Vault__Object_Store(vault_path=os.path.join(self.tmp_dir, '.sg_vault'),
                                              crypto=self.crypto)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _store_blob(self, content: bytes) -> str:
        encrypted = self.crypto.encrypt(self.read_key, content)
        return self.obj_store.store(encrypted)

    def _make_tree(self, entries_dict: dict) -> Schema__Object_Tree:
        tree = Schema__Object_Tree(schema='tree_v1')
        for path, blob_id in entries_dict.items():
            tree.entries.append(Schema__Object_Tree_Entry(path=path, blob_id=blob_id, size=10))
        return tree

    def test_write_conflict_files_creates_files(self):
        content    = b'theirs version content'
        blob_id    = self._store_blob(content)
        ours_tree  = self._make_tree({'a.txt': 'aabbccddeeff'})
        theirs_tree = self._make_tree({'a.txt': blob_id})
        conflicts  = ['a.txt']

        written = self.merger.write_conflict_files(self.tmp_dir, conflicts,
                                                    ours_tree, theirs_tree,
                                                    self.obj_store, self.read_key)
        assert 'a.txt.conflict' in written
        conflict_path = os.path.join(self.tmp_dir, 'a.txt.conflict')
        assert os.path.isfile(conflict_path)
        with open(conflict_path, 'rb') as f:
            assert f.read() == content

    def test_write_conflict_files_skips_missing_entry(self):
        ours_tree   = self._make_tree({'a.txt': 'aabbccddeeff'})
        theirs_tree = self._make_tree({})
        conflicts   = ['a.txt']

        written = self.merger.write_conflict_files(self.tmp_dir, conflicts,
                                                    ours_tree, theirs_tree,
                                                    self.obj_store, self.read_key)
        assert written == []

    def test_remove_conflict_files(self):
        conflict_path = os.path.join(self.tmp_dir, 'a.txt.conflict')
        with open(conflict_path, 'w') as f:
            f.write('conflict content')

        removed = self.merger.remove_conflict_files(self.tmp_dir)
        assert len(removed) == 1
        assert 'a.txt.conflict' in removed[0]
        assert not os.path.isfile(conflict_path)

    def test_remove_conflict_files_empty(self):
        removed = self.merger.remove_conflict_files(self.tmp_dir)
        assert removed == []

    def test_has_conflicts_true(self):
        conflict_path = os.path.join(self.tmp_dir, 'a.txt.conflict')
        with open(conflict_path, 'w') as f:
            f.write('conflict')
        assert self.merger.has_conflicts(self.tmp_dir) is True

    def test_has_conflicts_false(self):
        assert self.merger.has_conflicts(self.tmp_dir) is False

    def test_has_conflicts_ignores_hidden_dirs(self):
        hidden_dir = os.path.join(self.tmp_dir, '.hidden')
        os.makedirs(hidden_dir)
        with open(os.path.join(hidden_dir, 'x.conflict'), 'w') as f:
            f.write('hidden')
        assert self.merger.has_conflicts(self.tmp_dir) is False
