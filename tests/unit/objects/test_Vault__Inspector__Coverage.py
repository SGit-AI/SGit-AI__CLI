import json
import os
import tempfile
from sg_send_cli.objects.Vault__Inspector    import Vault__Inspector
from sg_send_cli.objects.Vault__Object_Store import Vault__Object_Store
from sg_send_cli.objects.Vault__Ref_Manager  import Vault__Ref_Manager
from sg_send_cli.crypto.Vault__Crypto        import Vault__Crypto
from sg_send_cli.schemas.Schema__Object_Commit import Schema__Object_Commit
from sg_send_cli.schemas.Schema__Object_Tree       import Schema__Object_Tree
from sg_send_cli.schemas.Schema__Object_Tree_Entry import Schema__Object_Tree_Entry


class Test_Vault__Inspector__Format_Methods:

    def setup_method(self):
        self.tmp_dir    = tempfile.mkdtemp()
        self.crypto     = Vault__Crypto()
        self.inspector  = Vault__Inspector(crypto=self.crypto)
        self.read_key   = os.urandom(32)

    def _vault_path(self):
        return os.path.join(self.tmp_dir, '.sg_vault')

    def _setup_vault_with_commit(self, message='Test commit', version=1, parent_id=None):
        vault_path   = os.path.join(self.tmp_dir, '.sg_vault')
        os.makedirs(vault_path, exist_ok=True)
        object_store = Vault__Object_Store(vault_path=vault_path, crypto=self.crypto)
        ref_manager  = Vault__Ref_Manager(vault_path=vault_path)

        blob_data    = self.crypto.encrypt(self.read_key, b'file content here')
        blob_id      = object_store.store(blob_data)

        tree = Schema__Object_Tree()
        tree.entries.append(Schema__Object_Tree_Entry(path='readme.md', blob_id=blob_id, size=17))
        tree_json      = json.dumps(tree.json()).encode()
        tree_encrypted = self.crypto.encrypt(self.read_key, tree_json)
        tree_id        = object_store.store(tree_encrypted)

        commit = Schema__Object_Commit(tree_id   = tree_id,
                                        timestamp = '2026-03-12T10:00:00.000Z',
                                        message   = message,
                                        version   = version,
                                        parent    = parent_id)
        commit_json      = json.dumps(commit.json()).encode()
        commit_encrypted = self.crypto.encrypt(self.read_key, commit_json)
        commit_id        = object_store.store(commit_encrypted)

        ref_manager.write_head(commit_id)
        return commit_id, tree_id, blob_id, object_store, ref_manager

    # --- format_vault_summary ---

    def test_format_vault_summary__no_vault(self):
        empty_dir = tempfile.mkdtemp()
        summary   = self.inspector.format_vault_summary(empty_dir)
        assert 'Vault Summary' in summary
        assert 'none' in summary

    def test_format_vault_summary__with_objects(self):
        commit_id, _, _, _, _ = self._setup_vault_with_commit()
        summary = self.inspector.format_vault_summary(self.tmp_dir)
        assert 'Vault Summary' in summary
        assert 'object-store' in summary
        assert commit_id in summary

    # --- format_object_detail ---

    def test_format_object_detail__missing_object(self):
        vault_path = self._vault_path()
        os.makedirs(vault_path, exist_ok=True)
        detail = self.inspector.format_object_detail(self.tmp_dir, 'aabbccddeeff')
        assert 'aabbccddeeff' in detail
        assert 'Exists:' in detail

    # --- format_commit_log ---

    def test_format_commit_log__single_commit(self):
        chain = [dict(commit_id='a1b2c3d4e5f6', version=1,
                       timestamp='2026-03-12T10:00:00Z',
                       message='Initial commit', tree_id='bbccdd112233',
                       parent=None)]
        result = self.inspector.format_commit_log(chain)
        assert 'a1b2c3d4e5f6' in result
        assert '(HEAD)' in result
        assert 'Initial commit' in result

    def test_format_commit_log__multi_commit(self):
        chain = [dict(commit_id='commit2aaaaa', version=2,
                       timestamp='2026-03-12T11:00:00Z',
                       message='Second commit', tree_id='tree2aaaaaaa',
                       parent='commit1aaaaa'),
                 dict(commit_id='commit1aaaaa', version=1,
                       timestamp='2026-03-12T10:00:00Z',
                       message='First commit', tree_id='tree1aaaaaaa',
                       parent=None)]
        result = self.inspector.format_commit_log(chain)
        assert 'commit2aaaaa' in result
        assert 'commit1aaaaa' in result
        assert '(HEAD)' in result

    def test_format_commit_log__oneline(self):
        chain = [dict(commit_id='a1b2c3d4e5f6', version=1,
                       timestamp='2026-03-12T10:00:00Z',
                       message='Test', tree_id='bbccdd112233',
                       parent=None)]
        result = self.inspector.format_commit_log(chain, oneline=True)
        assert 'a1b2c3d4e5f6' in result
        assert 'Test' in result

    def test_format_commit_log__graph(self):
        chain = [dict(commit_id='commit2aaaaa', version=2,
                       timestamp='2026-03-12T11:00:00Z',
                       message='Second', tree_id='tree2aaaaaaa',
                       parent='commit1aaaaa'),
                 dict(commit_id='commit1aaaaa', version=1,
                       timestamp='2026-03-12T10:00:00Z',
                       message='First', tree_id='tree1aaaaaaa',
                       parent=None)]
        result = self.inspector.format_commit_log(chain, graph=True)
        assert '*' in result
        assert 'v2' in result

    def test_format_commit_log__graph_oneline(self):
        chain = [dict(commit_id='aabbccddeeff', version=1,
                       message='Test', tree_id='112233445566',
                       parent=None)]
        result = self.inspector.format_commit_log(chain, oneline=True, graph=True)
        assert '*' in result
        assert 'v1' in result

    def test_format_commit_log__error_entry(self):
        chain = [dict(commit_id='aabbccddeeff', error='object not found locally')]
        result = self.inspector.format_commit_log(chain)
        assert 'object not found locally' in result

    def test_format_commit_log__error_entry_graph(self):
        chain = [dict(commit_id='aabbccddeeff', error='object not found locally')]
        result = self.inspector.format_commit_log(chain, graph=True)
        assert '*' in result
        assert 'object not found locally' in result

    # --- cat_object ---

    def test_cat_object__missing(self):
        vault_path = self._vault_path()
        os.makedirs(vault_path, exist_ok=True)
        result = self.inspector.cat_object(self.tmp_dir, 'aabbccddeeff', self.read_key)
        assert result['exists'] is False

    def test_cat_object__commit_type(self):
        commit_id, tree_id, blob_id, _, _ = self._setup_vault_with_commit()
        result = self.inspector.cat_object(self.tmp_dir, commit_id, self.read_key)
        assert result['exists'] is True
        assert result['type']   == 'commit'
        assert 'tree_id' in result['content']

    def test_cat_object__tree_type(self):
        commit_id, tree_id, blob_id, _, _ = self._setup_vault_with_commit()
        result = self.inspector.cat_object(self.tmp_dir, tree_id, self.read_key)
        assert result['exists'] is True
        assert result['type']   == 'tree'
        assert 'entries' in result['content']

    def test_cat_object__blob_type(self):
        commit_id, tree_id, blob_id, _, _ = self._setup_vault_with_commit()
        result = self.inspector.cat_object(self.tmp_dir, blob_id, self.read_key)
        assert result['exists']   is True
        assert result['type']     == 'blob'
        assert result['content']  == 'file content here'

    # --- format_cat_object ---

    def test_format_cat_object__missing(self):
        vault_path = self._vault_path()
        os.makedirs(vault_path, exist_ok=True)
        result = self.inspector.format_cat_object(self.tmp_dir, 'aabbccddeeff', self.read_key)
        assert 'not found' in result

    def test_format_cat_object__commit(self):
        commit_id, _, _, _, _ = self._setup_vault_with_commit()
        result = self.inspector.format_cat_object(self.tmp_dir, commit_id, self.read_key)
        assert 'Object:' in result
        assert 'commit' in result
        assert 'Tree' in result

    def test_format_cat_object__blob(self):
        commit_id, tree_id, blob_id, _, _ = self._setup_vault_with_commit()
        result = self.inspector.format_cat_object(self.tmp_dir, blob_id, self.read_key)
        assert 'blob' in result
        assert 'file content here' in result

    # --- inspect_commit_chain ---

    def test_inspect_commit_chain__single_commit(self):
        commit_id, _, _, _, _ = self._setup_vault_with_commit()
        chain = self.inspector.inspect_commit_chain(self.tmp_dir, read_key=self.read_key)
        assert len(chain) == 1
        assert chain[0]['commit_id'] == commit_id
        assert chain[0]['parent'] is None

    def test_inspect_commit_chain__no_read_key(self):
        commit_id, _, _, _, _ = self._setup_vault_with_commit()
        chain = self.inspector.inspect_commit_chain(self.tmp_dir)
        assert len(chain) == 1
        assert 'error' in chain[0]

    def test_inspect_commit_chain__limit(self):
        commit_id, _, _, _, _ = self._setup_vault_with_commit()
        chain = self.inspector.inspect_commit_chain(self.tmp_dir, read_key=self.read_key, limit=1)
        assert len(chain) == 1

    # --- _detect_object_type ---

    def test_detect_object_type__commit(self):
        result = self.inspector._detect_object_type({'tree_id': 'abc', 'version': 1})
        assert result == 'commit'

    def test_detect_object_type__tree(self):
        result = self.inspector._detect_object_type({'entries': []})
        assert result == 'tree'

    def test_detect_object_type__json_blob(self):
        result = self.inspector._detect_object_type({'some_key': 'some_value'})
        assert result == 'blob (json)'

    # --- _find_child_commit ---

    def test_find_child_commit__found(self):
        chain = [{'commit_id': 'child1'}, {'commit_id': 'parent1'}]
        assert self.inspector._find_child_commit(chain, 'parent1') == 'child1'

    def test_find_child_commit__not_found(self):
        chain = [{'commit_id': 'only1'}]
        assert self.inspector._find_child_commit(chain, 'missing') is None

    def test_find_child_commit__head_has_no_child(self):
        chain = [{'commit_id': 'head1'}, {'commit_id': 'parent1'}]
        assert self.inspector._find_child_commit(chain, 'head1') is None

    # --- object_store_stats ---

    def test_object_store_stats__with_objects(self):
        commit_id, _, _, _, _ = self._setup_vault_with_commit()
        stats = self.inspector.object_store_stats(self.tmp_dir)
        assert stats['total_objects'] >= 3
        assert stats['total_bytes'] > 0
        assert len(stats['buckets']) > 0

    # --- cat_object for binary blob ---

    def test_cat_object__binary_blob(self):
        vault_path = self._vault_path()
        os.makedirs(vault_path, exist_ok=True)
        object_store = Vault__Object_Store(vault_path=vault_path, crypto=self.crypto)

        binary_data      = bytes(range(256))
        blob_encrypted   = self.crypto.encrypt(self.read_key, binary_data)
        blob_id          = object_store.store(blob_encrypted)

        ref_manager = Vault__Ref_Manager(vault_path=vault_path)

        result = self.inspector.cat_object(self.tmp_dir, blob_id, self.read_key)
        assert result['exists'] is True
        assert 'binary' in result['type']
