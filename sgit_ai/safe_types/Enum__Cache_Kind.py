from enum import Enum


class Enum__Cache_Kind(Enum):
    VALUE   = 'value'                     # cache object holds a copy of the file's plaintext
    POINTER = 'pointer'                   # cache object holds a blob_id / tree_id reference
