from osbot_utils.type_safe.Type_Safe                    import Type_Safe
from sgit_ai.safe_types.Enum__User_Signature_Format     import Enum__User_Signature_Format
from sgit_ai.safe_types.Safe_Str__User_Signature_Blob   import Safe_Str__User_Signature_Blob


class Schema__User_Signature(Type_Safe):
    """The signer's own signature (SSH or OpenPGP) on a commit or tag: Git's `gpgsig`.
    It covers the same bytes as the clone signature and neither covers the other
    (design__02 §5.1)."""
    format : Enum__User_Signature_Format   = None
    blob   : Safe_Str__User_Signature_Blob = None
