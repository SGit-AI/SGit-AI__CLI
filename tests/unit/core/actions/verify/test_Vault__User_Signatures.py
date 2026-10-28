"""Showing and checking user signatures on a real vault (design__02 step 5): `check verify`
counts and exit codes, `history log / show --show-signature` in Git's words. Commits are
signed with a real key (in-process SSH signer); trust comes from the user's Git config
(GIT_CONFIG_GLOBAL in a temp folder), never from the vault."""
import json
import os
import time

import pytest

from sgit_ai.cli.CLI__Main                              import CLI__Main
from sgit_ai.core.Vault__Sync__Base                     import Vault__Sync__Base
from sgit_ai.core.actions.verify.Vault__User_Signatures import Vault__User_Signatures
from sgit_ai.crypto.signing.SSH__Signer__In_Process     import SSH__Signer__In_Process
from sgit_ai.crypto.signing.User__Signer                import User__Signer
from sgit_ai.schemas.Schema__Signing_Config             import Schema__Signing_Config
from sgit_ai.storage.Vault__Commit                      import Vault__Commit
from tests.unit.crypto.signing.signing_keys             import Signing_Keys
from tests.unit.sync.vault_test_env                     import Vault__Test_Env


class Signer__Of_Other_Bytes:
    """A real signer that signs the wrong bytes: its signature is genuine but does not
    cover the commit (what a tampered commit looks like to a verifier)."""
    def __init__(self, key_path):
        self.key_path = key_path

    def sign(self, payload: bytes):
        return SSH__Signer__In_Process().sign(payload + b'tampered', self.key_path)


