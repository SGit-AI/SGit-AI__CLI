"""Shared setup for the backup/restore step tests: one real vault (Vault__Test_Env), a
backup zip of it with and without the key, and a Restore__State builder."""
import os
import tempfile

from tests._helpers.vault_test_env                              import Vault__Test_Env
from sgit_ai.core.actions.backup.Vault__Backup                  import Vault__Backup
from sgit_ai.safe_types.Safe_Str__File_Path                     import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Restore_Mode                  import Safe_Str__Restore_Mode
from sgit_ai.safe_types.Safe_Str__Vault_Key                     import Safe_Str__Vault_Key
from sgit_ai.schemas.workflow.backup.Schema__Restore__State     import Schema__Restore__State
from sgit_ai.workflow.backup.Restore__Workspace                 import Restore__Workspace

FILES = {'hello.txt': 'hello world\n', 'sub/data.txt': 'data content'}


class Backup_Steps_Base:
    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env(); cls._env.setup_single_vault(files=FILES)

    @classmethod
    def teardown_class(cls):
        if cls._env: cls._env.cleanup_snapshot()

    def setup_method(self):
        self.env   = self._env.restore(); self.vault = self.env.vault_dir
        self.out   = tempfile.mkdtemp(prefix='backup_steps_')
        self.ws    = Restore__Workspace()

    def teardown_method(self):
        import shutil
        self.env.cleanup(); shutil.rmtree(self.out, ignore_errors=True)

    def make_zip(self, include_key: bool = False, label: str = 'steps') -> dict:
        return Vault__Backup().backup(self.vault, output_dir=self.out, label=label, include_key=include_key)

    def dest(self, name: str = 'restored') -> str:
        return os.path.join(self.out, name)

    def state(self, **fields) -> Schema__Restore__State:
        kwargs = {}
        for key, value in fields.items():
            if value is None:
                continue
            kwargs[key] = {'mode': Safe_Str__Restore_Mode, 'vault_key': Safe_Str__Vault_Key}.get(key, Safe_Str__File_Path)(value)
        return Schema__Restore__State(**kwargs)
