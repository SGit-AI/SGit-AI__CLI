from osbot_utils.type_safe.Type_Safe                              import Type_Safe
from sgit_ai.safe_types.Safe_Str__Schema_Version              import Safe_Str__Schema_Version
from sgit_ai.safe_types.Safe_Str__Index_Id                    import Safe_Str__Index_Id
from sgit_ai.schemas.Schema__Branch_Meta                      import Schema__Branch_Meta
from sgit_ai.safe_types.Safe_Str__Semver                      import Safe_Str__Semver
from sgit_ai.safe_types.Safe_Str__Feature                     import Safe_Str__Feature
from osbot_utils.type_safe.primitives.core.Safe_UInt          import Safe_UInt
from sgit_ai.schemas.Schema__Tag_Ref                          import Schema__Tag_Ref
from sgit_ai.safe_types.Safe_Str__Index_Entry_Json            import Safe_Str__Index_Entry_Json


class Schema__Branch_Index(Type_Safe):
    schema     : Safe_Str__Schema_Version = None          # e.g. 'branch_index_v1'
    branches   : list[Schema__Branch_Meta]
    # The format gate. Absent on every vault that predates it: format 1, no minimum
    # client. Set by the owner (sgit vault format); writers that do not know these
    # fields drop them, which fails OPEN (back to format 1), never closed.
    format     : Safe_UInt                = None          # 1 (12-hex ids) or 2 (new objects get 32-hex ids)
    min_client : Safe_Str__Semver         = None          # 'MAJOR.MINOR.PATCH'; a client below it refuses by name
    features   : list[Safe_Str__Feature]                  # e.g. 'signatures-required'
    # Tags (0.21.0): name -> signed tag object. Clients that do not know the field
    # drop it when they rewrite the index; the next current client's pull restores
    # it from its own copy, the same way dropped branch entries come back.
    tags       : list[Schema__Tag_Ref]
    # Tag entries this version cannot read (another version's name rule, a field it does
    # not know, a commit-shaped name), as their exact JSON. Never used, never dropped: the
    # writer (Vault__Index_Reader.serialize) puts them back in `tags`, so this is never a
    # key on disk. Dropping them erased other clients' tags and tombstones (review eed8084 B1).
    carried_tags : list[Safe_Str__Index_Entry_Json]
