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
