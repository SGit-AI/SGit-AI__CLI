"""Workflow — base class for an ordered sequence of Steps."""
from osbot_utils.type_safe.Type_Safe            import Type_Safe
from sgit_ai.safe_types.Safe_Str__Workflow_Name import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver        import Safe_Str__Semver
from sgit_ai.workflow.Step                      import Step


class Workflow(Type_Safe):
    """Base class. Subclasses declare name, version, and the ordered step list."""

    name    : Safe_Str__Workflow_Name = None
    version : Safe_Str__Semver        = None
    steps   = None   # list of Step subclasses (not instances); plain attr to avoid Type_Safe mutable-list rejection

    def workflow_name(self) -> str:
        if self.name is not None:
            return str(self.name)
        return self.__class__.__name__

    def workflow_version(self) -> str:
        if self.version is not None:
            return str(self.version)
        return '1.0.0'

    def step_classes(self) -> list:
        return self.steps or []

    def execute(self, input: Type_Safe, workspace: 'Workflow__Workspace') -> dict:
        """Run all steps in order, skipping already-completed ones."""
        for idx, step_class in enumerate(self.step_classes(), start=1):
            step = step_class()
            if step.is_done(workspace):
                continue
            step_input = workspace.gather_input_for(step)
            step.validate_input(step_input)
            output = step.execute(step_input, workspace)
            step.validate_output(output)
            workspace.persist_output(step, output, index=idx)
        return workspace.final_output()
