from sgit_ai.plugins._base.Plugin__Read_Only          import Plugin__Read_Only
from sgit_ai.plugins._base.Schema__Plugin_Manifest    import Schema__Plugin_Manifest
from sgit_ai.plugins.history.CLI__History              import CLI__History


class Plugin__History(Plugin__Read_Only):
    manifest : Schema__Plugin_Manifest

    def register_subparsers(self, parent_parser, context: dict):
        ns           = CLI__History()
        ns.vault     = context.get('vault')
        ns.diff      = context.get('diff')
        ns.revert    = context.get('revert')
        ns.register(parent_parser)
