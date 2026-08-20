from osbot_utils.type_safe.Type_Safe            import Type_Safe
from sgit_ai.safe_types.Safe_Str__File_Path     import Safe_Str__File_Path
from sgit_ai.safe_types.Safe_Str__Cover_Text    import Safe_Str__Cover_Text
from sgit_ai.safe_types.Safe_Str__ISO_Timestamp import Safe_Str__ISO_Timestamp


class Schema__Vault_Cover(Type_Safe):
    """cover.json — the closed vault's public face (P4): what a keyless
    visitor sees. `updated` derives from the head commit's timestamp, never
    wall-clock, so publishing twice stays byte-identical (P2 determinism).
    `access` is a free-text 'how to request access' hint (e.g. an email)."""
    title       : Safe_Str__Cover_Text      = None
    description : Safe_Str__Cover_Text      = None
    image       : Safe_Str__File_Path       = None
    updated     : Safe_Str__ISO_Timestamp   = None
    access      : Safe_Str__Cover_Text      = None
    public      : bool                      = False
