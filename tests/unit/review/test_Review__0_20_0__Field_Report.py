"""Field report on 0.20.0 from the sgit.ai site agent (9 Oct 2026): daily-use issues.

 1  the clone hint named `sgit log` (now `sgit history log`)
 2  `sgit history log` on a read-only clone printed "(no commits)", exit 0
 3  `--vault-key <read key>:<vault id>` crashed with InvalidTag
 4  doctor / status did not recognise the default (unnamed) server
 5  doctor sent the saved token as `Authorization: Bearer` (server reads x-sgraph-access-token)
 6  `pki encrypt --recipient <own fingerprint>` needed your own bundle imported
 7  `pki verify` named the signer by label only
    + `pki decrypt --output` / stdout; a signing key that does not load no longer encrypts unsigned"""
import json
import os
import shutil
import tempfile
from types import SimpleNamespace

import pytest

from sgit_ai.cli.CLI__Main                 import CLI__Main
from sgit_ai.cli.CLI__Vault                import CLI__Vault
from sgit_ai.crypto.Vault__Crypto          import Vault__Crypto


def _log_args(directory, **kw):
    base = dict(directory=directory, oneline=True, graph=False, limit=None, grep=None, since=None,
                until=None, author=None, stat=False, vault_key=None, read_key=None)
    base.update(kw)
    return SimpleNamespace(**base)


class Test_Report_1__Moved_Commands:

    def test_clone_hint_names_history_log(self):
        import inspect
        source = inspect.getsource(CLI__Vault)
        assert "sgit log  " not in source
        assert 'sgit history log     — view commit history' in source

    @pytest.mark.parametrize('word, place', [('log'   , 'sgit history log'   ),
                                             ('reflog', 'sgit history reflog'),
                                             ('stash' , 'sgit vault stash'   ),
                                             ('fsck'  , 'sgit check fsck'    )])
    def test_old_top_level_name_points_to_its_new_place(self, word, place, capsys):
        with pytest.raises(SystemExit) as exc:
            CLI__Main().run([word])
        assert exc.value.code == 2
        assert place in capsys.readouterr().err

    def test_global_flags_before_the_word_are_skipped(self, capsys):
        with pytest.raises(SystemExit) as exc:
            CLI__Main().run(['--base-url', 'http://127.0.0.1:9', 'log'])
        assert exc.value.code == 2
        assert 'sgit history log' in capsys.readouterr().err

    def test_a_word_that_is_nowhere_keeps_argparse_error(self, capsys):
        with pytest.raises(SystemExit) as exc:
            CLI__Main().run(['no-such-command'])
        assert exc.value.code == 2
        assert 'invalid choice' in capsys.readouterr().err


class Test_Report_2_3__History_Log_Keys:

    def test_read_only_clone_shows_its_history(self, read_only_clone, capsys):
        CLI__Vault().cmd_log(_log_args(read_only_clone['ro_dir']))
        out = capsys.readouterr().out
        assert 'initial commit' in out
        assert '(no commits)' not in out

    def test_read_key_shorthand_as_vault_key(self, read_only_clone, capsys):
        key = f"{read_only_clone['read_key_hex']}:{read_only_clone['vault_id']}"
        CLI__Vault().cmd_log(_log_args(read_only_clone['ro_dir'], vault_key=key))
        assert 'initial commit' in capsys.readouterr().out

    @pytest.mark.parametrize('public', [True, False])
    def test_declared_read_key_with_and_without_vault_id(self, read_only_clone, public, capsys):
        crypto = Vault__Crypto()
        key    = crypto.format_read_key(read_only_clone['read_key_hex'], public=public)
        for value in (key, f"{key}:{read_only_clone['vault_id']}"):
            CLI__Vault().cmd_log(_log_args(read_only_clone['ro_dir'], vault_key=value))
            assert 'initial commit' in capsys.readouterr().out

    def test_vault_key_still_works(self, read_only_clone, capsys):
        CLI__Vault().cmd_log(_log_args(read_only_clone['ro_dir'],
                                       vault_key=read_only_clone['source_vault_key']))
        assert 'initial commit' in capsys.readouterr().out

    def test_wrong_key_exits_1_with_a_message_not_invalid_tag(self, read_only_clone, capsys):
        wrong = f"{'ab' * 32}:{read_only_clone['vault_id']}"
        with pytest.raises(SystemExit) as exc:
            CLI__Vault().cmd_log(_log_args(read_only_clone['ro_dir'], vault_key=wrong))
        assert exc.value.code == 1
        assert 'does not open this vault' in capsys.readouterr().err

    def test_declared_read_key_that_does_not_parse_exits_1(self, read_only_clone, capsys):
        with pytest.raises(SystemExit) as exc:
            CLI__Vault().cmd_log(_log_args(read_only_clone['ro_dir'], vault_key='sgit_public_read_zz:abcd1234'))
        assert exc.value.code == 1
        assert 'read key' in capsys.readouterr().err

    def test_no_key_anywhere_exits_1_instead_of_no_commits(self, read_only_clone, capsys):
        os.remove(os.path.join(read_only_clone['ro_dir'], '.sg_vault', 'local', 'clone_mode.json'))
        with pytest.raises(SystemExit) as exc:
            CLI__Vault().cmd_log(_log_args(read_only_clone['ro_dir']))
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert 'needs a key' in captured.err
        assert '(no commits)' not in captured.out


