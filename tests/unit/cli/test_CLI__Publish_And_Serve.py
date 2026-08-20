"""P2/P3/P4 CLI surfaces: sgit publish + sgit vault serve, end to end."""
import argparse
import os
import shutil
import tempfile
import urllib.request

import pytest

from sgit_ai.cli.CLI__Publish                       import CLI__Publish
from sgit_ai.cli.CLI__Serve                         import CLI__Serve
from sgit_ai.crypto.Vault__Crypto                   import Vault__Crypto
from sgit_ai.core.Vault__Sync                       import Vault__Sync
from sgit_ai.network.api.Vault__API__In_Memory      import Vault__API__In_Memory


def _args(**kwargs):
    return argparse.Namespace(**kwargs)


class Test_CLI__Publish:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.api    = Vault__API__In_Memory()
        self.api.setup()
        self.sync   = Vault__Sync(crypto=self.crypto, api=self.api)
        self.tmp    = tempfile.mkdtemp()
        self.vault  = os.path.join(self.tmp, 'vault')
        result      = self.sync.init(self.vault)
        self.vault_id = result['vault_id']
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('hi')
        self.sync.commit(self.vault, 'initial')
        self.sync.push(self.vault)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_baseline_publish_output(self, capsys):
        CLI__Publish().cmd_publish(_args(directory=self.vault))
        out = capsys.readouterr().out
        assert f'Publishing vault {self.vault_id} → .sg_vault/publish/' in out
        assert 'NOT copied' in out
        assert 'unlisted, NOT access-controlled' in out               # SP-7/SP-12
        assert 'count/sizes/cadence (needed for custody)' in out
        assert 'sgit vault serve' in out
        assert f'sgit clone <read-key>:{self.vault_id}' in out

    def test_public_requires_confirmation_and_prints_history_note(self, capsys):
        cli = CLI__Publish(prompt_answers=['y'])
        cli.cmd_publish(_args(directory=self.vault, visibility='public'))
        out = capsys.readouterr().out
        assert 'This publishes the READ KEY alongside the vault' in out
        assert 'cannot be undone' in out
        assert 'stay in its history' in out                           # git-history note
        assert os.path.isfile(os.path.join(self.vault, '.sg_vault', 'publish', 'manifest.json'))

    def test_public_refused_without_confirmation(self, capsys):
        cli = CLI__Publish(prompt_answers=['n'])
        with pytest.raises(SystemExit):
            cli.cmd_publish(_args(directory=self.vault, visibility='public'))
        assert 'Nothing written' in capsys.readouterr().out
        assert not os.path.isdir(os.path.join(self.vault, '.sg_vault', 'publish'))

    def test_yes_skips_the_public_prompt(self):
        CLI__Publish().cmd_publish(_args(directory=self.vault, visibility='public', yes=True))
        surface = os.listdir(os.path.join(self.vault, '.sg_vault', 'publish'))
        assert any(name.startswith('sgit_public_read_') for name in surface)

    def test_downgrade_blocked_without_yes(self, capsys):
        CLI__Publish().cmd_publish(_args(directory=self.vault, visibility='public', yes=True))
        # a fresh clone resolves bare — simulate by clearing the stored choice
        config_path = os.path.join(self.vault, '.sg_vault', 'local', 'config.json')
        import json as _json
        with open(config_path) as f:
            config = _json.load(f)
        config['publish_visibility'] = None
        with open(config_path, 'w') as f:
            _json.dump(config, f)
        with pytest.raises(SystemExit):
            CLI__Publish().cmd_publish(_args(directory=self.vault))
        err = capsys.readouterr().err
        assert 'last published as PUBLIC' in err
        assert 'REMOVED and readers locked out' in err


class Test_CLI__Serve:

    def setup_method(self):
        self.crypto = Vault__Crypto()
        self.api    = Vault__API__In_Memory()
        self.api.setup()
        self.sync   = Vault__Sync(crypto=self.crypto, api=self.api)
        self.tmp    = tempfile.mkdtemp()
        self.vault  = os.path.join(self.tmp, 'vault')
        result      = self.sync.init(self.vault)
        self.vault_id = result['vault_id']
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('hi')
        self.sync.commit(self.vault, 'initial')
        self.sync.push(self.vault)
        self.cwd = os.getcwd()

    def teardown_method(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_serve_publishes_first_then_serves_store_virtually(self, capsys):
        os.chdir(self.vault)
        server = CLI__Serve(block=False).cmd_serve(_args(directory=None, port=0,
                                                         bind='127.0.0.1', open=False))
        try:
            out = capsys.readouterr().out
            assert 'No published folder yet' in out
            assert 'Why this command exists' in out                   # the opaque-origin rule
            assert 'Read-only. Bound to 127.0.0.1' in out
            url = server.url()
            with urllib.request.urlopen(url, timeout=10) as response:
                assert b'Encrypted vault' in response.read()          # the loader
            # I1: the virtual bare route returns store bytes verbatim
            refs_dir = os.path.join(self.vault, '.sg_vault', 'bare', 'refs')
            ref_name = sorted(os.listdir(refs_dir))[0]
            with urllib.request.urlopen(f'{url}api/vault/read/{self.vault_id}/bare/refs/{ref_name}',
                                        timeout=10) as response:
                served = response.read()
            with open(os.path.join(refs_dir, ref_name), 'rb') as f:
                assert served == f.read()
        finally:
            server.stop()

    def test_serve_republishes_when_stale(self, capsys):
        os.chdir(self.vault)
        first = CLI__Serve(block=False).cmd_serve(_args(directory=None, port=0,
                                                        bind='127.0.0.1', open=False))
        first.stop()
        with open(os.path.join(self.vault, 'hello.txt'), 'w') as f:
            f.write('changed')
        self.sync.commit(self.vault, 'change')                        # store moves on
        capsys.readouterr()
        second = CLI__Serve(block=False).cmd_serve(_args(directory=None, port=0,
                                                         bind='127.0.0.1', open=False))
        second.stop()
        assert 'stale' in capsys.readouterr().out

    def test_serve_explicit_directory(self, capsys):
        from sgit_ai.core.actions.publish.Vault__Publish import Vault__Publish
        Vault__Publish(crypto=self.crypto, api=self.api).publish(self.vault)
        publish_dir = os.path.join(self.vault, '.sg_vault', 'publish')
        server = CLI__Serve(block=False).cmd_serve(_args(directory=publish_dir, port=0,
                                                         bind='127.0.0.1', open=False))
        try:
            with urllib.request.urlopen(server.url() + 'cover.json', timeout=10) as response:
                assert response.status == 200
        finally:
            server.stop()

    def test_bind_all_interfaces_prints_sharp_warning(self, capsys):
        os.chdir(self.vault)
        server = CLI__Serve(block=False).cmd_serve(_args(directory=None, port=0,
                                                         bind='0.0.0.0', open=False))
        server.stop()
        out = capsys.readouterr().out
        assert 'WARNING: bound to 0.0.0.0' in out
        assert 'read-key-free' in out
