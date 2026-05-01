# Additional coverage tests for Vault__Diff — real on-disk vault, no mocks.
import hashlib
import os
import shutil
import tempfile

import pytest

from sgit_ai.crypto.Vault__Crypto        import Vault__Crypto
from sgit_ai.schemas.Schema__Diff_File   import Schema__Diff_File
from sgit_ai.schemas.Schema__Diff_Result import Schema__Diff_Result
from sgit_ai.sync.Vault__Diff            import Vault__Diff, BINARY_CHECK_BYTES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_diff() -> Vault__Diff:
    return Vault__Diff(crypto=Vault__Crypto())


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_vault(passphrase: str, vault_name: str) -> tuple:
    """Return (tmp_dir, sync) with an initialised vault."""
    from sgit_ai.sync.Vault__Sync import Vault__Sync
    tmp  = tempfile.mkdtemp()
    sync = Vault__Sync(crypto=Vault__Crypto())
    sync.init(tmp, vault_key=f'{passphrase}:{vault_name}')
    return tmp, sync


# ---------------------------------------------------------------------------
# _unified_diff edge cases
# ---------------------------------------------------------------------------

class Test_Vault__Diff__Unified_Diff:

    def test_unified_diff_produces_headers(self):
        d      = _make_diff()
        before = b'line1\nline2\n'
        after  = b'line1\nline3\n'
        result = d._unified_diff('test.txt', before, after)
        assert '--- a/test.txt' in result
        assert '+++ b/test.txt' in result

    def test_unified_diff_shows_added_line(self):
        d      = _make_diff()
        before = b'a\n'
        after  = b'a\nb\n'
        result = d._unified_diff('f.txt', before, after)
        assert '+b' in result

    def test_unified_diff_shows_removed_line(self):
        d      = _make_diff()
        before = b'a\nb\n'
        after  = b'a\n'
        result = d._unified_diff('f.txt', before, after)
        assert '-b' in result

    def test_unified_diff_handles_invalid_utf8(self):
        d      = _make_diff()
        before = b'\xff\xfe line one\n'
        after  = b'\xff\xfe line two\n'
        # Should not raise
        result = d._unified_diff('f.txt', before, after)
        assert isinstance(result, str)

    def test_unified_diff_empty_before(self):
        d      = _make_diff()
        result = d._unified_diff('f.txt', b'', b'new\n')
        assert isinstance(result, str)

    def test_unified_diff_empty_after(self):
        d      = _make_diff()
        result = d._unified_diff('f.txt', b'old\n', b'')
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _build_result edge cases
# ---------------------------------------------------------------------------

class Test_Vault__Diff__Build_Result__Extra:

    def test_build_result_empty_files(self):
        d      = _make_diff()
        result = d._build_result('/tmp', 'head', '', [])
        assert int(result.added_count)    == 0
        assert int(result.modified_count) == 0
        assert int(result.deleted_count)  == 0

    def test_build_result_directory_preserved(self):
        d      = _make_diff()
        result = d._build_result('/my/vault', 'head', '', [])
        assert result.directory == '/my/vault'

    def test_build_result_commit_id_empty_string_becomes_none(self):
        d      = _make_diff()
        result = d._build_result('/tmp', 'commit', '', [])
        assert result.commit_id is None

    def test_build_result_commit_id_preserved(self):
        d      = _make_diff()
        result = d._build_result('/tmp', 'commit', 'abc123', [])
        assert str(result.commit_id) == 'abc123'

    def test_build_result_only_unchanged_not_counted(self):
        d     = _make_diff()
        files = [Schema__Diff_File(path='x.txt', status='unchanged')]
        result = d._build_result('/tmp', 'head', '', files)
        assert int(result.added_count)    == 0
        assert int(result.modified_count) == 0
        assert int(result.deleted_count)  == 0


# ---------------------------------------------------------------------------
# diff_files — extended
# ---------------------------------------------------------------------------

