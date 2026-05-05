import re
from osbot_utils.type_safe.Type_Safe                import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str
from sgit_ai.safe_types.Safe_Str__Semver            import Safe_Str__Semver


class Safe_Str__Plugin_Name(Safe_Str):
    regex       = re.compile(r'[^a-z0-9_\-]')
    max_length  = 64
    allow_empty = False


class Schema__Plugin_Manifest(Type_Safe):
    name      : Safe_Str__Plugin_Name = None
    version   : Safe_Str__Semver      = None
    stability : Safe_Str              = None
    commands  : list[Safe_Str__Plugin_Name]
    enabled   : bool                  = True
    settings  : dict                  = None
