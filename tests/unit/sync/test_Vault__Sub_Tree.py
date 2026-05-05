"""Tests targeting uncovered lines in Vault__Sub_Tree."""
import json
import os
import tempfile
import shutil
import unittest.mock

from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from sgit_ai.storage.Vault__Object_Store       import Vault__Object_Store
from sgit_ai.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sgit_ai.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry
from sgit_ai.storage.Vault__Sub_Tree              import Vault__Sub_Tree
from sgit_ai.storage.Vault__Storage               import Vault__Storage


class Test_Vault__Sub_Tree:

    def setup_method(self):
        self.tmp_dir  = tempfile.mkdtemp()
        self.crypto   = Vault__Crypto()
        self.read_key = os.urandom(32)
        self.storage  = Vault__Storage()
        self.storage.create_bare_structure(self.tmp_dir)
        self.sg_dir    = self.storage.sg_vault_dir(self.tmp_dir)
        self.obj_store = Vault__Object_Store(vault_path=self.sg_dir, crypto=self.crypto)
        self.sub_tree  = Vault__Sub_Tree(crypto=self.crypto, obj_store=self.obj_store)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_file(self, rel_path: str, content: str):
        full = os.path.join(self.tmp_dir, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w') as f:
            f.write(content)

    def _store_tree(self, tree: Schema__Object_Tree) -> str:
        return self.sub_tree._store_tree(tree, self.read_key)

    # ------------------------------------------------------------------
    # Line 31: build() with old_flat_entries=None uses default {}
    # ------------------------------------------------------------------

    def test_build_no_old_flat_entries_defaults_to_empty(self):
        """Line 31: build() without old_flat_entries → old_flat_entries = {}."""
        self._write_file('file.txt', 'hello')
        tree_id = self.sub_tree.build(self.tmp_dir, {'file.txt': True}, self.read_key)
        assert tree_id is not None

    # ------------------------------------------------------------------
    # Line 60: build() skips path not in file_map
    # ------------------------------------------------------------------

    def test_build_skips_rel_path_not_in_file_map(self):
        """Line 60: a dir_contents entry with rel_path not in file_map → continue."""
        self._write_file('a.txt', 'aaa')
        self._write_file('b.txt', 'bbb')
        # Only include a.txt — b.txt is in the directory but not in file_map
        tree_id = self.sub_tree.build(self.tmp_dir, {'a.txt': True}, self.read_key)
        flat = self.sub_tree.flatten(tree_id, self.read_key)
        assert 'a.txt' in flat
        assert 'b.txt' not in flat

    # ------------------------------------------------------------------
    # Line 63: build() skips path where local file doesn't exist
    # ------------------------------------------------------------------

    def test_build_skips_nonexistent_file(self):
        """Line 63: rel_path in file_map but file missing → continue."""
        self._write_file('a.txt', 'aaa')
        # Include nonexistent.txt in file_map
        tree_id = self.sub_tree.build(self.tmp_dir,
                                      {'a.txt': True, 'nonexistent.txt': True},
                                      self.read_key)
        flat = self.sub_tree.flatten(tree_id, self.read_key)
        assert 'a.txt' in flat
        assert 'nonexistent.txt' not in flat

    # ------------------------------------------------------------------
    # Line 99: build() continue when child_dir has '/' in remainder
    # (a deep subdirectory is skipped when processing an ancestor dir)
    # ------------------------------------------------------------------

    def test_build_deep_nested_skips_non_immediate_subdirs(self):
        """Lines 93/99: deep nesting (a/b/c) causes continue for non-immediate subdirs."""
        self._write_file('a/b/c/deep.txt', 'deep')
        self._write_file('a/b/c/other.txt', 'other')
        tree_id = self.sub_tree.build(self.tmp_dir,
                                      {'a/b/c/deep.txt': True, 'a/b/c/other.txt': True},
                                      self.read_key)
        flat = self.sub_tree.flatten(tree_id, self.read_key)
        assert 'a/b/c/deep.txt' in flat
        assert 'a/b/c/other.txt' in flat

    # ------------------------------------------------------------------
    # Line 151: build_from_flat() skips entry with no entry_data
    # ------------------------------------------------------------------

    def test_build_from_flat_skips_missing_entry_data(self):
        """Line 151: path in dir_contents but entry_data is None → continue."""
        # A None value in flat_map means entry_data is falsy → skipped.
        flat_map = {'file.txt': None}
        tree_id = self.sub_tree.build_from_flat(flat_map, self.read_key)
        assert tree_id is not None
        result = self.sub_tree.flatten(tree_id, self.read_key)
        assert result == {}

    # ------------------------------------------------------------------
    # Lines 168/170-174: build_from_flat() deep-nested subdirs
    # ------------------------------------------------------------------

    def test_build_from_flat_deep_nested_dirs(self):
        """Lines 168-174: deep subdirs trigger the child_dir loop logic."""
        blob_id = self.obj_store.store(self.crypto.encrypt(self.read_key, b'content'))
        flat_map = {
            'a/b/c/file.txt':   {'blob_id': blob_id, 'size': 7, 'content_hash': ''},
            'a/b/c/other.txt':  {'blob_id': blob_id, 'size': 7, 'content_hash': ''},
            'a/x/file.txt':     {'blob_id': blob_id, 'size': 7, 'content_hash': ''},
        }
        tree_id = self.sub_tree.build_from_flat(flat_map, self.read_key)
        result  = self.sub_tree.flatten(tree_id, self.read_key)
        assert 'a/b/c/file.txt'  in result
        assert 'a/b/c/other.txt' in result
        assert 'a/x/file.txt'    in result

    # ------------------------------------------------------------------
    # Line 201: flatten() skips entry with no name
    # ------------------------------------------------------------------

    def test_flatten_skips_entry_with_no_name_enc(self):
        """Line 201: tree entry with no name_enc → _decrypt_name returns '' → continue."""
        tree = Schema__Object_Tree(schema='tree_v1')
        # Entry with no name_enc — _decrypt_name will return ''
        tree.entries.append(Schema__Object_Tree_Entry(blob_id='obj-cas-imm-aabbccddeeff'))
        tree_id = self._store_tree(tree)
        result  = self.sub_tree.flatten(tree_id, self.read_key)
        # Entry is skipped because name is empty
        assert result == {}

    # ------------------------------------------------------------------
    # Line 226: checkout() skips entry with no name
    # ------------------------------------------------------------------

    def test_checkout_skips_entry_with_no_name_enc(self):
        """Line 226: checkout skips tree entries with empty name_enc."""
        tree = Schema__Object_Tree(schema='tree_v1')
        tree.entries.append(Schema__Object_Tree_Entry(blob_id='obj-cas-imm-aabbccddeeff'))
        tree_id  = self._store_tree(tree)
        out_dir  = tempfile.mkdtemp()
        try:
            self.sub_tree.checkout(out_dir, tree_id, self.read_key)
            # Nothing written since name was empty
            assert os.listdir(out_dir) == []
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Lines 256, 261, 266, 271: decrypt helpers return defaults when enc is empty
    # ------------------------------------------------------------------

    def test_decrypt_name_no_enc_returns_empty(self):
        """Line 256: _decrypt_name returns '' when name_enc is empty."""
        entry  = Schema__Object_Tree_Entry()
        result = self.sub_tree._decrypt_name(entry, self.read_key)
        assert result == ''

    def test_decrypt_size_no_enc_returns_zero(self):
        """Line 261: _decrypt_size returns 0 when size_enc is empty."""
        entry  = Schema__Object_Tree_Entry()
        result = self.sub_tree._decrypt_size(entry, self.read_key)
        assert result == 0

    def test_decrypt_content_hash_no_enc_returns_empty(self):
        """Line 266: _decrypt_content_hash returns '' when content_hash_enc is empty."""
        entry  = Schema__Object_Tree_Entry()
        result = self.sub_tree._decrypt_content_hash(entry, self.read_key)
        assert result == ''

    def test_decrypt_content_type_no_enc_returns_default(self):
        """Line 271: _decrypt_content_type returns 'application/octet-stream' when empty."""
        entry  = Schema__Object_Tree_Entry()
        result = self.sub_tree._decrypt_content_type(entry, self.read_key)
        assert result == 'application/octet-stream'

    # ------------------------------------------------------------------
    # Lines 71-72: build() reuses old blob when content_hash matches
    # ------------------------------------------------------------------

    def test_build_reuses_old_blob_when_content_unchanged(self):
        """Lines 71-72: old_flat_entries has matching content_hash → blob_id reused."""
        self._write_file('file.txt', 'hello world')

        # First build to get a blob_id
        tree_id1 = self.sub_tree.build(self.tmp_dir, {'file.txt': True}, self.read_key)
        flat1    = self.sub_tree.flatten(tree_id1, self.read_key)
        old_blob_id = flat1['file.txt']['blob_id']

        # Rebuild with old_flat_entries containing the same content_hash
        tree_id2 = self.sub_tree.build(self.tmp_dir, {'file.txt': True}, self.read_key,
                                        old_flat_entries=flat1)
        flat2 = self.sub_tree.flatten(tree_id2, self.read_key)

        # Blob ID should be reused (same as the first build)
        assert flat2['file.txt']['blob_id'] == old_blob_id

    def test_build_reuses_old_blob_large_flag(self):
        """Line 72: is_large reused from old_entry when content_hash matches."""
        self._write_file('file.txt', 'some content')
        tree_id1 = self.sub_tree.build(self.tmp_dir, {'file.txt': True}, self.read_key)
        flat1    = self.sub_tree.flatten(tree_id1, self.read_key)
        # Rebuild with old_flat_entries — large flag is preserved
        tree_id2 = self.sub_tree.build(self.tmp_dir, {'file.txt': True}, self.read_key,
                                        old_flat_entries=flat1)
        flat2 = self.sub_tree.flatten(tree_id2, self.read_key)
        assert flat2['file.txt']['large'] == flat1['file.txt']['large']

    # ------------------------------------------------------------------
    # Lines 228-238: checkout() writes files and recurses into sub-trees
    # ------------------------------------------------------------------

    def test_checkout_writes_file_to_directory(self):
        """Lines 230-236: checkout() writes blob content to working directory."""
        self._write_file('hello.txt', 'hello world')
        tree_id = self.sub_tree.build(self.tmp_dir, {'hello.txt': True}, self.read_key)

        out_dir = tempfile.mkdtemp()
        try:
            self.sub_tree.checkout(out_dir, tree_id, self.read_key)
            assert os.path.isfile(os.path.join(out_dir, 'hello.txt'))
            with open(os.path.join(out_dir, 'hello.txt'), 'rb') as f:
                assert f.read() == b'hello world'
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_checkout_recurses_into_subdirectory(self):
        """Lines 237-238: checkout() recurses into tree_id entries (sub-dirs)."""
        self._write_file('sub/file.txt', 'nested content')
        tree_id = self.sub_tree.build(self.tmp_dir, {'sub/file.txt': True}, self.read_key)

        out_dir = tempfile.mkdtemp()
        try:
            self.sub_tree.checkout(out_dir, tree_id, self.read_key)
            nested = os.path.join(out_dir, 'sub', 'file.txt')
            assert os.path.isfile(nested)
            with open(nested, 'rb') as f:
                assert f.read() == b'nested content'
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    def test_build_make_entry_skips_path_not_in_file_map_line_36(self):
        """Line 36: make_entry(rel_path not in file_map) → return None (skip entry)."""
        self._write_file('real.txt', 'content')
        orig_populate = self.sub_tree._populate_dir_contents

        def patched_populate(paths):
            dir_contents, all_dirs = orig_populate(paths)
            # Inject an extra entry whose rel_path is NOT in file_map
            dir_contents.setdefault('', []).append(('ghost.txt', 'ghost.txt'))
            return dir_contents, all_dirs

        file_map = {'real.txt': True}
        with unittest.mock.patch.object(self.sub_tree, '_populate_dir_contents', patched_populate):
            tree_id = self.sub_tree.build(self.tmp_dir, file_map, self.read_key)
        # ghost.txt was skipped (line 36); real.txt should still be in the tree
        flat = self.sub_tree.flatten(tree_id, self.read_key)
        assert 'real.txt' in flat
        assert 'ghost.txt' not in flat
