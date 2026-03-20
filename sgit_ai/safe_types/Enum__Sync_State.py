from enum import Enum

class Enum__Sync_State(Enum):
    SYNCED             = 'synced'
    MODIFIED_LOCALLY   = 'modified_locally'
    MODIFIED_REMOTELY  = 'modified_remotely'
    CONFLICT           = 'conflict'
    ADDED_LOCALLY      = 'added_locally'
    ADDED_REMOTELY     = 'added_remotely'
    DELETED_LOCALLY    = 'deleted_locally'
    DELETED_REMOTELY   = 'deleted_remotely'
