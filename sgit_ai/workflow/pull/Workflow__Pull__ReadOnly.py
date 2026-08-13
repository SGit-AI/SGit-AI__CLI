"""Workflow__Pull__ReadOnly — 4-step read-only pull pipeline (no merge).

Redefined `pull` for read-only clones (architect contract §5.3, Q2 ratified):
"re-fetch the named-branch HEAD from the server, download missing
commits/trees/blobs, re-checkout the working copy at the new HEAD — no merge,
no commit creation, no clone-branch ref write."

Steps:
    derive_keys          (reused — clone-mode-aware via §4.1)
    ro-load-named-head   (NEW — fetch named HEAD ref, no clone-branch lookup)
    fetch-missing        (reused — stop_at = previously-cached named HEAD)
    ro-checkout          (NEW — straight checkout of the named HEAD; no merge)

Every server interaction on this path is an api.read(...) only — never
api.write(...) — so a read-only clone stays genuinely read-only against the
server (zero-knowledge guarantee).
"""
from sgit_ai.safe_types.Safe_Str__Workflow_Name                    import Safe_Str__Workflow_Name
from sgit_ai.safe_types.Safe_Str__Semver                           import Safe_Str__Semver
from sgit_ai.workflow.Workflow                                      import Workflow
from sgit_ai.workflow.pull.Step__Pull__Derive_Keys                 import Step__Pull__Derive_Keys
from sgit_ai.workflow.pull.Step__Pull__RO__Load_Named_Head         import Step__Pull__RO__Load_Named_Head
from sgit_ai.workflow.pull.Step__Pull__Fetch_Missing               import Step__Pull__Fetch_Missing
from sgit_ai.workflow.pull.Step__Pull__RO__Checkout                import Step__Pull__RO__Checkout
from sgit_ai.plugins.dev.workflow.CLI__Dev__Workflow               import register_workflow


@register_workflow
class Workflow__Pull__ReadOnly(Workflow):
    """4-step read-only pull: derive_keys → ro-load-named-head → fetch-missing → ro-checkout."""
    name    = Safe_Str__Workflow_Name('pull-read-only')
    version = Safe_Str__Semver('1.0.0')
    steps   = [
        Step__Pull__Derive_Keys,
        Step__Pull__RO__Load_Named_Head,
        Step__Pull__Fetch_Missing,
        Step__Pull__RO__Checkout,
    ]
