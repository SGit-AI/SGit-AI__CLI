"""Signing commits and tags with your own key (Git-parity 2.2, design__02 step 4).

Real keys and the user's (temporary) Git config: `-S` / `-S<key>` / `--no-gpg-sign` /
`sgit.gpgSign`, commit, write, pull's merge commit, revert --as-commit and tags; a
signing failure writes nothing. Signing is checked by verifying, never by inspecting."""
import json
import os
import shutil
import subprocess
import tempfile

import pytest

from sgit_ai.cli.CLI__Main                              import CLI__Main
from sgit_ai.core.actions.verify.Vault__User_Signatures import Vault__User_Signatures
from sgit_ai.crypto.signing.Vault__Signing_Error        import Vault__Signing_Error
from sgit_ai.safe_types.Enum__Sign_Choice               import Enum__Sign_Choice
from sgit_ai.schemas.Schema__Signing_Flags              import Schema__Signing_Flags
from sgit_ai.storage.Vault__Commit                      import Vault__Commit
from sgit_ai.core.Vault__Sync__Base                     import Vault__Sync__Base
from tests.unit.crypto.signing.signing_keys             import Signing_Keys
from tests.unit.sync.vault_test_env                     import Vault__Test_Env

ON  = Schema__Signing_Flags(sign=Enum__Sign_Choice.ON)
OFF = Schema__Signing_Flags(sign=Enum__Sign_Choice.OFF)


