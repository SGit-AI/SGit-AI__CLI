"""Vault__Merge_Style_Resolver — which merge style a pull or branch merge uses.

Precedence, as Git reads `-X`/`--conflict` before `merge.conflictStyle`: the command's
flag, then the session's SGIT_MERGE_STYLE (agents set it per session; design__01 D1),
then this clone's `.sg_vault/local/config.json`, then the default: `files` (keep ours,
theirs in `<path>.conflict`, what the web UI does) and, in `lines` style, `merge`
markers. Never synced: the style is how this clone merges, not a property of the vault.
"""
import os
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.safe_types.Enum__Conflict_Style      import Enum__Conflict_Style
from   sgit_ai.safe_types.Enum__Merge_Style         import Enum__Merge_Style

MERGE_STYLE_ENV = 'SGIT_MERGE_STYLE'


class Vault__Merge_Style_Resolver(Type_Safe):

    def resolve(self, merge_flag: str = None, conflict_flag: str = None, local_config=None) -> tuple:
        """(Enum__Merge_Style, Enum__Conflict_Style)."""
        merge_style = (self.parse(Enum__Merge_Style, merge_flag)
                       or self.parse(Enum__Merge_Style, os.environ.get(MERGE_STYLE_ENV))
                       or getattr(local_config, 'merge_style', None)
                       or Enum__Merge_Style.FILES)
        conflict_style = (self.parse(Enum__Conflict_Style, conflict_flag)
                          or getattr(local_config, 'conflict_style', None)
                          or Enum__Conflict_Style.MERGE)
        return merge_style, conflict_style

    def parse(self, enum_type, value):
        """The enum member for a value, or None (an unknown environment value is ignored:
        the flag is checked by argparse, the environment is not)."""
        if isinstance(value, enum_type):
            return value
        text = str(value or '').strip().lower()
        for member in enum_type:
            if member.value == text:
                return member
        return None
