import re
from osbot_utils.type_safe.Type_Safe            import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str


class Safe_Str__Plugin_Name(Safe_Str):
    regex       = re.compile(r'[^a-z0-9_\-]')
    max_length  = 64
    allow_empty = False


class Safe_Str__Semver(Safe_Str):
    regex       = re.compile(r'[^0-9.]')
    max_length  = 32
    allow_empty = False


class Schema__Plugin_Manifest(Type_Safe):
    name      : Safe_Str__Plugin_Name  = None
    version   : Safe_Str__Semver       = None
    stability : str                    = 'stable'
    commands  : list
    enabled   : bool                   = True
