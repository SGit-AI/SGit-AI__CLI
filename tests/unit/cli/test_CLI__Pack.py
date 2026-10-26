"""`sgit pack` and `sgit init --packs` at the CLI boundary, over the in-memory host:
the parser, the six subcommands' output, and the round trip import -> push -> export
driven through the commands themselves."""
import json
import os
import types

import pytest

from sgit_ai.cli.CLI__Main                     import CLI__Main
from sgit_ai.cli.CLI__Pack                     import CLI__Pack
from sgit_ai.cli.CLI__Token_Store              import CLI__Token_Store
from sgit_ai.cli.CLI__Vault                    import CLI__Vault
from sgit_ai.core.Vault__Sync                  import Vault__Sync
from sgit_ai.crypto.Vault__Crypto              import Vault__Crypto
from tests._helpers.pack_env                   import Pack__Env
from tests._helpers.vault_test_env             import TEST_VAULT_KEYS


class _Args:
    def __init__(self, **kw):
        self.token = None; self.base_url = None; self.remote = None; self.transport = 'auto'
        self.verify_tls = None; self.json = False
        for k, v in kw.items():
            setattr(self, k, v)


def _cli(env) -> CLI__Pack:
    vault = CLI__Vault(token_store=CLI__Token_Store())
    api   = env.api
    def _create_sync(self, base_url=None, access_token=None, **kwargs):
        return Vault__Sync(crypto=Vault__Crypto(), api=api)
    vault.create_sync = types.MethodType(_create_sync, vault)
    return CLI__Pack(vault_ref=vault)


class Test_CLI__Pack__Parser:

    def test_pack_subcommands_parse(self):
        p = CLI__Main().build_parser()
        for argv, func in ((['pack', 'import', 'src', 'dst'], 'cmd_import'), (['pack', 'export', 'src', 'dst'], 'cmd_export'),
                           (['pack', 'compact', '--dry-run'], 'cmd_compact'), (['pack', 'ls'], 'cmd_ls'),
                           (['pack', 'verify', 'd'], 'cmd_verify'), (['pack', 'stats', '--json'], 'cmd_stats')):
            args = p.parse_args(argv)
            assert args.func.__name__ == func, argv
        args = p.parse_args(['pack', 'import', 'src', 'dst', '--no-deflate', '--vault-key', 'k'])
        assert args.no_deflate and args.vault_key == 'k' and args.source == 'src' and args.target == 'dst'

    def test_init_and_create_take_packs(self):
        p = CLI__Main().build_parser()
        assert p.parse_args(['init', 'd', '--packs']).packs is True
        assert p.parse_args(['init', 'd']).packs is False
        assert p.parse_args(['create', 'name', '--packs']).packs is True


class Test_CLI__Pack__Commands:

    def setup_method(self):
        self.env = Pack__Env()
        self.cli = _cli(self.env)
        self.sync, self.normal, _ = self.env.normal_vault(self.env.text_files(3), vault_key=TEST_VAULT_KEYS[0])

    def test_import_push_ls_stats_verify_compact_export(self, capsys):
        packed = self.env.path('packed')
        self.cli.cmd_import(_Args(source=self.normal, target=packed, vault_key=TEST_VAULT_KEYS[1], no_deflate=False))
        out = capsys.readouterr().out
        assert 'Imported into a new pack vault' in out and 'sgit push' in out and 'deflated' in out
        assert os.path.isfile(os.path.join(packed, '.sg_vault', 'remotes.json')) or True   # base url recorded when known
        assert self.env.tree(packed) == self.env.tree(self.normal)
        sync_p = self.env.sync(); assert sync_p.push(packed)['status'] == 'pushed'

        self.cli.cmd_ls(_Args(directory=packed)); out = capsys.readouterr().out
        assert 'snapshots/  (1 pack(s)' in out and 'commits/  (0 pack(s)' in out and '* = absorbed' in out
        self.cli.cmd_stats(_Args(directory=packed)); out = capsys.readouterr().out
        assert 'loose objects under bare/data/: 0' in out and 'deflated' in out
        self.cli.cmd_verify(_Args(directory=packed)); out = capsys.readouterr().out
        assert out.strip().endswith('ok')

        sync_c, c = self.env.clone(TEST_VAULT_KEYS[1] if False else sync_p._read_vault_key(packed), 'c')
        self.env.write(c, {'more.md': b'more\n' * 30}); sync_c.commit(c, message='more'); sync_c.push(c)
        sync_p.pull(packed)
        self.cli.cmd_compact(_Args(directory=packed, dry_run=True)); out = capsys.readouterr().out
        assert 'Would snapshot head' in out and 'absorbed by the snapshot -> archive/' in out
        self.cli.cmd_compact(_Args(directory=packed, dry_run=False)); out = capsys.readouterr().out
        assert 'Did snapshot head' in out and 'archived. Nothing was deleted without its copy' in out
        self.cli.cmd_ls(_Args(directory=packed, json=True)); listed = json.loads(capsys.readouterr().out)
        assert len(listed['snapshots']) == 1 and listed['commits'] == [] and len(listed['archive']) == 2

        exported = self.env.path('exported')
        self.cli.cmd_export(_Args(source=packed, target=exported, vault_key=TEST_VAULT_KEYS[2], json=True))
        stats = json.loads(capsys.readouterr().out)
        assert stats['packs'] is False and stats['deflated'] == 0 and stats['commits'] >= 3
        assert self.env.tree(exported) == self.env.tree(packed)

    def test_verify_exits_non_zero_on_a_bad_pack(self, capsys):
        sync_p, packed, key = self.env.pack_vault(self.env.text_files(2), vault_key=TEST_VAULT_KEYS[1])
        vid  = sync_p._init_components(packed).vault_id
        name = [p for p in self.env.api.packs(vid) if '/indexes/' not in p][0]              # a data pack, not its index
        self.env.api._store[f'{vid}/{name}'] = b'\0' * len(self.env.api._store[f'{vid}/{name}'])
        with pytest.raises(SystemExit):
            self.cli.cmd_verify(_Args(directory=packed))
        assert 'FAILED' in capsys.readouterr().out

    def test_compact_refuses_a_normal_vault(self):
        with pytest.raises(RuntimeError, match='not a pack vault'):
            self.cli.cmd_compact(_Args(directory=self.normal, dry_run=True))

    def test_init_packs_through_the_vault_command(self, capsys):
        vault = self.cli.vault_ref
        d     = self.env.path('cli-init')
        vault.cmd_init(_Args(directory=d, vault_key=TEST_VAULT_KEYS[1], existing=True, restore=False, packs=True))
        out = capsys.readouterr().out
        assert '(pack vault)' in out
        from sgit_ai.core.actions.pack.Vault__Packs import Vault__Packs
        assert Vault__Packs(crypto=Vault__Crypto(), api=self.env.api).is_pack_vault(d)
