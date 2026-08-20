import os
import shutil
import tempfile
import pytest

from sgit_ai.cli.CLI__Cache                      import CLI__Cache
from sgit_ai.cli.CLI__Main                       import CLI__Main
from sgit_ai.core.Vault__Sync                    import Vault__Sync
from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory   import Vault__API__In_Memory
from sgit_ai.storage.Vault__Storage              import Vault__Storage
from sgit_ai.storage.Vault__Cache_Manager        import Vault__Cache_Manager
from sgit_ai.safe_types.Enum__Cache_Kind         import Enum__Cache_Kind


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Base:

    def setup_method(self):
        self.tmp   = tempfile.mkdtemp()
        self.vault = os.path.join(self.tmp, 'vault')
        self.cli   = CLI__Cache()
        sync       = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        init       = sync.init(self.vault)
        self.vault_id = init['vault_id']
        keys       = Vault__Crypto().derive_keys_from_vault_key(init['vault_key'])
        self.rk    = keys['read_key_bytes']
        self.mgr   = Vault__Cache_Manager(crypto=Vault__Crypto(), storage=Vault__Storage())

        self._write('pages/home.md', '# Home\n')
        self._write('media/a.txt',   'photo')
        sync.commit(self.vault, 'initial')

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel, text):
        p = os.path.join(self.vault, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as f:
            f.write(text)

    def _args(self, **kw):
        kw.setdefault('directory', self.vault)
        return _Args(**kw)


class Test_CLI__Cache__Add(_Base):

    def test_small_file_defaults_to_value(self, capsys):
        self.cli.cmd_cache_add(self._args(path='pages/home.md', pointer=False, value=False))
        out = capsys.readouterr().out
        assert 'Kind:      value' in out
        cid = self.mgr.cache_id(self.rk, self.vault_id, 'pages/home.md', Enum__Cache_Kind.VALUE)
        assert self.mgr.exists(self.vault, Enum__Cache_Kind.VALUE, cid)

    def test_folder_defaults_to_pointer(self, capsys):
        self.cli.cmd_cache_add(self._args(path='media', pointer=False, value=False))
        out = capsys.readouterr().out
        assert 'Kind:      pointer' in out and 'folder' in out

    def test_explicit_pointer_on_a_file(self, capsys):
        self.cli.cmd_cache_add(self._args(path='pages/home.md', pointer=True, value=False))
        assert 'Kind:      pointer' in capsys.readouterr().out

    def test_value_on_a_folder_is_rejected(self, capsys):
        with pytest.raises(SystemExit):
            self.cli.cmd_cache_add(self._args(path='media', pointer=False, value=True))
        assert 'folder cannot be cached by value' in capsys.readouterr().err

    def test_both_flags_rejected(self, capsys):
        with pytest.raises(SystemExit):
            self.cli.cmd_cache_add(self._args(path='pages/home.md', pointer=True, value=True))
        assert 'not both' in capsys.readouterr().err

    def test_unknown_path_rejected(self, capsys):
        with pytest.raises(SystemExit):
            self.cli.cmd_cache_add(self._args(path='nope/missing.txt', pointer=False, value=False))
        assert 'path not found' in capsys.readouterr().err

    def test_switching_kind_replaces__one_object_per_path(self, capsys):
        # D4: a path is cached as value OR pointer, never both
        self.cli.cmd_cache_add(self._args(path='pages/home.md', pointer=False, value=True))
        capsys.readouterr()
        self.cli.cmd_cache_add(self._args(path='pages/home.md', pointer=True, value=False))
        assert 'replaced existing value cache' in capsys.readouterr().out

        v = self.mgr.cache_id(self.rk, self.vault_id, 'pages/home.md', Enum__Cache_Kind.VALUE)
        p = self.mgr.cache_id(self.rk, self.vault_id, 'pages/home.md', Enum__Cache_Kind.POINTER)
        assert self.mgr.exists(self.vault, Enum__Cache_Kind.VALUE,   v) is False
        assert self.mgr.exists(self.vault, Enum__Cache_Kind.POINTER, p) is True


class Test_CLI__Cache__Rm(_Base):

    def test_removes_declared_cache(self, capsys):
        self.cli.cmd_cache_add(self._args(path='pages/home.md', pointer=False, value=False))
        capsys.readouterr()
        self.cli.cmd_cache_rm(self._args(path='pages/home.md'))
        assert 'Removed value cache' in capsys.readouterr().out
        assert self.mgr.list_all(self.vault) == []

    def test_undeclared_path_records_removal_intent(self, capsys):
        # Not a pure no-op any more: the id may exist on the server (declared by
        # another clone), so rm records tombstones that the next push honours.
        self.cli.cmd_cache_rm(self._args(path='pages/home.md'))
        assert 'removal recorded' in capsys.readouterr().out
        assert len(self.mgr.tombstoned_ids(self.vault)) == 2      # value + pointer ids


class Test_CLI__Cache__Status(_Base):

    def test_empty(self, capsys):
        self.cli.cmd_cache_status(self._args(json=False))
        assert 'No cache objects declared' in capsys.readouterr().out

    def test_lists_declared_and_marks_fresh(self, capsys):
        self.cli.cmd_cache_add(self._args(path='pages/home.md', pointer=False, value=False))
        capsys.readouterr()
        self.cli.cmd_cache_status(self._args(json=False))
        out = capsys.readouterr().out
        assert 'pages/home.md' in out
        assert 'fresh' in out                      # just declared at the current head

    def test_marks_stale_after_a_new_commit(self, capsys):
        self.cli.cmd_cache_add(self._args(path='pages/home.md', pointer=False, value=False))
        capsys.readouterr()
        self._write('pages/home.md', '# Home v2\n')
        Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup()).commit(self.vault, 'edit')
        self.cli.cmd_cache_status(self._args(json=False))
        out = capsys.readouterr().out
        assert 'stale' in out and 'sgit push' in out

    def test_json_output(self, capsys):
        import json as _json
        self.cli.cmd_cache_add(self._args(path='media', pointer=False, value=False))
        capsys.readouterr()
        self.cli.cmd_cache_status(self._args(json=True))
        data = _json.loads(capsys.readouterr().out)
        assert data['entries'][0]['path'] == 'media'
        assert data['entries'][0]['kind'] == 'pointer'