class Test_Vault__Diff__Diff_Files__Extended:

    def test_diff_files_large_equal_sets(self):
        data  = {f'file{i:04d}.txt': b'same-content' for i in range(100)}
        d     = _make_diff()
        result = d.diff_files(data, data)
        assert all(r.status == 'unchanged' for r in result)
        assert len(result) == 100

    def test_diff_files_one_changed_in_large_set(self):
        base_data = {f'file{i}.txt': b'content' for i in range(10)}
        working   = dict(base_data)
        working['file5.txt'] = b'changed'
        d      = _make_diff()
        result = d.diff_files(working, base_data)
        by_path = {str(r.path): r for r in result}
        assert by_path['file5.txt'].status == 'modified'
        for i in range(10):
            if i != 5:
                assert by_path[f'file{i}.txt'].status == 'unchanged'

    def test_diff_files_subset_deleted(self):
        before = {'a.txt': b'a', 'b.txt': b'b', 'c.txt': b'c'}
        after  = {'a.txt': b'a'}
        d      = _make_diff()
        result = d.diff_files(after, before)
        by_path = {str(r.path): r for r in result}
        assert by_path['a.txt'].status == 'unchanged'
        assert by_path['b.txt'].status == 'deleted'
        assert by_path['c.txt'].status == 'deleted'


# ---------------------------------------------------------------------------
# diff_vs_commit() — requires real vault
# ---------------------------------------------------------------------------

class Test_Vault__Diff__Vs_Commit:

    def test_diff_vs_specific_commit(self):
        tmp, sync = _make_vault('vscommitpass12345678', 'vscommit')
        try:
            # commit A: just hello.txt
            with open(os.path.join(tmp, 'hello.txt'), 'w') as f:
                f.write('version 1\n')
            sync.commit(tmp, message='first commit')

            # Capture the commit ID from HEAD
            from sgit_ai.sync.Vault__Storage        import Vault__Storage, SG_VAULT_DIR
            from sgit_ai.sync.Vault__Branch_Manager import Vault__Branch_Manager
            from sgit_ai.schemas.Schema__Local_Config import Schema__Local_Config
            from sgit_ai.crypto.PKI__Crypto          import PKI__Crypto
            from sgit_ai.objects.Vault__Object_Store import Vault__Object_Store
            from sgit_ai.objects.Vault__Ref_Manager  import Vault__Ref_Manager
            from sgit_ai.crypto.Vault__Key_Manager   import Vault__Key_Manager
            import json as _json

            sg_dir     = os.path.join(tmp, SG_VAULT_DIR)
            crypto     = Vault__Crypto()
            storage    = Vault__Storage()
            pki        = PKI__Crypto()
            obj_store  = Vault__Object_Store(vault_path=sg_dir, crypto=crypto)
            ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
            key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=crypto, pki=pki)
            branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=crypto,
                                                    key_manager=key_manager,
                                                    ref_manager=ref_manager,
                                                    storage=storage)

            vault_key_path = os.path.join(tmp, SG_VAULT_DIR, 'local', 'vault_key')
            with open(vault_key_path) as f:
                vault_key = f.read().strip()
            keys = crypto.derive_keys_from_vault_key(vault_key)
            read_key = keys['read_key_bytes']

            config_path = storage.local_config_path(tmp)
            with open(config_path) as f:
                config_data = _json.load(f)
            local_config = Schema__Local_Config.from_json(config_data)
            branch_id    = str(local_config.my_branch_id)

            index_id     = keys['branch_index_file_id']
            branch_index = branch_manager.load_branch_index(tmp, index_id, read_key)
            branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
            commit_id_a  = ref_manager.read_ref(str(branch_meta.head_ref_id), read_key)

            # commit B: modify hello.txt + add world.txt
            with open(os.path.join(tmp, 'hello.txt'), 'w') as f:
                f.write('version 2\n')
            with open(os.path.join(tmp, 'world.txt'), 'w') as f:
                f.write('new file\n')
            sync.commit(tmp, message='second commit')

            # diff working (current state = same as B) vs commit A
            diff_engine = Vault__Diff(crypto=Vault__Crypto())
            result      = diff_engine.diff_vs_commit(tmp, commit_id_a)
            by_path     = {str(f.path): f for f in result.files}

            assert by_path['hello.txt'].status == 'modified'
            assert by_path['world.txt'].status == 'added'
            assert str(result.mode) == 'commit'
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# diff_commits() — compare two specific commits
# ---------------------------------------------------------------------------

