from sgit_ai.plugins._base.Plugin__Read_Only          import Plugin__Read_Only
from sgit_ai.plugins._base.Schema__Plugin_Manifest    import Schema__Plugin_Manifest
from sgit_ai.plugins.dev.CLI__Dev                      import CLI__Dev


class Plugin__Dev(Plugin__Read_Only):
    manifest : Schema__Plugin_Manifest

    def register_subparsers(self, parent_parser, context: dict):
        ns            = CLI__Dev()
        ns.vault_ref  = context.get('vault')
        ns.dump_ref   = context.get('dump')
        ns.main_ref   = context.get('main')
        ns.register(parent_parser)
