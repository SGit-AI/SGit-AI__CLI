from sgit_ai.workflow.Workflow__Workspace import Workflow__Workspace


class Move__Workspace(Workflow__Workspace):
    api = None   # injected by tests; steps prefer this over creating a real Vault__API
