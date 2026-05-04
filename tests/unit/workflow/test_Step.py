"""Tests for Step base class."""
import pytest

from sgit_ai.workflow.Step                             import Step
from sgit_ai.safe_types.Safe_Str__Step_Name            import Safe_Str__Step_Name
from osbot_utils.type_safe.Type_Safe                   import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str    import Safe_Str


class Schema__In(Type_Safe):
    value : Safe_Str = None

class Schema__Out(Type_Safe):
    result : Safe_Str = None


class _TestStep(Step):
    name          = Safe_Str__Step_Name('test-step')
    input_schema  = Schema__In
    output_schema = Schema__Out

    def execute(self, input, workspace):
        return Schema__Out(result='done')


class Test_Step:

    def test_step_name_from_field(self):
        s = _TestStep()
        assert s.step_name() == 'test-step'

    def test_step_name_from_class_when_none(self):
        class NamelessStep(Step):
            name = None
        s = NamelessStep()
        assert s.step_name() == 'NamelessStep'

    def test_execute_raises_not_implemented_in_base(self):
        s = Step()
        with pytest.raises(NotImplementedError):
            s.execute(None, None)

    def test_validate_input_passes_by_default(self):
        s = _TestStep()
        s.validate_input(Schema__In())  # no exception

    def test_validate_output_passes_by_default(self):
        s = _TestStep()
        s.validate_output(Schema__Out())  # no exception

    def test_is_done_delegates_to_workspace(self):
        class FakeWorkspace:
            def has_output_for(self, step):
                return True
        s = _TestStep()
        assert s.is_done(FakeWorkspace()) is True

    def test_is_done_false_when_workspace_says_no(self):
        class FakeWorkspace:
            def has_output_for(self, step):
                return False
        s = _TestStep()
        assert s.is_done(FakeWorkspace()) is False

    def test_execute_returns_output_schema(self):
        class FakeWorkspace:
            def has_output_for(self, step): return False
        s = _TestStep()
        out = s.execute(Schema__In(), FakeWorkspace())
        assert isinstance(out, Schema__Out)
        assert out.result == 'done'
