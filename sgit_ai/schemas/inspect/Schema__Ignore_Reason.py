from osbot_utils.type_safe.Type_Safe           import Type_Safe

from sgit_ai.safe_types.Safe_Str__Vault_Path   import Safe_Str__Vault_Path
from sgit_ai.safe_types.Safe_Str__Diff_Text    import Safe_Str__Diff_Text


class Schema__Ignore_Reason(Type_Safe):
    rel_path     : Safe_Str__Vault_Path = None
    is_ignored   : bool                 = False
    reason_code  : Safe_Str__Diff_Text  = None   # 'always_ignored_dir' | 'always_ignored_file' | 'env_secret_glob' | 'gitignore_pattern' | 'tracked'
    matched_rule : Safe_Str__Diff_Text  = None
    description  : Safe_Str__Diff_Text  = None
