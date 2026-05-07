"""Workflow__Vault_Restore — 5-step restore pipeline."""
from sgit_ai.safe_types.Safe_Str__Workflow_Name                            import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver                                   import Safe_Str__Semver
from sgit_ai.workflow.Workflow                                             import Workflow
from sgit_ai.workflow.backup.steps.Step__Restore__Validate_Destination    import Step__Restore__Validate_Destination
from sgit_ai.workflow.backup.steps.Step__Restore__Verify_Zip_Integrity    import Step__Restore__Verify_Zip_Integrity
from sgit_ai.workflow.backup.steps.Step__Restore__Extract_Bare             import Step__Restore__Extract_Bare
from sgit_ai.workflow.backup.steps.Step__Restore__Resolve_Vault_Key        import Step__Restore__Resolve_Vault_Key
from sgit_ai.workflow.backup.steps.Step__Restore__Extract_Working_Copy     import Step__Restore__Extract_Working_Copy
from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow                       import register_workflow


@register_workflow
class Workflow__Vault_Restore(Workflow):
    """5-step restore workflow: validate_destination → verify_zip_integrity →
    extract_bare → resolve_vault_key → extract_working_copy."""
    name    = Safe_Str__Workflow_Name('restore')
    version = Safe_Str__Semver('1.0.0')
    steps   = [
        Step__Restore__Validate_Destination,
        Step__Restore__Verify_Zip_Integrity,
        Step__Restore__Extract_Bare,
        Step__Restore__Resolve_Vault_Key,
        Step__Restore__Extract_Working_Copy,
    ]
