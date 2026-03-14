from enum import Enum


class Enum__Batch_Op(str, Enum):
    WRITE          = 'write'
    WRITE_IF_MATCH = 'write-if-match'
    DELETE         = 'delete'
