"""Workflow__Clone__Headless — credentials-only clone: keys derived, config written, no data."""
from sgit_ai.safe_types.Safe_Str__Workflow_Name                        import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver                               import Safe_Str__Semver
from sgit_ai.workflow.Workflow                                          import Workflow
from sgit_ai.workflow.clone.Step__Clone__Derive_Keys                    import Step__Clone__Derive_Keys
from sgit_ai.workflow.clone.Step__Clone__Headless__Setup_Config         import Step__Clone__Headless__Setup_Config
from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow                    import register_workflow


@register_workflow
class Workflow__Clone__Headless(Workflow):
    """Derive keys and write local config only — no bare/ directory, no object downloads."""
    name    = Safe_Str__Workflow_Name('clone-headless')
    version = Safe_Str__Semver('1.0.0')
    steps   = [
        Step__Clone__Derive_Keys,
        Step__Clone__Headless__Setup_Config,
    ]
