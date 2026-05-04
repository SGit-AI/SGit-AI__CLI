from osbot_utils.type_safe.Type_Safe                          import Type_Safe
from sgit_ai.plugins._base.Schema__Plugin_Manifest import Schema__Plugin_Manifest


class Plugin__Read_Only(Type_Safe):
    manifest : Schema__Plugin_Manifest

    def register_subparsers(self, parent_parser, context: dict):
        raise NotImplementedError(f'{type(self).__name__}.register_subparsers() not implemented')

    def commands(self) -> list:
        return list(self.manifest.commands)
