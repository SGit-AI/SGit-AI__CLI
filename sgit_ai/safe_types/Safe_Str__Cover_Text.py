import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

# Human-facing cover.json text: titles, descriptions and access hints, which
# legitimately carry emails (ir@example.com) and URLs. Angle brackets, quotes
# and backslashes are stripped — the loader renders this into a page, so the
# alphabet must not be able to open a tag or an attribute.
COVER_TEXT__REGEX = re.compile(r'[^a-zA-Z0-9 .,;:!?@#%&()+/\-_\'’À-ɏ]')


class Safe_Str__Cover_Text(Safe_Str):
    regex           = COVER_TEXT__REGEX
    max_length      = 2048
    allow_empty     = True
    trim_whitespace = True
