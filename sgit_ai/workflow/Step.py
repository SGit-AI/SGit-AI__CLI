"""Step — base class for a single idempotent workflow step."""
from osbot_utils.type_safe.Type_Safe        import Type_Safe
from sgit_ai.safe_types.Safe_Str__Step_Name import Safe_Str__Step_Name


class Step(Type_Safe):
    """Base class. Subclasses declare input_schema / output_schema and implement execute()."""

    name          : Safe_Str__Step_Name = None
    input_schema  : type = None    # Type_Safe subclass (class, not instance)
    output_schema : type = None    # Type_Safe subclass (class, not instance)

    def execute(self, input: Type_Safe, workspace: 'Workflow__Workspace') -> Type_Safe:
        """Run the step. Return an instance of output_schema."""
        raise NotImplementedError(f'{self.__class__.__name__}.execute() not implemented')

    def is_done(self, workspace: 'Workflow__Workspace') -> bool:
        """Return True if this step's output already exists in the workspace."""
        return workspace.has_output_for(self)

    def validate_input(self, input: Type_Safe) -> None:
        """Raise ValueError if input is invalid. Default: pass."""

    def validate_output(self, output: Type_Safe) -> None:
        """Raise ValueError if output is invalid. Default: pass."""

    def step_name(self) -> str:
        """Return the step name as a plain string."""
        n = self.name
        if n is not None:
            return str(n)
        return self.__class__.__name__
