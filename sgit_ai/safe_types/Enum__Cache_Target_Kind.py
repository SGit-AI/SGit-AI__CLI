from enum import Enum


class Enum__Cache_Target_Kind(Enum):
    BLOB = 'blob'                         # pointer targets a file blob   (obj-cas-imm-*)
    TREE = 'tree'                         # pointer targets a folder/subtree (obj-cas-imm-*)