class Test_Vault__Diff__Commits:

    def test_diff_commits_shows_changes_between_two_commits(self):
        tmp, sync = _make_vault('diffcommitspass12345', 'diffcmts')
        try:
            # Commit A
            with open(os.path.join(tmp, 'a.txt'), 'w') as f:
                f.write('version a\n')
            sync.commit(tmp, message='commit A')

            # Capture commit A id
            from sgit_ai.sync.Vault__Storage          import Vault__Storage, SG_VAULT_DIR
            from sgit_ai.sync.Vault__Branch_Manager   import Vault__Branch_Manager
            from sgit_ai.schemas.Schema__Local_Config import Schema__Local_Config
            from sgit_ai.crypto.PKI__Crypto            import PKI__Crypto
            from sgit_ai.objects.Vault__Object_Store  import Vault__Object_Store
            from sgit_ai.objects.Vault__Ref_Manager   import Vault__Ref_Manager
            from sgit_ai.crypto.Vault__Key_Manager    import Vault__Key_Manager
            import json as _json

            sg_dir      = os.path.join(tmp, SG_VAULT_DIR)
            crypto      = Vault__Crypto()
            storage     = Vault__Storage()
            pki         = PKI__Crypto()
            obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=crypto)
            ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
            key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=crypto, pki=pki)
            branch_manager = Vault__Branch_Manager(vault_path=sg_dir, crypto=crypto,
                                                    key_manager=key_manager,
                                                    ref_manager=ref_manager,
                                                    storage=storage)

            vault_key_path = os.path.join(tmp, SG_VAULT_DIR, 'local', 'vault_key')
            with open(vault_key_path) as f:
                vault_key = f.read().strip()
            keys     = crypto.derive_keys_from_vault_key(vault_key)
            read_key = keys['read_key_bytes']

            config_path  = storage.local_config_path(tmp)
            with open(config_path) as f:
                config_data = _json.load(f)
            local_config = Schema__Local_Config.from_json(config_data)
            branch_id    = str(local_config.my_branch_id)

            index_id      = keys['branch_index_file_id']
            branch_index  = branch_manager.load_branch_index(tmp, index_id, read_key)
            branch_meta   = branch_manager.get_branch_by_id(branch_index, branch_id)
            commit_id_a   = ref_manager.read_ref(str(branch_meta.head_ref_id), read_key)

            # Commit B: add b.txt, delete (overwrite) a.txt
            with open(os.path.join(tmp, 'a.txt'), 'w') as f:
                f.write('version b\n')
            with open(os.path.join(tmp, 'b.txt'), 'w') as f:
                f.write('new in B\n')
            sync.commit(tmp, message='commit B')

            branch_index  = branch_manager.load_branch_index(tmp, index_id, read_key)
            branch_meta   = branch_manager.get_branch_by_id(branch_index, branch_id)
            commit_id_b   = ref_manager.read_ref(str(branch_meta.head_ref_id), read_key)

            diff_engine = Vault__Diff(crypto=Vault__Crypto())
            result      = diff_engine.diff_commits(tmp, commit_id_a, commit_id_b)

            by_path = {str(f.path): f for f in result.files}
            # a.txt changed between commits
            assert by_path['a.txt'].status == 'modified'
            # result has files from both commits covered
            # commit_id_b stored (Safe_Str may normalise separators)
            # diff_commits(a, b) returns a diff result with changes recorded
            assert len(result.files) >= 1
            # commit_id_b is stored (may normalise separators via Safe_Str)
            assert commit_id_b.replace('-', '_') in str(result.commit_id_b) or \
                   commit_id_b in str(result.commit_id_b)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# show_commit()
# ---------------------------------------------------------------------------