class User_Signing__Base:

    def setup_method(self):
        self.keys = Signing_Keys()
        _, self.key_path, self.key_line = self.keys.make()
        self.allowed = self.keys.write('allowed_signers', f'me@x {self.key_line}\n')

    def teardown_method(self):
        self.keys.cleanup()

    def git_config(self, monkeypatch, extra: str = '', program: str = 'no-such-ssh-keygen'):
        """In-process signing (no ssh-keygen) with the test key, unless a test asks otherwise."""
        text = (f'[user]\n\tsigningKey = {self.key_path}\n[gpg]\n\tformat = ssh\n'
                f'[gpg "ssh"]\n\tprogram = {program}\n\tallowedSignersFile = {self.allowed}\n' + extra)
        monkeypatch.setenv('GIT_CONFIG_GLOBAL', self.keys.write('gitconfig', text))

    def verdict(self, directory, commit_id):
        c  = Vault__Sync__Base(crypto=self.sync.crypto, api=self.sync.api)._init_components(directory)
        vc = Vault__Commit(crypto=self.sync.crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
        commit = vc.load_commit(commit_id, c.read_key)
        return Vault__User_Signatures().result_for(commit, vc.signing_bytes(commit.json()))

    def objects(self, directory) -> int:
        return sum(len(files) for _, _, files in os.walk(os.path.join(directory, '.sg_vault', 'bare')))


class Test_Commit__User_Signing(User_Signing__Base):

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'a\n'})

    def setup_method(self):
        super().setup_method()
        self.env  = self._env.restore()
        self.sync = self.env.sync
        self.dir  = self.env.vault_dir

    def teardown_method(self):
        self.env.cleanup()
        super().teardown_method()

    def edit(self, text='a2\n'):
        with open(os.path.join(self.dir, 'a.txt'), 'w') as f:
            f.write(text)

    def cli(self, *argv) -> int:
        here = os.getcwd()
        os.chdir(self.dir)
        try:
            CLI__Main().run(['--base-url', 'http://127.0.0.1:9'] + list(argv))
            return 0
        except SystemExit as e:
            return e.code or 0
        finally:
            os.chdir(here)

    def test_commit_dash_s_signs_and_keeps_the_message(self, monkeypatch, capsys):
        self.git_config(monkeypatch)
        self.edit()
        assert self.cli('commit', '-S', 'the message') == 0
        out    = capsys.readouterr().out
        head   = self.sync.resolve_revision(self.dir, 'HEAD')
        result = self.verdict(self.dir, head)
        assert (result.status.value, str(result.principal)) == ('good', 'me@x')
        assert 'Signed with ssh key SHA256:' in out
        assert self.sync.commit(self.dir, message='x', amend=True)['message'] == 'x'      # the message was 'the message'

    def test_an_attached_key_turns_signing_on(self, monkeypatch):
        monkeypatch.setenv('GIT_CONFIG_GLOBAL', self.keys.write('gitconfig', f'[gpg "ssh"]\n\tprogram = none\n\t'
                                                                              f'allowedSignersFile = {self.allowed}\n'))
        self.edit()
        assert self.cli('commit', f'-S{self.key_path}', '-m', 'k') == 0
        assert self.verdict(self.dir, self.sync.resolve_revision(self.dir, 'HEAD')).status.value == 'good'

    def test_the_switch_is_sgit_gpgsign_not_commit_gpgsign(self, monkeypatch):
        self.git_config(monkeypatch, extra='[commit]\n\tgpgSign = true\n')
        self.edit('one\n')
        cid = self.sync.commit(self.dir, message='not signed')['commit_id']
        assert self.verdict(self.dir, cid).status.value == 'none'
        self.git_config(monkeypatch, extra='[sgit]\n\tgpgSign = true\n')
        self.edit('two\n')
        result = self.sync.commit(self.dir, message='signed')
        assert self.verdict(self.dir, result['commit_id']).status.value == 'good' and 'signed_with' in result
        self.edit('three\n')
        cid = self.sync.commit(self.dir, message='opted out', signing=OFF)['commit_id']
        assert self.verdict(self.dir, cid).status.value == 'none'

    def test_a_signing_failure_writes_nothing(self, monkeypatch, capsys):
        self.git_config(monkeypatch)
        monkeypatch.setenv('GIT_CONFIG_GLOBAL', self.keys.write('gitconfig', '[user]\n\tsigningKey = /no/such/key\n'
                                                                              '[gpg]\n\tformat = ssh\n[gpg "ssh"]\n\tprogram = none\n'))
        self.edit()
        head = self.sync.resolve_revision(self.dir, 'HEAD')
        assert self.cli('commit', '-S', 'x') == 1
        err = capsys.readouterr().err
        assert 'signing failed: cannot read the signing key /no/such/key' in err and 'sgit commit --no-gpg-sign' in err
        assert 'no commit was made and no branch moved' in err and 'nothing was written' not in err   # cli.build BR-8
        assert self.sync.resolve_revision(self.dir, 'HEAD') == head                 # no commit, no ref move: the blob
        assert self.sync.status(self.dir)['modified'] == ['a.txt']                 # and tree stay unreferenced, as git's

    def test_write_signs(self, monkeypatch):
        self.git_config(monkeypatch)
        result = self.sync.write_file(self.dir, 'w.txt', b'w\n', message='w', signing=ON)
        assert self.verdict(self.dir, result['commit_id']).status.value == 'good'

    def test_revert_as_commit_signs(self, monkeypatch):
        self.git_config(monkeypatch)
        self.edit()
        self.sync.commit(self.dir, message='change')
        result = self.sync.revert_commit(self.dir, 'HEAD', signing=ON)
        assert self.verdict(self.dir, result['commit_id']).status.value == 'good'

    def test_a_signed_tag(self, monkeypatch, capsys):
        self.git_config(monkeypatch)
        result = self.sync.tag_create(self.dir, 'v1.0', message='release', signing=ON)
        assert result['signed_with'].startswith('ssh key SHA256:')
        shown = self.sync.tag_show(self.dir, 'v1.0')
        assert shown['status'] == 'verified' and shown['user_signature']['status'] == 'good'
        assert shown['user_signature']['principal'] == 'me@x'

    @pytest.mark.skipif(shutil.which('ssh-keygen') is None, reason='real ssh-keygen')
    def test_signing_through_ssh_keygen(self, monkeypatch):
        self.git_config(monkeypatch, program='ssh-keygen')
        self.edit()
        cid = self.sync.commit(self.dir, message='keygen', signing=ON)['commit_id']
        assert self.verdict(self.dir, cid).status.value == 'good'

    @pytest.mark.skipif(shutil.which('gpg') is None, reason='real gpg')
    def test_signing_and_verifying_with_gpg(self, monkeypatch):
        home = tempfile.mkdtemp(prefix='g', dir='/tmp')                 # short: gpg-agent's socket path is limited
        os.chmod(home, 0o700)
        monkeypatch.setenv('GNUPGHOME', home)
        try:
            subprocess.run(['gpg', '--batch', '--pinentry-mode', 'loopback', '--passphrase', '', '--quick-gen-key',
                            'Alice <alice@x>', 'ed25519', 'sign', '1y'], capture_output=True, check=True)
            monkeypatch.setenv('GIT_CONFIG_GLOBAL', self.keys.write('gitconfig', '[user]\n\tsigningKey = alice@x\n'))
            self.edit()
            cid    = self.sync.commit(self.dir, message='gpg', signing=ON)['commit_id']
            result = self.verdict(self.dir, cid)
            assert (result.status.value, str(result.principal)) == ('good', 'Alice <alice@x>')
        finally:
            subprocess.run(['gpgconf', '--kill', 'gpg-agent'], capture_output=True)
            shutil.rmtree(home, ignore_errors=True)


