"""Step__Restore__Extract_Working_Copy — checks the working copy out of the restored bare
store (expanded) or skips it (bare)."""
import os

import pytest

from tests.unit.workflow.backup.steps.backup_steps_env                      import Backup_Steps_Base, FILES
from sgit_ai.core.actions.backup.Vault__Restore                            import Vault__Restore
from sgit_ai.workflow.backup.steps.Step__Restore__Extract_Working_Copy     import Step__Restore__Extract_Working_Copy


class Test_Step__Restore__Extract_Working_Copy(Backup_Steps_Base):

    def _extracted(self, include_key=False):
        """The state Step__Restore__Extract_Bare would hand over if it could (see its test):
        the bare store extracted by Vault__Restore._extract_bare and sg_dir recorded."""
        r = self.make_zip(include_key=include_key)
        sg_dir, _names = Vault__Restore()._extract_bare(r['zip_path'], self.dest())
        return self.state(zip_path=r['zip_path'], destination=self.dest(), sg_dir=sg_dir)

    def test_bare_mode_skips_the_checkout_and_records_zero_time(self):
        bare = self._extracted()
        data = bare.json(); data['mode'] = 'bare'
        out  = Step__Restore__Extract_Working_Copy().execute(type(bare).from_json(data), self.ws)
        assert int(out.t_checkout_ms) == 0
        assert not os.path.exists(os.path.join(self.dest(), 'hello.txt'))

    def test_expanded_mode_writes_the_files_then_fails_building_its_output(self):
        """Pins what the code does today: Vault__Restore._extract_working_copy returns the
        list of working files, and the step stores that list as `t_checkout_ms`
        (Safe_UInt__Timestamp), which raises TypeError. The working copy is fully written
        before that. The live restore path (Vault__Restore.restore) does not use this step."""
        bare = self._extracted()
        data = bare.json(); data['vault_key'] = self.env.vault_key
        with pytest.raises(TypeError, match='Safe_UInt__Timestamp requires an integer value, got list'):
            Step__Restore__Extract_Working_Copy().execute(type(bare).from_json(data), self.ws)
        for rel, content in FILES.items():
            with open(os.path.join(self.dest(), rel)) as f:
                assert f.read() == content

    def test_expanded_mode_without_a_key_fails(self):
        """Pins what the code does today: mode unset and no key is an expanded restore with
        vault_key None, and the checkout raises rather than falling back to bare."""
        bare = self._extracted()
        with pytest.raises(Exception):
            Step__Restore__Extract_Working_Copy().execute(bare, self.ws)
