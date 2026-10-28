from enum import Enum


class Enum__Merge_Style(Enum):
    """What a merge does when both sides changed one file: FILES keeps ours and writes
    theirs to <path>.conflict (the default, the web UI's behaviour); LINES merges the
    lines as Git does and writes conflict markers where they collide."""
    FILES = 'files'
    LINES = 'lines'
