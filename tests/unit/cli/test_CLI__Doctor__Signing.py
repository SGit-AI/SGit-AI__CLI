"""`sgit doctor`'s Signing block (design__02 §5.6.2): what signing would use, from the user's Git config."""
import os
import tempfile

from sgit_ai.cli.CLI__Doctor import CLI__Doctor


class Test_CLI__Doctor__Signing:

    def setup_method(self):
        self.dir = tempfile.mkdtemp()

    def config(self, monkeypatch, text: str):
        path = os.path.join(self.dir, 'gitconfig')
        with open(path, 'w') as f:
            f.write(text)
        monkeypatch.setenv('GIT_CONFIG_GLOBAL', path)
        monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')

    def test_nothing_configured(self, monkeypatch, capsys):
        self.config(monkeypatch, '')
        summary = CLI__Doctor().signing_summary()
        assert summary['sign'] is False and summary['signing_key'] is None
        CLI__Doctor().print_signing(summary)
        out = capsys.readouterr().out
        assert 'sign by default : no' in out and 'user.signingKey not set' in out and 'SSH signatures read U' in out

    def test_an_ssh_setup(self, monkeypatch, capsys):
        key = os.path.join(self.dir, 'id_ed25519')
        open(key, 'w').close()
        self.config(monkeypatch, f'[sgit]\n\tgpgSign = true\n[gpg]\n\tformat = ssh\n[user]\n\tsigningKey = {key}\n'
                                 f'[gpg "ssh"]\n\tallowedSignersFile = {self.dir}/allowed\n')
        summary = CLI__Doctor().signing_summary()
        assert (summary['sign'], summary['format'], summary['key_file']) == (True, 'ssh', True)
        CLI__Doctor().print_signing(summary)
        out = capsys.readouterr().out
        assert 'sign by default : yes  (sgit.gpgSign)' in out and f'signing key     : {key}' in out and 'no such file' not in out

    def test_a_missing_key_file_and_an_unsupported_format(self, monkeypatch, capsys):
        self.config(monkeypatch, f'[gpg]\n\tformat = ssh\n[user]\n\tsigningKey = {self.dir}/gone\n')
        CLI__Doctor().print_signing(CLI__Doctor().signing_summary())
        assert '! no such file' in capsys.readouterr().out
        self.config(monkeypatch, '[gpg]\n\tformat = x509\n')
        summary = CLI__Doctor().signing_summary()
        assert 'x509 is not supported' in summary['error']

    def test_an_openpgp_key_id_is_not_checked_as_a_file(self, monkeypatch):
        self.config(monkeypatch, '[user]\n\tsigningKey = 0123456789ABCDEF\n')
        summary = CLI__Doctor().signing_summary()
        assert summary['format'] == 'openpgp' and summary['key_file'] is None
