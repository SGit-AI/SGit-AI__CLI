from osbot_utils.type_safe.Type_Safe                       import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt       import Safe_UInt
from sgit_ai.safe_types.Safe_Str__Schema_Version           import Safe_Str__Schema_Version
from sgit_ai.safe_types.Safe_Str__Tag_Name                 import Safe_Str__Tag_Name
from sgit_ai.safe_types.Safe_Str__Tag_Message              import Safe_Str__Tag_Message
from sgit_ai.safe_types.Safe_Str__Commit_Id                import Safe_Str__Commit_Id
from sgit_ai.safe_types.Safe_Str__Author_Key_Id            import Safe_Str__Author_Key_Id
from sgit_ai.safe_types.Safe_Str__Branch_Id                import Safe_Str__Branch_Id
from sgit_ai.safe_types.Safe_Str__Signature                import Safe_Str__Signature


class Schema__Object_Tag(Type_Safe):
    """An annotated, signed tag: an immutable object in bare/data, encrypted under
    the read key and named by the hash of its ciphertext like every other object.
    The signature covers the canonical (JCS) form of this object without
    `signature`, the same rule as a commit's, so the name, the commit and the
    message are all signed: a tag cannot be re-pointed or renamed undetected."""
    schema        : Safe_Str__Schema_Version = None        # 'tag_v1'
    name          : Safe_Str__Tag_Name       = None
    commit_id     : Safe_Str__Commit_Id      = None
    message       : Safe_Str__Tag_Message    = None
    timestamp_ms  : Safe_UInt
    tagger_branch : Safe_Str__Branch_Id      = None        # the clone branch that made it
    tagger_key_id : Safe_Str__Author_Key_Id  = None        # its public key (bare/keys/<id>)
    signature     : Safe_Str__Signature      = None