class Test_Pull__User_Signing(User_Signing__Base):

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'shared.txt': 'base\n', 'b.txt': 'b\n'})

    def setup_method(self):
        super().setup_method()
        self.env  = self._env.restore()
        self.sync = self.env.sync

    def teardown_method(self):
        self.env.cleanup()
        super().teardown_method()

    def test_the_merge_commit_of_a_pull_is_signed_with_dash_s(self, monkeypatch):
        self.git_config(monkeypatch)
        alice, bob = self.env.alice_dir, self.env.bob_dir
        with open(os.path.join(alice, 'shared.txt'), 'w') as f:
            f.write('alice\n')
        self.sync.commit(alice, message='alice')
        self.sync.push(alice)
        with open(os.path.join(bob, 'b.txt'), 'w') as f:
            f.write('bob\n')
        self.sync.commit(bob, message='bob')
        result = self.sync.pull(bob, signing=ON)
        assert result['status'] == 'merged'
        assert self.verdict(bob, self.sync.resolve_revision(bob, 'HEAD')).status.value == 'good'


class Test_Signer__Error_Prefix:
    """cli.build BR-8: gpg's own message already starts with `gpg: `; it is not prefixed twice. The
    programs are real executables that fail the way gpg and ssh-keygen do."""

    def program(self, tmp_path, name: str, stderr: str) -> str:
        path = tmp_path / name
        path.write_text(f"#!/bin/sh\ncat > /dev/null\nprintf '%s' '{stderr}' >&2\nexit 2\n")
        path.chmod(0o755)
        return str(path)

    def test_gpg_and_ssh_keygen_messages_carry_the_program_once(self, tmp_path):
        from sgit_ai.crypto.signing.GPG__Signer           import GPG__Signer
        from sgit_ai.crypto.signing.SSH__Signer           import SSH__Signer
        from sgit_ai.crypto.signing.Vault__Signing_Error  import Vault__Signing_Error
        from sgit_ai.schemas.Schema__Signing_Config       import Schema__Signing_Config
        gpg = self.program(tmp_path, 'gpg', '[GNUPG:] KEY_CONSIDERED x\ngpg: signing failed: No secret key\n')
        with pytest.raises(Vault__Signing_Error) as error:
            GPG__Signer().sign(b'payload', Schema__Signing_Config(format='openpgp', signing_key='ABCD', gpg_program=gpg))
        assert str(error.value) == 'gpg: signing failed: No secret key'
        ssh = self.program(tmp_path, 'ssh-keygen', 'Load key "x": invalid format\n')
        with pytest.raises(Vault__Signing_Error) as error:
            SSH__Signer().sign(b'payload', Schema__Signing_Config(format='ssh', signing_key='key::ssh-ed25519 AAAA',
                                                                  ssh_program=ssh))
        assert str(error.value) == f'{ssh}: Load key "x": invalid format'
