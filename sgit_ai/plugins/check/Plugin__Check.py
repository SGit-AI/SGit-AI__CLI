from sgit_ai.plugins._base.Plugin__Read_Only          import Plugin__Read_Only
from sgit_ai.plugins._base.Schema__Plugin_Manifest    import Schema__Plugin_Manifest
from sgit_ai.plugins.check.CLI__Check                  import CLI__Check


class Plugin__Check(Plugin__Read_Only):
    manifest : Schema__Plugin_Manifest

    def register_subparsers(self, parent_parser, context: dict):
        ns       = CLI__Check()
        ns.vault = context.get('vault')
        ns.register(parent_parser)
