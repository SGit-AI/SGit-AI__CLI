import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str

# A published file_id is the wire path of an object relative to .sg_vault/ —
# e.g. bare/refs/ref-pid-muw-1995ccf51fe8 or bare/data/obj-cas-imm-4ccb5bc28ba1.
# Consumers must STILL route it through Vault__Path_Guard before using it as a
# filesystem path (SP-8): this type constrains the alphabet, the guard
# constrains the topology.
PUBLISHED_FILE_ID__REGEX = re.compile(r'[^a-zA-Z0-9/._\-]')


class Safe_Str__Published_File_Id(Safe_Str):
    regex           = PUBLISHED_FILE_ID__REGEX
    max_length      = 512
    allow_empty     = True
    trim_whitespace = True
