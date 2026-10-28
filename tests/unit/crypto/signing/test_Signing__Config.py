"""Git config reading and signing-config resolution (design__02 §5.6), with real `git`."""
import os
import shutil

import pytest

from sgit_ai.core.Vault__Errors                       import Vault__Signing_Error
from sgit_ai.crypto.signing.Git__Config__Reader       import Git__Config__Reader
from sgit_ai.crypto.signing.Signing__Config__Resolver import Signing__Config__Resolver
from sgit_ai.safe_types.Enum__Sign_Choice             import Enum__Sign_Choice
from sgit_ai.safe_types.Enum__User_Signature_Format   import Enum__User_Signature_Format as F
from sgit_ai.schemas.Schema__Signing_Flags            import Schema__Signing_Flags
from tests.unit.crypto.signing.signing_keys           import Signing_Keys

CONFIG = '''[user]
\tsigningKey = ~/keys/first.pub
\tsigningKey = ~/keys/id.pub
[gpg]
\tformat = ssh
[gpg "ssh"]
\tallowedSignersFile = "~/allowed signers" ; trailing comment
\tprogram = /opt/ssh-keygen
[sgit]
\tgpgSign
[commit]
\tgpgSign = true
'''


class Test_Git__Config__Reader:

    def setup_method(self):
        self.keys = Signing_Keys()
        self.path = self.keys.write('gitconfig', CONFIG)

    def teardown_method(self):
        self.keys.cleanup()

    def env(self, monkeypatch):
        monkeypatch.setenv('GIT_CONFIG_GLOBAL', self.path)
        monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')

    @pytest.mark.skipif(shutil.which('git') is None, reason='git reads its own config')
    def test_values_last_wins_and_bare_booleans_with_git(self, monkeypatch):
        self.env(monkeypatch)
        values = Git__Config__Reader().read()
        assert values['user.signingkey']             == '~/keys/id.pub'
        assert values['gpg.ssh.allowedsignersfile']  == '~/allowed signers'
        assert Git__Config__Reader().as_bool(values['sgit.gpgsign'])

    @pytest.mark.skipif(shutil.which('git') is None, reason='git follows includes')
    def test_includes_are_followed_by_git(self, monkeypatch):
        extra = self.keys.write('extra', '[user]\n\tsigningKey = from-include\n')
        self.path = self.keys.write('gitconfig', CONFIG + f'[include]\n\tpath = {extra}\n')
        self.env(monkeypatch)
        assert Git__Config__Reader().read()['user.signingkey'] == 'from-include'

    def test_the_fallback_reader_gives_the_same_values(self, monkeypatch):
        self.env(monkeypatch)
        values = Git__Config__Reader().read_files()
        assert values['user.signingkey'] == '~/keys/id.pub'
        assert values['gpg.ssh.allowedsignersfile'] == '~/allowed signers'
        assert values['gpg.ssh.program'] == '/opt/ssh-keygen' and values['sgit.gpgsign'] == 'true'

    def test_the_repository_config_is_never_read(self, monkeypatch, tmp_path):
        self.env(monkeypatch)
        repo = tmp_path / 'repo'
        (repo / '.git').mkdir(parents=True)
        (repo / '.git' / 'config').write_text('[sgit]\n\tgpgSign = false\n[user]\n\tsigningKey = evil\n')
        monkeypatch.chdir(repo)
        assert Git__Config__Reader().read()['user.signingkey'] == '~/keys/id.pub'


class Test_Signing__Config__Resolver:

    def resolve(self, values: dict, **flags):
        return Signing__Config__Resolver().resolve(Schema__Signing_Flags(**flags), values=values)

    def test_sgit_gpgsign_is_the_switch_and_commit_gpgsign_alone_is_not(self):
        assert self.resolve({'sgit.gpgsign': 'true'}).sign is True
        assert self.resolve({'commit.gpgsign': 'true'}).sign is False

    def test_flags_beat_config(self):
        assert self.resolve({'sgit.gpgsign': 'true'}, sign=Enum__Sign_Choice.OFF).sign is False
        assert self.resolve({}, sign=Enum__Sign_Choice.ON).sign is True
        config = self.resolve({'user.signingkey': 'a'}, key='b')
        assert config.sign is True and str(config.signing_key) == 'b' and config.source == 'flag'

    def test_format_from_config_or_inferred_from_the_key(self):
        assert self.resolve({'gpg.format': 'ssh', 'user.signingkey': 'ABCD'}).format == F.SSH
        assert self.resolve({'user.signingkey': '~/.ssh/id_ed25519.pub'}).format == F.SSH
        assert self.resolve({'user.signingkey': 'key::ssh-ed25519 AAAA'}).format == F.SSH
        assert self.resolve({'user.signingkey': 'alice@example.com'}).format == F.OPENPGP
        assert self.resolve({}).format == F.OPENPGP

    def test_an_openssh_private_key_path_means_ssh(self):
        keys = Signing_Keys()
        _, path, _ = keys.make()
        assert self.resolve({'user.signingkey': path}).format == F.SSH
        keys.cleanup()

    def test_x509_is_refused_by_name(self):
        with pytest.raises(Vault__Signing_Error, match='x509'):
            self.resolve({'gpg.format': 'x509'})

    def test_paths_and_programs(self):
        config = self.resolve({'gpg.ssh.allowedsignersfile': '~/allowed', 'gpg.program': 'gpg2',
                               'gpg.openpgp.program': 'gpg-custom', 'gpg.mintrustlevel': 'Fully'})
        assert str(config.allowed_signers_file) == os.path.expanduser('~/allowed')
        assert str(config.gpg_program) == 'gpg-custom' and str(config.ssh_program) == 'ssh-keygen'
        assert config.min_trust_level.value == 'fully'