class Test_CLI__Cache__Parser:

    def test_cache_namespace_registered(self):
        p  = CLI__Main().build_parser()
        ch = p._subparsers._group_actions[0].choices
        assert 'cache' in ch
        assert set(ch['cache']._subparsers._group_actions[0].choices) == {'add', 'rm', 'status', 'repair'}

    def test_repair_routes_to_handler(self):
        p    = CLI__Main().build_parser()
        args = p.parse_args(['cache', 'repair', '--dry-run'])
        assert args.func.__func__ is CLI__Cache.cmd_cache_repair
        assert args.dry_run is True

    def test_add_routes_to_handler(self):
        cli  = CLI__Main()
        p    = cli.build_parser()
        args = p.parse_args(['cache', 'add', 'pages/home.md'])
        assert args.func.__self__.__class__ is CLI__Cache
        assert args.func.__func__ is CLI__Cache.cmd_cache_add


class Test_CLI__Cache__Review_Regressions(_Base):
    """Regressions from the post-implementation review (2026-08-13)."""

    def test_unicode_path_survives_declare_and_push(self, capsys):
        # Safe_Str__File_Path SANITISED unicode ('café'->'caf_'), so the stored
        # path never matched the flatten() key and the next push deleted the
        # cache as an orphan. Schema__Cache_* now use Safe_Str__Cache_Path,
        # which validates instead of rewriting.
        self._write('docs/café-notes.md', '# Notes\n')
        sync = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        sync.commit(self.vault, 'add unicode file')
        self.cli.cmd_cache_add(self._args(path='docs/café-notes.md', pointer=False, value=True))
        capsys.readouterr()

        cid = self.mgr.cache_id(self.rk, self.vault_id, 'docs/café-notes.md', Enum__Cache_Kind.VALUE)
        obj = self.mgr.load(self.vault, Enum__Cache_Kind.VALUE, cid, self.rk)
        assert str(obj.path) == 'docs/café-notes.md'          # byte-identical, not sanitised

    def test_trailing_slash_and_dot_prefix_normalised(self, capsys):
        # 'media/' and './media' must derive the same id as 'media'
        self.cli.cmd_cache_add(self._args(path='./media/', pointer=True, value=False))
        capsys.readouterr()
        cid = self.mgr.cache_id(self.rk, self.vault_id, 'media', Enum__Cache_Kind.POINTER)
        assert self.mgr.exists(self.vault, Enum__Cache_Kind.POINTER, cid)

    def test_value_cap_refuses_oversized_file(self, capsys):
        self._write('big.bin', 'x' * (1024 * 1024 + 1))
        sync = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        sync.commit(self.vault, 'add big file')
        with pytest.raises(SystemExit):
            self.cli.cmd_cache_add(self._args(path='big.bin', pointer=False, value=True))
        assert 'too large to cache by value' in capsys.readouterr().err

    def test_oversized_file_defaults_to_pointer_without_flags(self, capsys):
        self._write('big.bin', 'x' * (1024 * 1024 + 1))
        sync = Vault__Sync(crypto=Vault__Crypto(), api=Vault__API__In_Memory().setup())
        sync.commit(self.vault, 'add big file')
        self.cli.cmd_cache_add(self._args(path='big.bin', pointer=False, value=False))
        assert 'Kind:      pointer' in capsys.readouterr().out
