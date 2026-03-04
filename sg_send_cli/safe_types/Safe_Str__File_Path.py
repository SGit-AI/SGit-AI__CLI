import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

FILE_PATH__REGEX      = re.compile(r'[^a-zA-Z0-9/\\_.\- ]')
FILE_PATH__MAX_LENGTH = 4096

class Safe_Str__File_Path(Safe_Str):
    regex       = FILE_PATH__REGEX
    max_length  = FILE_PATH__MAX_LENGTH
    allow_empty = True
