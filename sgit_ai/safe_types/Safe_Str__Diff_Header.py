import re
from osbot_utils.type_safe.primitives.core.Safe_Str import Safe_Str


class Safe_Str__Diff_Header(Safe_Str):
    """`@@ -10,6 +10,8 @@ def main():` — display only; control characters replaced."""
    regex           = re.compile(r'[\x00-\x1f\x7f]')
    max_length      = 300
    allow_empty     = True
    trim_whitespace = False