class Test_Vault__Diff__Show_Commit:

    def test_show_commit_returns_commit_info_and_diff(self):
        tmp, sync = _make_vault('showcommitpass123456', 'showcmts')
        try:
            with open(os.path.join(tmp, 'readme.txt'), 'w') as f:
                f.write('first\n')
            sync.commit(tmp, message='initial commit')

            from sgit_ai.sync.Vault__Storage          import Vault__Storage, SG_VAULT_DIR
            from sgit_ai.sync.Vault__Branch_Manager   import Vault__Branch_Manager
            from sgit_ai.schemas.Schema__Local_Config import Schema__Local_Config
            from sgit_ai.crypto.PKI__Crypto            import PKI__Crypto
            from sgit_ai.objects.Vault__Object_Store  import Vault__Object_Store
            from sgit_ai.objects.Vault__Ref_Manager   import Vault__Ref_Manager
            from sgit_ai.crypto.Vault__Key_Manager    import Vault__Key_Manager
            import json as _json

            sg_dir      = os.path.join(tmp, SG_VAULT_DIR)
            crypto      = Vault__Crypto()
            storage     = Vault__Storage()
            pki         = PKI__Crypto()
            ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
            key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=crypto, pki=pki)
            branch_manager = Vault__Branch_Manager(
                vault_path=sg_dir, crypto=crypto,
                key_manager=key_manager, ref_manager=ref_manager, storage=storage)

            vault_key_path = os.path.join(tmp, SG_VAULT_DIR, 'local', 'vault_key')
            with open(vault_key_path) as f:
                vault_key = f.read().strip()
            keys     = crypto.derive_keys_from_vault_key(vault_key)
            read_key = keys['read_key_bytes']

            config_path = storage.local_config_path(tmp)
            with open(config_path) as f:
                config_data = _json.load(f)
            local_config = Schema__Local_Config.from_json(config_data)
            branch_id    = str(local_config.my_branch_id)

            index_id     = keys['branch_index_file_id']
            branch_index = branch_manager.load_branch_index(tmp, index_id, read_key)
            branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
            commit_id    = ref_manager.read_ref(str(branch_meta.head_ref_id), read_key)

            diff_engine        = Vault__Diff(crypto=Vault__Crypto())
            commit_info, result = diff_engine.show_commit(tmp, commit_id)

            assert commit_info['commit_id'] == commit_id
            assert 'timestamp' in commit_info
            assert isinstance(commit_info['timestamp_ms'], int)
            assert isinstance(result, Schema__Diff_Result)
            # First commit — readme.txt should appear in the diff
            by_path = {str(f.path): f for f in result.files}
            assert 'readme.txt' in by_path
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_show_commit_with_parent(self):
        """Second commit should show parent_id and the diff vs parent."""
        tmp, sync = _make_vault('showcommitparentpass1', 'showcprt')
        try:
            # First commit
            with open(os.path.join(tmp, 'f.txt'), 'w') as f:
                f.write('v1\n')
            sync.commit(tmp, message='first')

            # Second commit
            with open(os.path.join(tmp, 'f.txt'), 'w') as f:
                f.write('v2\n')
            sync.commit(tmp, message='second')

            from sgit_ai.sync.Vault__Storage          import Vault__Storage, SG_VAULT_DIR
            from sgit_ai.sync.Vault__Branch_Manager   import Vault__Branch_Manager
            from sgit_ai.schemas.Schema__Local_Config import Schema__Local_Config
            from sgit_ai.crypto.PKI__Crypto            import PKI__Crypto
            from sgit_ai.objects.Vault__Ref_Manager   import Vault__Ref_Manager
            from sgit_ai.crypto.Vault__Key_Manager    import Vault__Key_Manager
            import json as _json

            sg_dir      = os.path.join(tmp, SG_VAULT_DIR)
            crypto      = Vault__Crypto()
            storage     = Vault__Storage()
            pki         = PKI__Crypto()
            ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=crypto)
            key_manager = Vault__Key_Manager(vault_path=sg_dir, crypto=crypto, pki=pki)
            branch_manager = Vault__Branch_Manager(
                vault_path=sg_dir, crypto=crypto,
                key_manager=key_manager, ref_manager=ref_manager, storage=storage)

            vault_key_path = os.path.join(tmp, SG_VAULT_DIR, 'local', 'vault_key')
            with open(vault_key_path) as f:
                vault_key = f.read().strip()
            keys     = crypto.derive_keys_from_vault_key(vault_key)
            read_key = keys['read_key_bytes']

            config_path = storage.local_config_path(tmp)
            with open(config_path) as f:
                config_data = _json.load(f)
            local_config = Schema__Local_Config.from_json(config_data)
            branch_id    = str(local_config.my_branch_id)

            index_id     = keys['branch_index_file_id']
            branch_index = branch_manager.load_branch_index(tmp, index_id, read_key)
            branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
            commit_id    = ref_manager.read_ref(str(branch_meta.head_ref_id), read_key)

            diff_engine        = Vault__Diff(crypto=Vault__Crypto())
            commit_info, result = diff_engine.show_commit(tmp, commit_id)

            assert commit_info['parent_id'] is not None
            by_path = {str(f.path): f for f in result.files}
            assert by_path['f.txt'].status == 'modified'
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# log_file()
# ---------------------------------------------------------------------------

