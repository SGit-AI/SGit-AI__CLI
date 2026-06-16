"""Tests for the disabled Step__Transfer__Init_Vault.

This step previously generated a NEW Simple Token via Simple_Token__Wordlist
and called Vault__Sync.init(token=new_token). It is the covert create-path the
architect flagged as F2 in
team/explorer/architect/reviews/06/13/v0__architect-review__cli-simple-token-disablement.md
— reached when a user runs `sgit clone <simple-token>` and the token is NOT
found as a SGit-AI vault but IS found as a SG/Send transfer.

The step's execute() now raises a clear "disabled pending security rework"
error before any token generation, blob download, or filesystem write.
"""
import pytest

from sgit_ai.workflow.clone.Step__Transfer__Init_Vault          import Step__Transfer__Init_Vault
from sgit_ai.workflow.clone.Workflow__Clone__Transfer           import Workflow__Clone__Transfer


class Test_Step__Transfer__Init_Vault__Disabled:

    def test_execute_raises_disabled_message(self):
        step = Step__Transfer__Init_Vault()
        with pytest.raises(RuntimeError) as exc:
            step.execute(input=None, workspace=None)
        msg = str(exc.value)
        assert 'sgit clone <simple-token>' in msg
        assert 'disabled'                  in msg
        assert 'Simple Token'              in msg
        assert 'backend'                   in msg.lower()

    def test_execute_does_not_call_wordlist_generate(self, monkeypatch):
        """The gate must fire BEFORE Simple_Token__Wordlist.generate() — otherwise
        a token is minted in memory even if it isn't persisted, which the rework
        is trying to avoid."""
        from sgit_ai.crypto.simple_token.Simple_Token__Wordlist import Simple_Token__Wordlist
        calls = {'count': 0}

        def fake_generate(self):
            calls['count'] += 1
            return 'should-not-be-used-0000'

        monkeypatch.setattr(Simple_Token__Wordlist, 'generate', fake_generate)

        step = Step__Transfer__Init_Vault()
        with pytest.raises(RuntimeError):
            step.execute(input=None, workspace=None)
        assert calls['count'] == 0

    def test_step_remains_registered_in_workflow(self):
        """The step is DISABLED at execute() — not removed from the workflow.
        Pinning this so the rework can re-enable in place without touching the
        Workflow__Clone__Transfer wiring."""
        classes = Workflow__Clone__Transfer().step_classes()
        assert Step__Transfer__Init_Vault in classes
