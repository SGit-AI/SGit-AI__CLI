from osbot_utils.type_safe.Type_Safe          import Type_Safe
from sgit_ai.safe_types.Safe_Str__File_Path   import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__SHA256      import Safe_Str__SHA256


class Schema__Plaintext_Entry(Type_Safe):
    """One file of the declared plaintext surface, with its hash — so
    'nothing else is exposed' is verifiable by inspection rather than
    trusted. manifest.json's own entry carries sha256=None (it cannot
    contain its own hash)."""
    path   : Safe_Str__File_Path = None
    sha256 : Safe_Str__SHA256    = None
