"""Fixed in 0.21.0 — one exported variable no longer redirects a vault (review d3b8eef S1 residual).

0.21.0 records the server at init and clone, but a vault made before it (or by
clone-branch / clone-headless / init --restore) recorded none, and every command on it
followed SGIT_DEFAULT_BASE_URL: the access token reached whatever host it named, about
20 commands with no warning (tag create, branch switch/merge, write --push, vault move,
check verify) because they built a bare Vault__API(). Now CLI__Main.run decides the
server once per command: the vault's recorded server; else the default, recorded on
first use; and if the variable names another server, a refusal.

Threat model: TM-F22.
"""
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sgit_ai.cli.CLI__Main             import CLI__Main
from sgit_ai.cli.CLI__Vault            import CLI__Vault
from sgit_ai.network.api.Vault__API    import Vault__API, DEFAULT_BASE_URL
from tests._helpers.vault_test_env     import Vault__Test_Env


class _Listener:
    """A loopback host that records every request it gets (header names only)."""

    def __init__(self):
        seen = self.seen = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _any(self):
                seen.append((self.command, self.path, sorted(k.lower() for k in self.headers.keys())))
                self.send_response(404); self.end_headers()
            do_GET = do_PUT = do_POST = do_DELETE = _any

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url   = f'http://127.0.0.1:{self.httpd.server_address[1]}'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown(); self.httpd.server_close()


class Test_Fixed__Server_Pin:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.md': 'a'})                  # records no server, like a pre-0.21 vault

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.cwd      = os.getcwd()
        self.s        = self._env.restore()
        self.vault    = self.s.vault_dir
        self.listener = _Listener()
        self.local    = os.path.join(self.vault, '.sg_vault', 'local')
        with open(os.path.join(self.local, 'token'), 'w') as f:
            f.write('secret-token')

    def teardown_method(self):
        os.chdir(self.cwd)
        self.listener.stop()
        self.s.cleanup()

    def _run(self, *argv):
        os.chdir(self.vault)                                                # run from inside the vault, as a user does
        try:
            CLI__Main().run(list(argv))
            return 0
        except SystemExit as exc:
            return exc.code

    def test_an_unrecorded_vault_refuses_the_variable(self, monkeypatch, capsys):
        monkeypatch.setenv('SGIT_DEFAULT_BASE_URL', self.listener.url)
        for argv in (['status'], ['pull'], ['push']):
            assert self._run(*argv) == 1
        assert self.listener.seen == []                                     # nothing, token included, reached it
        assert 'records no server' in capsys.readouterr().err
        assert not os.path.exists(os.path.join(self.local, 'base_url'))

    def test_an_unrecorded_vault_records_the_default_on_first_use(self, monkeypatch):
        monkeypatch.delenv('SGIT_DEFAULT_BASE_URL', raising=False)
        self._run('history', 'log')                             # local only: no request is made
        with open(os.path.join(self.local, 'base_url')) as f:
            assert f.read() == DEFAULT_BASE_URL

    def test_the_recorded_server_wins_for_every_command_including_bare_clients(self, monkeypatch):
        with open(os.path.join(self.local, 'base_url'), 'w') as f:
            f.write('http://127.0.0.1:9')
        monkeypatch.setenv('SGIT_DEFAULT_BASE_URL', self.listener.url)
        seen = {}
        monkeypatch.setattr(CLI__Vault, 'cmd_status',                     # what a command that builds a bare
                            lambda self, a: seen.setdefault('server', Vault__API().default_base_url()))   # client gets
        self._run('status')
        assert seen['server'] == 'http://127.0.0.1:9'
        assert os.environ['SGIT_DEFAULT_BASE_URL'] == self.listener.url    # restored after the command
        self._run('status')
        assert self.listener.seen == []

    def test_base_url_flag_still_chooses(self, monkeypatch):
        monkeypatch.setenv('SGIT_DEFAULT_BASE_URL', 'http://127.0.0.1:9')
        seen = {}
        monkeypatch.setattr(CLI__Vault, 'cmd_status', lambda self, a: seen.setdefault('server', Vault__API().default_base_url()))
        self._run('--base-url', self.listener.url, 'status')
        assert seen['server'] == self.listener.url

    @pytest.mark.parametrize('remedy', ['remote', 'flag'])
    def test_both_remedies_the_refusal_names_work_as_written(self, monkeypatch, capsys, remedy):
        """Review 0a0707d R2: the message said `sgit remote add origin <url>`, which the same
        check refused. Both remedies it names now run, and the vault then uses that server."""
        monkeypatch.setenv('SGIT_DEFAULT_BASE_URL', self.listener.url)
        assert self._run('status') == 1
        err = capsys.readouterr().err
        assert '--base-url <url>' in err and 'sgit remote add origin <url>' in err
        if remedy == 'remote':
            assert self._run('remote', 'add', 'origin', 'http://127.0.0.1:9', '--no-health-check') == 0   # port 9 is closed
        seen = {}
        monkeypatch.setattr(CLI__Vault, 'cmd_status', lambda self, a: seen.setdefault('server', Vault__API().default_base_url()))
        argv = ('status',) if remedy == 'remote' else ('--base-url', 'http://127.0.0.1:9', 'status')
        assert self._run(*argv) == 0
        assert seen['server'] == 'http://127.0.0.1:9'
        assert self.listener.seen == []
