"""Commit message length (28 Oct).

The encrypted message sat in a 1,024-character base64 field: 740 bytes of message, a
raw ValueError past it, and a commit any other client wrote with a longer message
could not be read by the CLI at all. Now:
- reading accepts up to 1 MiB (a long message from another client never breaks a walk);
- writing takes 740 bytes, or 64 KiB on a vault with `long-messages`, refused before
  anything is written with the size in bytes;
- adding `long-messages` raises min_client to 0.26.4, so older clients are told to update."""
import os

import pytest

from sgit_ai.cli.CLI__Main                       import CLI__Main
from sgit_ai.schemas.Schema__Object_Commit       import Schema__Object_Commit
from sgit_ai.storage.Vault__Commit               import Vault__Commit
from sgit_ai.storage.Vault__Commit_Message       import (Vault__Commit_Message_Too_Long_Error, SHORT_MESSAGE_BYTES,
                                                         LONG_MESSAGE_BYTES)
from sgit_ai.storage.Vault__Format               import (Vault__Format, Vault__Client_Too_Old_Error, FEATURE_LONG_MESSAGES,
                                                         LONG_MESSAGES_MIN_CLIENT)
from tests.unit.sync.vault_test_env              import Vault__Test_Env


class Test_Vault__Sync__Commit_Message_Length:

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_single_vault(files={'a.txt': 'a'})

    def setup_method(self):
        self.env  = self._env.restore()
        self.sync = self.env.sync
        self.dir  = self.env.vault_dir
        self.n    = 0

    def teardown_method(self):
        self.env.cleanup()

    def change(self):
        self.n += 1
        with open(os.path.join(self.dir, 'a.txt'), 'w') as f:
            f.write(f'change {self.n}')

    def objects(self):
        return sorted(os.listdir(os.path.join(self.dir, '.sg_vault', 'bare', 'data')))

    def index(self):
        c = self.sync._init_components(self.dir)
        return c.branch_manager.load_branch_index(self.dir, c.branch_index_file_id, c.read_key)

    # --- the default limit --------------------------------------------------------

    def test_740_bytes_commit_and_741_are_refused_before_anything_is_written(self):
        self.change()
        self.sync.commit(self.dir, message='x' * SHORT_MESSAGE_BYTES)
        self.change()
        head, objects = self.sync.resolve_revision(self.dir, 'HEAD'), self.objects()
        with pytest.raises(Vault__Commit_Message_Too_Long_Error) as error:
            self.sync.commit(self.dir, message='x' * (SHORT_MESSAGE_BYTES + 1))
        assert 'is 741 bytes (UTF-8) and this vault takes up to 740' in str(error.value)
        assert 'sgit vault format --feature long-messages' in str(error.value)
        assert self.sync.resolve_revision(self.dir, 'HEAD') == head
        assert self.objects() == objects                                   # no blob, no tree

    def test_the_limit_is_in_bytes(self):
        self.change()
        with pytest.raises(Vault__Commit_Message_Too_Long_Error) as error:
            self.sync.commit(self.dir, message='é' * 371)                  # 742 bytes, 371 characters
        assert error.value.size == 742

    def test_write_is_limited_the_same_way(self):
        with pytest.raises(Vault__Commit_Message_Too_Long_Error):
            self.sync.write_file(self.dir, 'b.txt', b'b', message='y' * 800)

    def test_the_cli_prints_it_as_a_refusal(self, capsys):
        cli = CLI__Main()
        try:
            cli._print_friendly_error(Vault__Commit_Message_Too_Long_Error(900, 740, True),
                                      cli.build_parser().parse_args(['commit', '-d', self.dir]))
        finally:
            err = capsys.readouterr().err
        assert err.startswith('error: the commit message is 900 bytes')
        assert '  at ' not in err                                         # a refusal, not a crash

    # --- long-messages --------------------------------------------------------------

    def test_the_feature_raises_the_gate_and_takes_64_kib(self):
        self.sync.set_format(self.dir, add_features=[FEATURE_LONG_MESSAGES])
        index = self.index()
        assert Vault__Format().has_feature(index, FEATURE_LONG_MESSAGES)
        assert Vault__Format().min_client_of(index) == LONG_MESSAGES_MIN_CLIENT
        self.change()
        long_text = 'Subject line\n\n' + ('body text ' * 7000)[:LONG_MESSAGE_BYTES - 14]
        result = self.sync.commit(self.dir, message=long_text)
        assert len(long_text.encode()) == LONG_MESSAGE_BYTES
        c      = self.sync._init_components(self.dir)
        vc     = Vault__Commit(crypto=self.env.crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
        commit = vc.load_commit(result['commit_id'], c.read_key)
        assert self.env.crypto.decrypt_metadata(c.read_key, str(commit.message_enc)) == long_text
        self.change()
        with pytest.raises(Vault__Commit_Message_Too_Long_Error) as error:
            self.sync.commit(self.dir, message='x' * (LONG_MESSAGE_BYTES + 1))
        assert str(error.value).endswith('Shorten it.')

    def test_an_older_client_is_told_to_update_and_this_build_is_not(self):
        self.sync.set_format(self.dir, add_features=[FEATURE_LONG_MESSAGES])
        index = self.index()
        with pytest.raises(Vault__Client_Too_Old_Error) as error:
            Vault__Format().check_client(index, client_version='0.26.3')
        assert 'needs sgit-ai >= 0.26.4' in str(error.value)
        Vault__Format().check_client(index, client_version='0.26.4')
        Vault__Format().check_client(index)                                  # this build carries the feature

    def test_the_gate_is_never_lowered(self):
        self.sync.set_format(self.dir, min_client='0.0.1')
        self.sync.set_format(self.dir, add_features=[FEATURE_LONG_MESSAGES])
        assert Vault__Format().min_client_of(self.index()) == LONG_MESSAGES_MIN_CLIENT


class Test_Vault__Commit_Message_Read_Tolerance:
    """A longer message written by another client (the web UI has no cap) loads."""

    def test_a_2000_byte_message_from_another_client_loads(self):
        env = Vault__Test_Env()
        env.setup_single_vault(files={'a.txt': 'a'})
        s   = env.restore()
        try:
            c         = s.sync._init_components(s.vault_dir)
            vc        = Vault__Commit(crypto=s.crypto, pki=c.pki, object_store=c.obj_store, ref_manager=c.ref_manager)
            head      = vc.load_commit(s.commit_id, c.read_key)
            text      = 'w' * 2000
            commit_id = vc.create_commit(read_key=c.read_key, tree_id=str(head.tree_id), parent_ids=[s.commit_id],
                                         message_enc=s.crypto.encrypt_metadata(c.read_key, text))   # as another writer would
            loaded    = vc.load_commit(commit_id, c.read_key)
            assert len(str(loaded.message_enc)) > 1024
            assert s.crypto.decrypt_metadata(c.read_key, str(loaded.message_enc)) == text
            assert Schema__Object_Commit.from_json(loaded.json()).json() == loaded.json()
        finally:
            s.cleanup()
            env.cleanup_snapshot()

    def test_the_default_vault_commit_refuses_a_long_plain_message(self):
        vc = Vault__Commit()
        with pytest.raises(Vault__Commit_Message_Too_Long_Error):
            vc.create_commit(read_key=bytes(32), tree_id='obj-cas-imm-aaaaaaaaaaaa', message='m' * 741)