class Test_Vault__User_Signatures:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'a\n'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync
        self.dir  = self.env.vault_dir
        self.keys = Signing_Keys()
        _, self.key_path, self.key_line = self.keys.make()

    def teardown_method(self):
        self.env.cleanup()
        self.keys.cleanup()

    def trust(self, monkeypatch, allowed: bool = True):
        allowed_file = self.keys.write('allowed_signers', f'me@x {self.key_line}\n' if allowed else '\n')
        monkeypatch.setenv('GIT_CONFIG_GLOBAL', self.keys.write('gitconfig', f'[gpg "ssh"]\n\tallowedSignersFile = {allowed_file}\n'))
        monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')

    def signed_commit(self, message='signed', signer=None) -> str:
        """A commit on top of this clone's head, signed by the clone key and by `signer`
        (the in-process SSH signer by default), made through Vault__Commit.create_commit."""
        base   = Vault__Sync__Base(crypto=self.sync.crypto, api=self.sync.api)
        c      = base._init_components(self.dir)
        config = base._read_local_config(self.dir, c.storage)
        index  = c.branch_manager.load_branch_index(self.dir, c.branch_index_file_id, c.read_key)
        meta   = c.branch_manager.get_branch_by_id(index, str(config.my_branch_id))
        head   = c.ref_manager.read_ref(str(meta.head_ref_id), c.read_key)
        vc     = Vault__Commit(crypto=self.sync.crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
        tree   = str(vc.load_commit(head, c.read_key).tree_id)
        key    = c.key_manager.load_private_key_locally(str(meta.public_key_id), c.storage.local_dir(self.dir))
        signer = signer or User__Signer(config=Schema__Signing_Config(format='ssh', signing_key=self.key_path,
                                                                       ssh_program='no-such-ssh-keygen'))
        cid    = vc.create_commit(read_key=c.read_key, tree_id=tree, parent_ids=[head], message=message,
                                  branch_id=str(config.my_branch_id), signing_key=key,
                                  author_key_id=str(meta.public_key_id), user_signer=signer)
        c.ref_manager.write_ref(str(meta.head_ref_id), cid, c.read_key)
        return cid

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

    # --- the chain walk ---------------------------------------------------------------

    def test_counts_good_untrusted_and_none(self, monkeypatch):
        self.trust(monkeypatch)
        self.signed_commit()
        report = self.sync.verify_signatures(self.dir, user_signatures=Vault__User_Signatures().setup())
        assert report['counts']['verified'] == report['total']                      # the clone signatures still verify
        assert report['user_counts']['good'] == 1 and report['user_counts']['none'] == report['total'] - 1
        self.trust(monkeypatch, allowed=False)
        report = self.sync.verify_signatures(self.dir, user_signatures=Vault__User_Signatures().setup())
        assert report['user_counts']['untrusted'] == 1

    def test_a_user_signature_over_other_bytes_is_bad_and_the_clone_signature_still_verifies(self, monkeypatch):
        self.trust(monkeypatch)
        cid    = self.signed_commit(signer=Signer__Of_Other_Bytes(self.key_path))
        report = self.sync.verify_signatures(self.dir, user_signatures=Vault__User_Signatures().setup())
        assert report['user_by_status']['bad'] == [cid] and report['counts']['bad'] == 0

    def test_a_failing_user_signer_stores_nothing(self, monkeypatch):
        from sgit_ai.crypto.signing.Vault__Signing_Error import Vault__Signing_Error
        before = sum(len(f) for _, _, f in os.walk(os.path.join(self.dir, '.sg_vault', 'bare')))
        broken = User__Signer(config=Schema__Signing_Config(format='ssh', signing_key=self.key_path + '.missing',
                                                              ssh_program='no-such-ssh-keygen'))
        with pytest.raises(Vault__Signing_Error, match='cannot read the signing key'):
            self.signed_commit(signer=broken)
        assert sum(len(f) for _, _, f in os.walk(os.path.join(self.dir, '.sg_vault', 'bare'))) == before

    # --- check verify -------------------------------------------------------------------

    def test_check_verify_prints_the_user_line_and_passes(self, monkeypatch, capsys):
        self.trust(monkeypatch)
        self.signed_commit()
        assert self.cli('check', 'verify') == 0
        out = capsys.readouterr().out
        assert 'User signatures: 1 good, 0 untrusted, 0 bad' in out

    def test_check_verify_without_user_signatures_prints_no_user_line(self, monkeypatch, capsys):
        self.trust(monkeypatch)
        assert self.cli('check', 'verify') == 0
        assert 'User signatures' not in capsys.readouterr().out

    def test_check_verify_fails_on_a_bad_user_signature(self, monkeypatch, capsys):
        self.trust(monkeypatch)
        cid = self.signed_commit(signer=Signer__Of_Other_Bytes(self.key_path))
        assert self.cli('check', 'verify') == 1
        assert f'! {cid}  user signature does not verify' in capsys.readouterr().out

    def test_require_user_signature(self, monkeypatch, capsys):
        self.trust(monkeypatch)
        self.signed_commit()
        assert self.cli('check', 'verify', '--require-user-signature') == 1           # the earlier commits are unsigned
        assert 'without a good user signature' in capsys.readouterr().out

    def test_require_user_signature_exempts_only_inits_empty_root_commit(self, monkeypatch, capsys):
        """The vault's first commit (sgit init: no parent, empty tree) cannot carry a user signature;
        every commit with content must. --limit N scopes the gate to the newest N commits."""
        self.trust(monkeypatch)
        self.signed_commit()
        report = self.sync.verify_signatures(self.dir, user_signatures=Vault__User_Signatures().setup())
        assert len(report['user_exempt']) == 1                                      # init's commit only
        assert report['user_counts']['none'] == report['total'] - 1                  # the fixture's content commit too
        assert self.cli('check', 'verify', '--require-user-signature') == 1           # that content commit is unsigned
        capsys.readouterr()
        assert self.cli('check', 'verify', '--require-user-signature', '--limit', '1') == 0
        assert 'Checked 1 commit(s)' in capsys.readouterr().out
        self.signed_commit(message='second')
        assert self.cli('check', 'verify', '--require-user-signature', '--limit', '2') == 0
        assert self.cli('check', 'verify', '--require-user-signature', '--limit', '3') == 1       # reaches the unsigned one

    def test_untrusted_does_not_fail_as_in_git(self, monkeypatch, capsys):
        self.trust(monkeypatch, allowed=False)
        self.signed_commit()
        assert self.cli('check', 'verify') == 0
        assert '1 untrusted' in capsys.readouterr().out

    def test_check_verify_json(self, monkeypatch, capsys):
        self.trust(monkeypatch)
        cid = self.signed_commit()
        assert self.cli('check', 'verify', '--json') == 0
        report = json.loads(capsys.readouterr().out)
        assert report['user_counts']['good'] == 1 and report['user_by_status'] == {'good': [cid]}

    # --- history ------------------------------------------------------------------------

    def test_log_and_show_with_show_signature_in_gits_words(self, monkeypatch, capsys):
        self.trust(monkeypatch)
        cid = self.signed_commit()
        assert self.cli('history', 'log', '--show-signature') == 0
        out = capsys.readouterr().out
        assert 'Good "git" signature for me@x with ED25519 key SHA256:' in out
        assert out.count('Good "git" signature') == 1                                  # unsigned commits print nothing
        assert self.cli('history', 'show', cid, '--show-signature') == 0
        assert 'Good "git" signature for me@x' in capsys.readouterr().out

    def test_untrusted_wording(self, monkeypatch, capsys):
        self.trust(monkeypatch, allowed=False)
        self.signed_commit()
        assert self.cli('history', 'log', '--show-signature') == 0
        out = capsys.readouterr().out
        assert 'Good "git" signature with ED25519 key SHA256:' in out and 'No principal matched.' in out

    def test_the_json_object_of_an_unsigned_and_a_signed_commit(self, monkeypatch):
        from sgit_ai.schemas.Schema__Object_Commit import Schema__Object_Commit
        users = Vault__User_Signatures()
        assert users.as_json(users.result_for(Schema__Object_Commit())) == {
            'status': 'none', 'code': 'N', 'format': '', 'principal': '', 'key_type': '', 'key_fingerprint': '',
            'signed_at_ms': '', 'reason': ''}
        self.trust(monkeypatch)
        self.signed_commit()
        report = self.sync.verify_signatures(self.dir, user_signatures=Vault__User_Signatures().setup())
        assert set(report['user_counts']) == {'good', 'untrusted', 'bad', 'expired-signature', 'expired-key',
                                              'revoked', 'cannot-check', 'none'}
