from osbot_utils.type_safe.Type_Safe                  import Type_Safe
from sgit_ai.safe_types.Enum__Sign_Choice             import Enum__Sign_Choice
from sgit_ai.safe_types.Safe_Str__Signing_Key_Spec    import Safe_Str__Signing_Key_Spec


class Schema__Signing_Flags(Type_Safe):
    """What a command line said about user signing: -S / --gpg-sign[=KEY] / --no-gpg-sign
    (tags: -s / -u KEY / --no-sign). None everywhere = the Git config decides."""
    sign : Enum__Sign_Choice          = None
    key  : Safe_Str__Signing_Key_Spec = None
