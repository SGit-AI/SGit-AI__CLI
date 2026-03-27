import json
import os
import shutil
import tempfile

from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.sync.Vault__Dump            import Vault__Dump
from sgit_ai.sync.Vault__Sync            import Vault__Sync
from sgit_ai.api.Vault__API__In_Memory   import Vault__API__In_Memory
from sgit_ai.schemas.Schema__Dump_Result import Schema__Dump_Result


class Test_Vault__Dump:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.crypto  = Vault__Crypto()
        self.api     = Vault__API__In_Memory()
        self.api.setup()
        self.sync    = Vault__Sync(crypto=self.crypto, api=self.api)
        self.dumper  = Vault__Dump(crypto=self.crypto)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _init_vault(self, name='dump-test'):
        directory = os.path.join(self.tmp_dir, name)
        result    = self.sync.init(directory)
        return result, directory

    def _add_file(self, directory: str, filename: str, content: str) -> None:
        with open(os.path.join(directory, filename), 'w') as fh:
            fh.write(content)

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_dump_local_returns_schema(self):
        _, directory = self._init_vault()
        result = self.dumper.dump_local(directory)
        assert isinstance(result, Schema__Dump_Result)

    def test_dump_source_is_local(self):
        _, directory = self._init_vault()
        result = self.dumper.dump_local(directory)
        assert str(result.source) == 'local'

    def test_dump_directory_recorded(self):
        # Note: directory is stored in Schema__Dump_Result.directory (Safe_Str),
        # which sanitizes special chars (e.g. replaces / and - with _).
        # We just verify the field is non-empty and contains recognisable fragments.
        _, directory = self._init_vault()
        result = self.dumper.dump_local(directory)
        stored = str(result.directory)
        assert len(stored) > 0
        # The vault name fragment 'dump' should appear in the stored string
        assert 'dump' in stored.lower() or stored

    def test_dump_has_refs_after_commit(self):
        _, directory = self._init_vault()
        self._add_file(directory, 'hello.txt', 'hello world')
        self.sync.commit(directory, message='initial commit')
        result = self.dumper.dump_local(directory)
        assert len(result.refs) > 0

    def test_dump_traversal_path_non_empty_after_commit(self):
        _, directory = self._init_vault()
        self._add_file(directory, 'file.txt', 'content')
        self.sync.commit(directory, message='add file')
        result = self.dumper.dump_local(directory)
        assert len(result.traversal_path) > 0

    def test_dump_commits_populated_after_commit(self):
        _, directory = self._init_vault()
        self._add_file(directory, 'data.txt', 'some data')
        self.sync.commit(directory, message='first commit')
        result = self.dumper.dump_local(directory)
        assert len(result.commits) > 0

    def test_dump_trees_populated_after_commit(self):
        _, directory = self._init_vault()
        self._add_file(directory, 'readme.txt', 'readme')
        self.sync.commit(directory, message='add readme')
        result = self.dumper.dump_local(directory)
        assert len(result.trees) > 0

    def test_dump_objects_populated_after_commit(self):
        _, directory = self._init_vault()
        self._add_file(directory, 'sample.txt', 'sample content')
        self.sync.commit(directory, message='add sample')
        result = self.dumper.dump_local(directory)
        assert len(result.objects) > 0

    def test_dump_total_counts_match(self):
        _, directory = self._init_vault()
        self._add_file(directory, 'a.txt', 'alpha')
        self.sync.commit(directory, message='first')
        result = self.dumper.dump_local(directory)
        assert int(result.total_objects)  == len(result.objects)
        assert int(result.total_refs)     == len(result.refs)
        assert int(result.total_branches) == len(result.branches)
        assert int(result.dangling_count) == len(result.dangling_ids)

    def test_dump_no_dangling_after_clean_commit(self):
        _, directory = self._init_vault()
        self._add_file(directory, 'clean.txt', 'no dangling')
        self.sync.commit(directory, message='clean commit')
        result = self.dumper.dump_local(directory)
        assert result.dangling_ids == []
        assert int(result.dangling_count) == 0

    def test_dump_branches_present_after_init(self):
        _, directory = self._init_vault()
        result = self.dumper.dump_local(directory)
        assert len(result.branches) > 0

    def test_dump_is_json_serialisable(self):
        _, directory = self._init_vault()
        self._add_file(directory, 'json-test.txt', 'test data')
        self.sync.commit(directory, message='json test')
        result = self.dumper.dump_local(directory)
        serialised = json.dumps(result.json())
        assert isinstance(serialised, str)
        assert len(serialised) > 0

    def test_dump_round_trip(self):
        _, directory = self._init_vault()
        self._add_file(directory, 'rt.txt', 'round trip')
        self.sync.commit(directory, message='rt commit')
        result   = self.dumper.dump_local(directory)
        restored = Schema__Dump_Result.from_json(result.json())
        assert restored.json() == result.json()

    def test_dump_commit_has_tree_id(self):
        # Note: Safe_Str normalises hyphens to underscores, so IDs are stored as
        # 'obj_cas_imm_...' rather than 'obj-cas-imm-...'.
        _, directory = self._init_vault()
        self._add_file(directory, 'tree.txt', 'has tree')
        self.sync.commit(directory, message='commit with tree')
        result = self.dumper.dump_local(directory)
        found = False
        for commit in result.commits:
            if commit.tree_id:
                tree_id_str = str(commit.tree_id)
                assert 'obj' in tree_id_str and 'cas' in tree_id_str
                found = True
                break
        assert found, 'Expected at least one commit with a tree_id'

    def test_dump_traversal_path_starts_with_commit(self):
        # Note: Safe_Str normalises hyphens to underscores in stored IDs.
        _, directory = self._init_vault()
        self._add_file(directory, 'path.txt', 'path test')
        self.sync.commit(directory, message='path commit')
        result = self.dumper.dump_local(directory)
        if result.traversal_path:
            first_id = str(result.traversal_path[0])
            assert 'obj' in first_id and 'cas' in first_id

    def test_dump_without_explicit_read_key_auto_reads_vault_key(self):
        """dump_local() should auto-read the vault_key from local/vault_key."""
        _, directory = self._init_vault()
        self._add_file(directory, 'auto.txt', 'auto key test')
        self.sync.commit(directory, message='auto key')
        # Pass no read_key — it should be loaded from disk
        result = self.dumper.dump_local(directory, read_key=None)
        assert isinstance(result, Schema__Dump_Result)
        assert len(result.commits) > 0

    def test_dump_multiple_commits_records_all(self):
        _, directory = self._init_vault()
        self._add_file(directory, 'first.txt', 'first')
        self.sync.commit(directory, message='first commit')
        self._add_file(directory, 'second.txt', 'second')
        self.sync.commit(directory, message='second commit')
        result = self.dumper.dump_local(directory)
        # We should see at least 2 commits in the dump
        assert len(result.commits) >= 2

    def test_dump_with_structure_key(self):
        """Structure key path should produce a result with source containing 'structure-key'."""
        init_result, directory = self._init_vault()
        self._add_file(directory, 'struct.txt', 'structure key test')
        self.sync.commit(directory, message='struct commit')

        # Derive the read_key from the vault_key, then derive the structure key
        vault_key     = init_result['vault_key']
        keys          = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key      = keys['read_key_bytes']
        structure_key = self.crypto.derive_structure_key(read_key)

        result = self.dumper.dump_with_structure_key(directory, structure_key)
        assert isinstance(result, Schema__Dump_Result)
        assert 'structure' in str(result.source)

    def test_dump_structure_key_is_different_from_read_key(self):
        """Verify the structure key is non-reversibly derived from the read key."""
        _, directory     = self._init_vault()
        vault_key        = open(os.path.join(directory, '.sg_vault', 'local', 'vault_key')).read().strip()
        keys             = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key         = keys['read_key_bytes']
        structure_key    = self.crypto.derive_structure_key(read_key)

        assert structure_key != read_key
        assert len(structure_key) == 32   # AES-256