class _Token_Server:
    """A loopback server that, like SG/Send behind its access-token middleware, reads
    the token from x-sgraph-access-token only and answers 401 without it."""

    def __init__(self, token):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        seen = self.seen = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                seen.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
                if self.headers.get('x-sgraph-access-token') != token:
                    self.send_response(401); self.end_headers(); return
                if self.path == '/api/info':
                    body = json.dumps({'service': 'sgraph-send', 'version': 'test'}).encode()
                elif self.path.startswith('/api/vault/list/'):
                    body = b'[]'
                else:
                    self.send_response(404); self.end_headers(); return
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(body)

        self.httpd  = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url    = f'http://127.0.0.1:{self.httpd.server_address[1]}'
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class Test_Report_4_5__Doctor_And_Status:

    TOKEN = 'field-report-token'
    _env  = None

    @classmethod
    def setup_class(cls):
        from tests._helpers.vault_test_env import Vault__Test_Env
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.md': 'a'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        from sgit_ai.cli.CLI__Token_Store import CLI__Token_Store
        self.s      = self._env.restore()
        self.server = _Token_Server(self.TOKEN)
        CLI__Token_Store().save_token(self.TOKEN, self.s.vault_dir)      # what `push --token` saves

    def teardown_method(self):
        self.server.stop()
        self.s.cleanup()

    def _doctor(self, **kw):
        from sgit_ai.cli.CLI__Doctor import CLI__Doctor
        args = SimpleNamespace(directory=self.s.vault_dir, remote=None, json=True, timeout=2,
                               write_probe=False, token=None, base_url=None, verify_tls=None)
        for k, v in kw.items():
            setattr(args, k, v)
        try:
            CLI__Doctor().cmd_doctor(args)
            return 0
        except SystemExit as exc:
            return exc.code

    def _checks(self, out):
        report = json.loads(out[out.index('{'):])
        return {c['name']: c for c in report['checks']}

    def test_doctor_checks_the_server_a_vault_without_a_named_remote_uses(self, monkeypatch, capsys):
        monkeypatch.setenv('SGIT_DEFAULT_BASE_URL', self.server.url)     # a vault that records no server
        assert self._doctor() == 0
        checks = self._checks(capsys.readouterr().out)
        assert checks['api_info']['status']    == 'pass'
        assert checks['vault_known']['status'] == 'pass'
        assert self.server.seen                                       # it reached the vault's server

    def test_doctor_uses_the_recorded_server(self, capsys):
        from sgit_ai.cli.CLI__Token_Store import CLI__Token_Store
        CLI__Token_Store().save_base_url(self.server.url, self.s.vault_dir)
        assert self._doctor(json=False) == 0
        out = capsys.readouterr().out
        assert f'checking the server this vault uses: {self.server.url}' in out

    def test_doctor_sends_the_saved_token_the_way_push_does(self, monkeypatch, capsys):
        monkeypatch.setenv('SGIT_DEFAULT_BASE_URL', self.server.url)
        self._doctor()
        checks = self._checks(capsys.readouterr().out)
        assert 'token rejected' not in str(checks['token_verify'].get('message'))
        assert checks['token_verify']['status'] != 'fail'
        assert all(h.get('x-sgraph-access-token') == self.TOKEN for _, h in self.server.seen)

    def test_doctor_with_the_wrong_token_still_fails(self, monkeypatch, capsys):
        from sgit_ai.cli.CLI__Token_Store import CLI__Token_Store
        CLI__Token_Store().save_token('not-the-token', self.s.vault_dir)
        monkeypatch.setenv('SGIT_DEFAULT_BASE_URL', self.server.url)
        assert self._doctor() == 1
        assert self._checks(capsys.readouterr().out)['api_info']['status'] == 'fail'

    def test_status_names_the_server_instead_of_not_configured(self, capsys):
        from sgit_ai.cli.CLI__Token_Store import CLI__Token_Store
        os.remove(os.path.join(self.s.vault_dir, '.sg_vault', 'local', 'token'))   # nothing recorded at all
        args = SimpleNamespace(directory=self.s.vault_dir, token=None, base_url=None, remote=None,
                               verify_tls=None, transport='auto', explain=False)
        CLI__Vault().cmd_status(args)
        out = capsys.readouterr().out
        assert 'not configured' not in out


