"""Step__Restore__Validate_Destination — resolves the zip source and refuses bad destinations."""
import os

import pytest

from tests.unit.workflow.backup.steps.backup_steps_env                      import Backup_Steps_Base
from sgit_ai.core.actions.backup.Vault__Restore                            import Vault__Restore
from sgit_ai.workflow.backup.steps.Step__Restore__Validate_Destination     import Step__Restore__Validate_Destination


class Test_Step__Restore__Validate_Destination(Backup_Steps_Base):

    def test_resolves_a_zip_path_into_the_state(self):
        zip_path = self.make_zip()['zip_path']
        out = Step__Restore__Validate_Destination().execute(self.state(zip_source=zip_path, destination=self.dest()), self.ws)
        assert str(out.zip_path) == os.path.abspath(zip_path)
        assert str(out.zip_source) == zip_path and str(out.destination) == self.dest()

    def test_the_vault_colon_backup_id_form_cannot_pass_through_the_state(self):
        """Pins what the code does today: Vault__Restore._resolve_source understands
        `<vault-dir>:<backup-id>`, but Safe_Str__File_Path (zip_source) strips the colon, so
        by the time the step reads it the source is `<vault-dir><backup-id>` and the step
        fails with 'Backup zip not found'. Vault__Restore.restore (the live path) resolves it."""
        from sgit_ai.core.actions.backup.Vault__Backup import Vault__Backup
        result    = Vault__Backup().backup(self.vault, label='named')
        backup_id = os.path.basename(result['zip_path'])[:-len('.zip')]
        assert Vault__Restore()._resolve_source(f'{self.vault}:{backup_id}') == result['zip_path']
        state = self.state(zip_source=f'{self.vault}:{backup_id}', destination=self.dest())
        assert ':' not in str(state.zip_source)
        with pytest.raises(RuntimeError, match='Backup zip not found'):
            Step__Restore__Validate_Destination().execute(state, self.ws)

    def test_non_empty_destination_is_refused(self):
        zip_path = self.make_zip()['zip_path']
        os.makedirs(self.dest()); open(os.path.join(self.dest(), 'x'), 'w').close()
        with pytest.raises(RuntimeError, match='Destination is not empty'):
            Step__Restore__Validate_Destination().execute(self.state(zip_source=zip_path, destination=self.dest()), self.ws)

    def test_destination_inside_an_existing_vault_is_refused(self):
        zip_path = self.make_zip()['zip_path']
        inside   = os.path.join(self.vault, 'nested', 'restore')
        with pytest.raises(RuntimeError, match='Cannot restore inside an existing vault'):
            Step__Restore__Validate_Destination().execute(self.state(zip_source=zip_path, destination=inside), self.ws)

    def test_missing_zip_source_is_refused(self):
        with pytest.raises(RuntimeError):
            Step__Restore__Validate_Destination().execute(self.state(zip_source=os.path.join(self.out, 'nope.zip'), destination=self.dest()), self.ws)
