from osbot_utils.type_safe.Type_Safe                    import Type_Safe
from sgit_ai.safe_types.Enum__Published_Layout          import Enum__Published_Layout
from sgit_ai.safe_types.Enum__Visibility                import Enum__Visibility
from sgit_ai.safe_types.Safe_Str__App_Version           import Safe_Str__App_Version
from sgit_ai.safe_types.Safe_Str__Object_Id             import Safe_Str__Object_Id
from sgit_ai.safe_types.Safe_Str__Schema_Version        import Safe_Str__Schema_Version
from sgit_ai.safe_types.Safe_Str__Vault_Id              import Safe_Str__Vault_Id
from sgit_ai.schemas.publish.Schema__Plaintext_Entry    import Schema__Plaintext_Entry
from sgit_ai.schemas.publish.Schema__Published_Object   import Schema__Published_Object

PUBLISHED_SCHEMA_VERSION = 'sgit_published_v1'


class Schema__Published_Manifest(Type_Safe):
    """manifest.json — required, three jobs (01 §4):

    1. CUSTODY — every filename in a vault derives from the read key, so a
       keyless client cannot name a single file without objects[].
    2. PARALLEL FETCH — the ordered commit list (walked from the head via
       parents) lets bundles be fetched in parallel.
    3. AUDITABILITY — plaintext_surface declares and hashes every
       non-ciphertext file in the folder.

    It is a hint, never authority: consumers that can re-derive integrity
    (content addresses, parent walks) must prefer their own derivation.
    """
    schema            : Safe_Str__Schema_Version         = None
    vault_id          : Safe_Str__Vault_Id               = None
    generated_by      : Safe_Str__App_Version            = None
    layout            : Enum__Published_Layout           = None
    visibility        : Enum__Visibility                 = None
    head              : Safe_Str__Object_Id              = None
    plaintext_surface : list[Schema__Plaintext_Entry]
    objects           : list[Schema__Published_Object]
    commits           : list[Safe_Str__Object_Id]
