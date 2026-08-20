from osbot_utils.type_safe.Type_Safe                    import Type_Safe
from sgit_ai.safe_types.Safe_Str__Cache_Id          import Safe_Str__Cache_Id
from sgit_ai.safe_types.Safe_Str__Cache_Path        import Safe_Str__Cache_Path
from sgit_ai.safe_types.Enum__Cache_Kind            import Enum__Cache_Kind


class Schema__Cache_Tombstone(Type_Safe):
    """A recorded intent to remove a cache declaration.

    `sgit cache rm` cannot just delete the local object: the push reconcile
    discovers targets from the SERVER listing (D6), so without a recorded
    intent the next push cannot tell "removed on purpose" from "declared by
    another clone that this one has not mirrored" — and would resurrect the
    declaration. The tombstone survives until a push or repair successfully
    deletes the remote copy, then is cleared.
    """
    kind     : Enum__Cache_Kind    = Enum__Cache_Kind.VALUE
    cache_id : Safe_Str__Cache_Id  = None
    path     : Safe_Str__Cache_Path = None      # for display / debugging only


class Schema__Cache_Tombstones(Type_Safe):
    removed : list[Schema__Cache_Tombstone]
