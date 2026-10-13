"""Step__Backup__Build_Zip — the backup workflow's one step, over a real vault."""
import os

from tests.unit.workflow.backup.steps.backup_steps_env              import Backup_Steps_Base
from sgit_ai.safe_types.Safe_Str__Backup_Label                      import Safe_Str__Backup_Label
from sgit_ai.safe_types.Safe_Str__File_Path                         import Safe_Str__File_Path
from sgit_ai.schemas.workflow.backup.Schema__Backup__State          import Schema__Backup__State
from sgit_ai.workflow.backup.steps.Step__Backup__Build_Zip          import Step__Backup__Build_Zip


class Test_Step__Backup__Build_Zip(Backup_Steps_Base):

    def test_builds_the_zip_and_fills_the_state(self):
        """directory/output_dir/label/includes_key are carried through; vault_id, zip_path,
        sha256, byte_size and object_count come from Vault__Backup; the zip is at zip_path
        with its .sha256 sidecar."""
        state = Schema__Backup__State(directory=Safe_Str__File_Path(self.vault), output_dir=Safe_Str__File_Path(self.out),
                                      label=Safe_Str__Backup_Label('nightly'), includes_key=False)
        out = Step__Backup__Build_Zip().execute(state, self.ws)
        keys = self.env.crypto.derive_keys_from_vault_key(self.env.vault_key)
        assert str(out.vault_id) == keys['vault_id']
        assert str(out.directory) == self.vault and str(out.output_dir) == self.out and str(out.label) == 'nightly'
        assert out.includes_key is False
        assert os.path.isfile(str(out.zip_path)) and os.path.dirname(str(out.zip_path)) == self.out
        assert 'nightly' in os.path.basename(str(out.zip_path))
        assert os.path.getsize(str(out.zip_path)) == int(out.byte_size) > 0
        assert int(out.object_count) > 0
        with open(str(out.zip_path) + '.sha256') as f:
            assert f.read().strip() == str(out.sha256)

    def test_defaults_when_output_dir_and_label_are_unset(self):
        """No output_dir: the zip lands in the vault's own .sg_vault/backups/; no label: 'manual'."""
        state = Schema__Backup__State(directory=Safe_Str__File_Path(self.vault))
        out   = Step__Backup__Build_Zip().execute(state, self.ws)
        assert os.path.dirname(str(out.zip_path)) == os.path.join(self.vault, '.sg_vault', 'backups')
        assert 'manual' in os.path.basename(str(out.zip_path))
        assert out.output_dir is None and out.label is None

    def test_includes_key_puts_the_vault_key_in_the_zip(self):
        import zipfile
        state = Schema__Backup__State(directory=Safe_Str__File_Path(self.vault), output_dir=Safe_Str__File_Path(self.out),
                                      includes_key=True)
        out = Step__Backup__Build_Zip().execute(state, self.ws)
        assert out.includes_key is True
        with zipfile.ZipFile(str(out.zip_path)) as zf:
            assert 'VAULT-KEY' in zf.namelist()
