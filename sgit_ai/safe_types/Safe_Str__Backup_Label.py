import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

class Safe_Str__Backup_Label(Safe_Str):
    regex           = re.compile(r'[^a-zA-Z0-9\-_]')
    max_length      = 64
    allow_empty     = False
    trim_whitespace = True
