"""Tests for Step__Clone__ReadOnly__Setup_Config (architect contract §3 / §7.1).

The read-only clone setup step MUST now write BOTH clone_mode.json AND config.json
(mode=READ_ONLY, my_branch_id=None, sparse carried through, branch_name recorded),
and write NEITHER a vault_key file NOR a clone-branch ref.
"""
import json
import os
import tempfile
import shutil

import pytest

from sgit_ai.storage.Vault__Storage                          import Vault__Storage
from sgit_ai.schemas.workflow.clone.Schema__Clone__State     import Schema__Clone__State
from sgit_ai.schemas.Schema__Clone_Mode                      import Schema__Clone_Mode
from sgit_ai.schemas.Schema__Local_Config                    import Schema__Local_Config
from sgit_ai.safe_types.Safe_Str__File_Path                  import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Vault_Id                   import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__Read_Key                   import Safe_Str__Read_Key
from sgit_ai.safe_types.Enum__Clone_Mode                     import Enum__Clone_Mode
from sgit_ai.safe_types.Enum__Local_Config_Mode              import Enum__Local_Config_Mode
from sgit_ai.workflow.clone.Step__Clone__ReadOnly__Setup_Config import Step__Clone__ReadOnly__Setup_Config


VAULT_ID     = 'rosetupvlt01'
READ_KEY_HEX = 'b' * 64


class _Workspace:
    """Minimal clone workspace exposing only what the setup step touches."""

    def __init__(self):
        self.storage = Vault__Storage()

    def progress(self, tag, msg):
        pass


class Test_Step__Clone__ReadOnly__Setup_Config:

    def setup_method(self):
        self.tmp       = tempfile.mkdtemp(prefix='ro_setup_')
        self.directory = os.path.join(self.tmp, 'cloned')
        os.makedirs(os.path.join(self.directory, '.sg_vault', 'local'), exist_ok=True)
        self.storage   = Vault__Storage()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, sparse=False):
        state = Schema__Clone__State(
            directory    = Safe_Str__File_Path(self.directory),
            vault_id     = Safe_Str__Vault_Id(VAULT_ID),
            read_key_hex = Safe_Str__Read_Key(READ_KEY_HEX),
            sparse       = sparse,
        )
        Step__Clone__ReadOnly__Setup_Config().execute(state, _Workspace())

    # -- clone_mode.json ----------------------------------------------------

    def test_clone_mode_json_written(self):
        self._run()
        path = self.storage.clone_mode_path(self.directory)
        assert os.path.isfile(path)
        cm = Schema__Clone_Mode.from_json(json.load(open(path)))
        assert cm.mode             == Enum__Clone_Mode.READ_ONLY
        assert str(cm.vault_id)    == VAULT_ID
        assert str(cm.read_key)    == READ_KEY_HEX

    def test_clone_mode_records_branch_name(self):
        """Q7: the tracked branch name is recorded in clone_mode.json."""
        self._run()
        cm = Schema__Clone_Mode.from_json(json.load(open(self.storage.clone_mode_path(self.directory))))
        assert str(cm.branch_name) == 'current'

    # -- config.json (the new behaviour) ------------------------------------

    def test_config_json_is_written(self):
        self._run()
        path = self.storage.local_config_path(self.directory)
        assert os.path.isfile(path), 'config.json MUST be written for RO clones (§3.3)'

    def test_config_json_mode_is_read_only(self):
        self._run()
        cfg = Schema__Local_Config.from_json(json.load(open(self.storage.local_config_path(self.directory))))
        assert cfg.mode == Enum__Local_Config_Mode.READ_ONLY

    def test_config_json_my_branch_id_is_none(self):
        self._run()
        cfg = Schema__Local_Config.from_json(json.load(open(self.storage.local_config_path(self.directory))))
        assert cfg.my_branch_id is None
        assert cfg.edit_token   is None

    def test_config_json_carries_sparse_false(self):
        self._run(sparse=False)
        cfg = Schema__Local_Config.from_json(json.load(open(self.storage.local_config_path(self.directory))))
        assert cfg.sparse is False

    def test_config_json_carries_sparse_true(self):
        self._run(sparse=True)
        cfg = Schema__Local_Config.from_json(json.load(open(self.storage.local_config_path(self.directory))))
        assert cfg.sparse is True

    # -- guard rails: vault_key and clone-branch ref absent -----------------

    def test_no_vault_key_file_written(self):
        self._run()
        assert not os.path.isfile(self.storage.vault_key_path(self.directory))

    def test_no_clone_branch_ref_written(self):
        """RO clones have no clone branch; the setup step writes no refs at all."""
        self._run()
        refs_dir = os.path.join(self.directory, '.sg_vault', 'bare', 'refs')
        # The setup step creates neither the refs dir nor any ref inside it.
        if os.path.isdir(refs_dir):
            assert os.listdir(refs_dir) == []
        else:
            assert not os.path.isdir(refs_dir)
