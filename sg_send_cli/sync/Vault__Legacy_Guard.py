import os
from osbot_utils.type_safe.Type_Safe import Type_Safe

SG_VAULT_DIR    = '.sg_vault'
LEGACY_TREE     = 'tree.json'
NEW_REFS_HEAD   = os.path.join('refs', 'head')


class Legacy_Vault_Error(Exception):
    pass


LEGACY_ERROR_MESSAGE = (
    "This vault uses the legacy format (created by vault.sgraph.ai or workspace.ai). "
    "This CLI version only supports the new git-like object store format. "
    "Use the web interface for legacy vaults."
)


class Vault__Legacy_Guard(Type_Safe):

    def check_vault_format(self, directory: str) -> None:
        vault_path     = os.path.join(directory, SG_VAULT_DIR)
        has_legacy_tree = os.path.isfile(os.path.join(vault_path, LEGACY_TREE))
        has_refs_head   = os.path.isfile(os.path.join(vault_path, NEW_REFS_HEAD))

        if has_legacy_tree and not has_refs_head:
            raise Legacy_Vault_Error(LEGACY_ERROR_MESSAGE)