class Test_Vault__Diff__Log_File:

    def test_log_file_tracks_added_file(self):
        tmp, sync = _make_vault('logfilepass123456789', 'logfile1')
        try:
            with open(os.path.join(tmp, 'track.txt'), 'w') as f:
                f.write('initial\n')
            sync.commit(tmp, message='add track.txt')

            diff_engine = Vault__Diff(crypto=Vault__Crypto())
            entries     = diff_engine.log_file(tmp, 'track.txt')

            assert len(entries) >= 1
            assert entries[0]['status'] in ('added', 'modified')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_log_file_tracks_modified_file(self):
        tmp, sync = _make_vault('logfilemodpass12345', 'logfile2')
        try:
            with open(os.path.join(tmp, 'mod.txt'), 'w') as f:
                f.write('v1\n')
            sync.commit(tmp, message='add mod.txt')

            with open(os.path.join(tmp, 'mod.txt'), 'w') as f:
                f.write('v2\n')
            sync.commit(tmp, message='modify mod.txt')

            diff_engine = Vault__Diff(crypto=Vault__Crypto())
            entries     = diff_engine.log_file(tmp, 'mod.txt')

            assert len(entries) >= 2
            statuses = [e['status'] for e in entries]
            assert 'modified' in statuses
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_log_file_empty_for_untracked_file(self):
        tmp, sync = _make_vault('logfileuntrackedpass1', 'logfile3')
        try:
            with open(os.path.join(tmp, 'other.txt'), 'w') as f:
                f.write('other\n')
            sync.commit(tmp, message='add other')

            diff_engine = Vault__Diff(crypto=Vault__Crypto())
            entries     = diff_engine.log_file(tmp, 'nonexistent.txt')
            assert entries == []
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_log_file_limit(self):
        tmp, sync = _make_vault('logfilelimitpass12345', 'logfile4')
        try:
            for i in range(5):
                with open(os.path.join(tmp, 'limited.txt'), 'w') as f:
                    f.write(f'version {i}\n')
                sync.commit(tmp, message=f'commit {i}')

            diff_engine = Vault__Diff(crypto=Vault__Crypto())
            entries     = diff_engine.log_file(tmp, 'limited.txt', limit=2)
            assert len(entries) <= 2
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_log_file_entries_have_required_keys(self):
        tmp, sync = _make_vault('logfilekeyspass123456', 'logfile5')
        try:
            with open(os.path.join(tmp, 'file.txt'), 'w') as f:
                f.write('content\n')
            sync.commit(tmp, message='initial commit')

            diff_engine = Vault__Diff(crypto=Vault__Crypto())
            entries     = diff_engine.log_file(tmp, 'file.txt')

            if entries:
                entry = entries[0]
                assert 'commit_id'    in entry
                assert 'timestamp_ms' in entry
                assert 'timestamp'    in entry
                assert 'message'      in entry
                assert 'status'       in entry
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
