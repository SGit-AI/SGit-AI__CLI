def parse_commit_range(arg: str) -> tuple:
    """Parse <from>..<to>, <from>.., ..<to>, or plain string (no range).

    Returns (from_commit, to_commit) as strings.
    Empty string on either side means open-ended.
    Raises ValueError on malformed input (e.g. multiple '..' separators treated
    as nested, which isn't supported).

    Disambiguation from directory paths: a range must not contain '/'.
    """
    if '..' not in arg:
        return ('', '')
    parts = arg.split('..', 1)
    return (parts[0].strip(), parts[1].strip())


def looks_like_range(arg: str) -> bool:
    """True if arg looks like a commit range rather than a filesystem path.

    Ranges contain '..' and no '/'. Paths always contain '/' or are '.' / '..'.
    """
    if not arg or '..' not in arg:
        return False
    if '/' in arg:
        return False
    return True
