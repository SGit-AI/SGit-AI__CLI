"""Step__Restore__Extract_Bare — the zip's bare store lands under <destination>/.sg_vault/."""
import os
import zipfile

import pytest

from tests.unit.workflow.backup.steps.backup_steps_env              import Backup_Steps_Base
from sgit_ai.workflow.backup.steps.Step__Restore__Extract_Bare     import Step__Restore__Extract_Bare


class Test_Step__Restore__Extract_Bare(Backup_Steps_Base):

    def test_the_step_extracts_the_store_then_fails_building_its_output(self):
        """Pins what the code does today: Vault__Restore._extract_bare returns (sg_dir, the
        list of extracted names) and the step stores that list as `vault_id`, which
        Safe_Str__Vault_Id rejects (too long / not an id). So on a real backup the files are
        extracted (key and manifest excluded) and the step then raises ValueError instead of
        returning a state. The live restore path (Vault__Restore.restore) does not use it."""
        r = self.make_zip(include_key=True)
        with pytest.raises(ValueError, match='Safe_Str__Vault_Id'):
            Step__Restore__Extract_Bare().execute(self.state(zip_path=r['zip_path'], destination=self.dest()), self.ws)
        sg_dir = os.path.join(self.dest(), '.sg_vault')
        assert os.path.isdir(os.path.join(sg_dir, 'bare', 'data'))
        assert not os.path.exists(os.path.join(sg_dir, 'VAULT-KEY'))
        assert not os.path.exists(os.path.join(sg_dir, 'manifest.json'))
        with zipfile.ZipFile(r['zip_path']) as zf:
            names = [n for n in zf.namelist() if n not in ('VAULT-KEY', 'manifest.json') and not n.endswith('/')]
        assert names
        for name in names:
            assert os.path.isfile(os.path.join(sg_dir, name)), name
