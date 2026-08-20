import re
from osbot_utils.type_safe.primitives.core.Safe_Str                         import Safe_Str
from osbot_utils.type_safe.primitives.core.enums.Enum__Safe_Str__Regex_Mode import Enum__Safe_Str__Regex_Mode

# The path stored inside a cache object is an IDENTITY, not display text: the
# contract (08/12 v0 §4) requires it byte-identical to the flatten() key it was
# derived from, because readers verify it against the derived id (the 48-bit
# collision guard) and the push reconcile looks it up in the head's flat map.
#
# Safe_Str__File_Path is a SANITIZER (strips non-ASCII), which silently mutated
# unicode paths — the stored 'caf_-notes.md' never matched the real
# 'café-notes.md', so the reconcile treated the cache as an orphan and DELETED
# it on the next push. This type therefore VALIDATES instead of sanitising:
# any character is allowed except control characters; the bytes pass through
# untouched. MATCH mode + strict_validation = reject, never rewrite.
CACHE_PATH__REGEX      = re.compile(r'^[^\x00-\x1f\x7f]+$')
CACHE_PATH__MAX_LENGTH = 4096

class Safe_Str__Cache_Path(Safe_Str):
    regex             = CACHE_PATH__REGEX
    regex_mode        = Enum__Safe_Str__Regex_Mode.MATCH
    max_length        = CACHE_PATH__MAX_LENGTH
    allow_empty       = True
    trim_whitespace   = False           # trailing/leading spaces are legal in filenames
    strict_validation = True
