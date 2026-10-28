from enum import Enum


class Enum__Conflict_Style(Enum):
    """How a line-merge conflict is written (Git's merge.conflictStyle): ours and theirs,
    or ours, the base and theirs."""
    MERGE = 'merge'
    DIFF3 = 'diff3'
