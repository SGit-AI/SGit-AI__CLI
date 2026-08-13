from enum import Enum


class Enum__Cache_Mutability(Enum):
    SNW = 'snw'                           # single-writer (the writing interface owns updates)
    MUW = 'muw'                           # multi-writer (updates use write-if-match CAS)
