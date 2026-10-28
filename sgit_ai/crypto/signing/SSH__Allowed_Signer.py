from   osbot_utils.type_safe.Type_Safe                  import Type_Safe
from   osbot_utils.type_safe.primitives.core.Safe_UInt  import Safe_UInt
from   sgit_ai.safe_types.Safe_Str__Signer_Principal    import Safe_Str__Signer_Principal


class SSH__Allowed_Signer(Type_Safe):
    """One line of an allowed-signers file. Option values are kept as written."""
    principals        : Safe_Str__Signer_Principal
    namespaces        : Safe_Str__Signer_Principal = None
    valid_after       : Safe_Str__Signer_Principal = None
    valid_before      : Safe_Str__Signer_Principal = None
    cert_authority    : bool = False
    no_touch_required : bool = False
    verify_required   : bool = False
    key_blob          : bytes
    line_number       : Safe_UInt
