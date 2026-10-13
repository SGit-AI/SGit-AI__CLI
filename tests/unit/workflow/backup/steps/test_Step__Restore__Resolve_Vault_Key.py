"""Step__Restore__Resolve_Vault_Key — where the key for an expanded restore comes from:
the state, the zip (--include-key backups), or the workspace prompt; bare mode needs none."""
import pytest

from tests.unit.workflow.backup.steps.backup_steps_env                  import Backup_Steps_Base
from sgit_ai.workflow.backup.Restore__Workspace                         import Restore__Workspace
from sgit_ai.workflow.backup.steps.Step__Restore__Resolve_Vault_Key    import Step__Restore__Resolve_Vault_Key


class Test_Step__Restore__Resolve_Vault_Key(Backup_Steps_Base):

    def test_bare_mode_returns_the_input_untouched(self):
        r     = self.make_zip()
        state = self.state(zip_path=r['zip_path'], destination=self.dest(), mode='bare')
        assert Step__Restore__Resolve_Vault_Key().execute(state, self.ws) is state
        assert state.vault_key is None

    def test_a_key_in_the_state_is_kept(self):
        r   = self.make_zip(include_key=True)
        out = Step__Restore__Resolve_Vault_Key().execute(self.state(zip_path=r['zip_path'], destination=self.dest(),
                                                                    vault_key=self.env.vault_key), self.ws)
        assert str(out.vault_key) == self.env.vault_key

    def test_the_key_is_read_from_a_zip_that_carries_it(self):
        r   = self.make_zip(include_key=True)
        out = Step__Restore__Resolve_Vault_Key().execute(self.state(zip_path=r['zip_path'], destination=self.dest()), self.ws)
        assert str(out.vault_key) == self.env.vault_key
        assert out.mode is None                                            # mode unset reads as expanded

    def test_without_a_key_anywhere_and_no_prompt_the_step_fails(self):
        r = self.make_zip()
        with pytest.raises(RuntimeError, match='Vault key required for expanded restore'):
            Step__Restore__Resolve_Vault_Key().execute(self.state(zip_path=r['zip_path'], destination=self.dest(), mode='expanded'), self.ws)

    def test_the_prompt_is_asked_only_when_nothing_else_has_the_key(self):
        r     = self.make_zip()
        asked = []
        ws    = Restore__Workspace(vault_key_prompt_fn=lambda: asked.append(1) or self.env.vault_key)
        out   = Step__Restore__Resolve_Vault_Key().execute(self.state(zip_path=r['zip_path'], destination=self.dest()), ws)
        assert str(out.vault_key) == self.env.vault_key and asked == [1]
        keyed = self.make_zip(include_key=True, label='keyed')
        Step__Restore__Resolve_Vault_Key().execute(self.state(zip_path=keyed['zip_path'], destination=self.dest()), ws)
        assert asked == [1]

    def test_an_empty_answer_from_the_prompt_re_raises_the_original_error(self):
        r  = self.make_zip()
        ws = Restore__Workspace(vault_key_prompt_fn=lambda: '')
        with pytest.raises(RuntimeError, match='Vault key required for expanded restore'):
            Step__Restore__Resolve_Vault_Key().execute(self.state(zip_path=r['zip_path'], destination=self.dest()), ws)
