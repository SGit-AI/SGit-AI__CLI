"""Step__Restore__Verify_Zip_Integrity — the zip's sha256 against its sidecar."""
import hashlib
import os

import pytest

from tests.unit.workflow.backup.steps.backup_steps_env                      import Backup_Steps_Base
from sgit_ai.workflow.backup.steps.Step__Restore__Verify_Zip_Integrity     import Step__Restore__Verify_Zip_Integrity


class Test_Step__Restore__Verify_Zip_Integrity(Backup_Steps_Base):

    def test_records_the_sha256_that_matches_the_sidecar(self):
        r   = self.make_zip()
        out = Step__Restore__Verify_Zip_Integrity().execute(self.state(zip_path=r['zip_path'], destination=self.dest()), self.ws)
        with open(r['zip_path'], 'rb') as f:
            assert str(out.sha256) == hashlib.sha256(f.read()).hexdigest() == r['sha256']

    def test_without_a_sidecar_the_hash_is_recorded_unchecked(self):
        r = self.make_zip(); os.remove(r['zip_path'] + '.sha256')
        out = Step__Restore__Verify_Zip_Integrity().execute(self.state(zip_path=r['zip_path'], destination=self.dest()), self.ws)
        assert str(out.sha256) == r['sha256']

    def test_a_sidecar_that_disagrees_fails_the_step(self):
        r = self.make_zip()
        with open(r['zip_path'] + '.sha256', 'w') as f:
            f.write('0' * 64)
        with pytest.raises(RuntimeError, match='Integrity check failed'):
            Step__Restore__Verify_Zip_Integrity().execute(self.state(zip_path=r['zip_path'], destination=self.dest()), self.ws)
