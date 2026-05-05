from sgit_ai.plugins._base.Plugin__Read_Only          import Plugin__Read_Only
from sgit_ai.plugins._base.Schema__Plugin_Manifest    import Schema__Plugin_Manifest
from sgit_ai.plugins.inspect.CLI__Inspect              import CLI__Inspect


class Plugin__Inspect(Plugin__Read_Only):
    manifest : Schema__Plugin_Manifest

    def register_subparsers(self, parent_parser, context: dict):
        ns        = CLI__Inspect()
        ns.vault  = context.get('vault')
        ns.dump   = context.get('dump')
        ns.register(parent_parser)
