from enum import Enum


class Enum__Line_Merge_Outcome(Enum):
    CLEAN         = 'clean'
    CONFLICT      = 'conflict'
    BINARY        = 'binary'
    TOO_LARGE     = 'too-large'
    TOO_DIFFERENT = 'too-different'
    MISSING_BLOB  = 'missing-blob'
    NOT_TEXT_PAIR = 'not-text-pair'           # modify/delete: not a content merge