class Test_Report_6_7__PKI:

    PASSPHRASE = 'field-report-passphrase'
    _base = None
    _fp   = None
    _sfp  = None

    @classmethod
    def setup_class(cls):
        from sgit_ai.cli.CLI__PKI import CLI__PKI
        cls._base = tempfile.mkdtemp()
        meta      = CLI__PKI().setup(cls._base).key_store.generate_and_store('me', cls.PASSPHRASE)
        cls._fp, cls._sfp = meta['encryption_fingerprint'], meta['signing_fingerprint']

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls._base, ignore_errors=True)

    def setup_method(self):
        self.work = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def _pki(self):
        from sgit_ai.cli.CLI__PKI import CLI__PKI
        return CLI__PKI().setup(self._base)

    def _file(self, name, data: bytes):
        path = os.path.join(self.work, name)
        with open(path, 'wb') as f:
            f.write(data)
        return path

    def _encrypt(self, path, recipient=None, fingerprint=None, output=None):
        self._pki().cmd_encrypt(SimpleNamespace(file=path, recipient=recipient or self._fp,
                                                fingerprint=fingerprint, output=output))

    def _decrypt(self, path, output=None):
        self._pki().cmd_decrypt(SimpleNamespace(file=path, fingerprint=self._fp, output=output))

    def test_encrypt_to_your_own_key_without_importing_it(self, monkeypatch, capsys):
        monkeypatch.setenv('SG_SEND_PASSPHRASE', self.PASSPHRASE)
        assert self._pki().keyring.list_contacts() == []
        path = self._file('secret.txt', b'provision me')
        self._encrypt(path)
        os.remove(path)
        self._decrypt(path + '.enc')
        with open(path, 'rb') as f:
            assert f.read() == b'provision me'

    def test_unknown_recipient_still_refused(self, capsys):
        with pytest.raises(SystemExit) as exc:
            self._encrypt(self._file('x.txt', b'x'), recipient='sha256:' + '0' * 64)
        assert exc.value.code == 1
        assert 'neither a contact nor one of your key pairs' in capsys.readouterr().err

    def test_a_signing_key_that_does_not_load_never_encrypts_unsigned(self, monkeypatch, capsys):
        monkeypatch.setenv('SG_SEND_PASSPHRASE', self.PASSPHRASE)
        pki    = self._pki()
        bundle = pki.key_store.export_public_bundle(self._fp)          # recipient as a contact, so the
        pki.keyring.add_contact(label='me', fingerprint=self._fp,      # old code reaches the signing step
                                public_key_pem=bundle['encrypt'])
        try:
            path = self._file('x.txt', b'x')
            with pytest.raises(SystemExit) as exc:
                self._encrypt(path, fingerprint='sha256:' + 'f' * 64)
            assert exc.value.code == 1
            assert not os.path.exists(path + '.enc')
        finally:
            pki.keyring.remove_contact(self._fp)

    def test_wrong_passphrase_is_a_message_not_a_traceback(self, monkeypatch, capsys):
        monkeypatch.setenv('SG_SEND_PASSPHRASE', 'not-the-passphrase')
        with pytest.raises(SystemExit) as exc:
            self._pki().cmd_sign(SimpleNamespace(file=self._file('x.txt', b'x'), fingerprint=self._fp))
        assert exc.value.code == 1
        assert 'wrong passphrase' in capsys.readouterr().err

    def _sign(self, monkeypatch, data=b'#!/bin/sh\necho entry\n'):
        monkeypatch.setenv('SG_SEND_PASSPHRASE', self.PASSPHRASE)
        path = self._file('entry.sh', data)
        self._pki().cmd_sign(SimpleNamespace(file=path, fingerprint=self._fp))
        return path

    def test_verify_prints_the_signing_fingerprint_and_checks_your_own_keys(self, monkeypatch, capsys):
        path = self._sign(monkeypatch)
        capsys.readouterr()
        self._pki().cmd_verify(SimpleNamespace(file=path, signature=path + '.sig', json=False))
        out = capsys.readouterr().out
        assert 'Signature valid' in out
        assert self._sfp in out
        assert 'me' in out

    def test_verify_json(self, monkeypatch, capsys):
        path = self._sign(monkeypatch)
        capsys.readouterr()
        self._pki().cmd_verify(SimpleNamespace(file=path, signature=path + '.sig', json=True))
        report = json.loads(capsys.readouterr().out)
        assert report == dict(valid=True, signing_fingerprint=self._sfp, signer_label='me', signer_source='own key')

    def test_verify_json_on_a_tampered_file_exits_1(self, monkeypatch, capsys):
        path = self._sign(monkeypatch)
        with open(path, 'ab') as f:
            f.write(b'rm -rf ~\n')
        capsys.readouterr()
        with pytest.raises(SystemExit) as exc:
            self._pki().cmd_verify(SimpleNamespace(file=path, signature=path + '.sig', json=True))
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().out)['valid'] is False

    def test_decrypt_keeps_binary_bytes_exactly_and_writes_0600(self, monkeypatch, capsys):
        monkeypatch.setenv('SG_SEND_PASSPHRASE', self.PASSPHRASE)
        data = bytes(range(256)) * 4                          # not UTF-8: was latin-1 decoded, UTF-8 written
        path = self._file('blob.bin', data)
        self._encrypt(path)
        out  = os.path.join(self.work, 'out.bin')
        self._decrypt(path + '.enc', output=out)
        with open(out, 'rb') as f:
            assert f.read() == data
        assert os.stat(out).st_mode & 0o077 == 0

    def test_decrypt_to_stdout_leaves_no_plaintext_file(self, monkeypatch, capfdbinary):
        monkeypatch.setenv('SG_SEND_PASSPHRASE', self.PASSPHRASE)
        path = self._file('k.txt', b'the-key')
        self._encrypt(path)
        os.remove(path)
        self._decrypt(path + '.enc', output='-')
        assert capfdbinary.readouterr().out.endswith(b'the-key')
        assert sorted(os.listdir(self.work)) == ['k.txt.enc']

    def test_decrypt_verifies_a_signature_by_your_own_key(self, monkeypatch, capsys):
        monkeypatch.setenv('SG_SEND_PASSPHRASE', self.PASSPHRASE)
        path = self._file('s.txt', b'signed')
        self._encrypt(path, fingerprint=self._fp)
        self._decrypt(path + '.enc', output=os.path.join(self.work, 'o.txt'))
        out = capsys.readouterr().out
        assert 'Signature verified' in out
        assert self._sfp in out


class Test_Report_Note__Clone_Key_From_Stdin:

    def _run_until_clone(self, monkeypatch, stdin_text, argv):
        import io
        seen = {}
        monkeypatch.setattr('sys.stdin', io.StringIO(stdin_text))
        monkeypatch.setattr(CLI__Vault, 'cmd_clone', lambda self, args: seen.setdefault('key', args.vault_key))
        CLI__Main().run(argv)
        return seen.get('key')

    def test_dash_reads_the_key_from_stdin(self, monkeypatch, tmp_path):
        key = 'sgit_public_read_' + 'ab' * 32 + ':abcd1234'
        assert self._run_until_clone(monkeypatch, key + '\n', ['clone', '-', str(tmp_path / 'c')]) == key

    def test_empty_stdin_exits_1(self, monkeypatch, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            self._run_until_clone(monkeypatch, '', ['clone', '-', str(tmp_path / 'c')])
        assert exc.value.code == 1
        assert 'on stdin' in capsys.readouterr().err
