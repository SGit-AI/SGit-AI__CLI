import os
from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Vault_Path import Safe_Str__Vault_Path

SG_VAULT_DIR   = '.sg_vault'
BARE_DIR       = 'bare'
LOCAL_DIR      = 'local'
BARE_DATA      = 'data'
BARE_REFS      = 'refs'
BARE_KEYS      = 'keys'
BARE_INDEXES   = 'indexes'
BARE_PENDING   = 'pending'
BARE_BRANCHES  = 'branches'
VAULT_KEY_FILE = 'vault_key'
TREE_FILE      = 'tree.json'
SETTINGS_FILE  = 'settings.json'


class Vault__Storage(Type_Safe):
    vault_path : Safe_Str__Vault_Path = None

    def sg_vault_dir(self, directory: str) -> str:
        return os.path.join(directory, SG_VAULT_DIR)

    def bare_dir(self, directory: str) -> str:
        return os.path.join(directory, SG_VAULT_DIR, BARE_DIR)

    def local_dir(self, directory: str) -> str:
        return os.path.join(directory, SG_VAULT_DIR, LOCAL_DIR)

    def bare_data_dir(self, directory: str) -> str:
        return os.path.join(self.bare_dir(directory), BARE_DATA)

    def bare_refs_dir(self, directory: str) -> str:
        return os.path.join(self.bare_dir(directory), BARE_REFS)

    def bare_keys_dir(self, directory: str) -> str:
        return os.path.join(self.bare_dir(directory), BARE_KEYS)

    def bare_indexes_dir(self, directory: str) -> str:
        return os.path.join(self.bare_dir(directory), BARE_INDEXES)

    def bare_pending_dir(self, directory: str) -> str:
        return os.path.join(self.bare_dir(directory), BARE_PENDING)

    def bare_branches_dir(self, directory: str) -> str:
        return os.path.join(self.bare_dir(directory), BARE_BRANCHES)

    def create_bare_structure(self, directory: str) -> str:
        sg_dir = self.sg_vault_dir(directory)
        for sub_dir in [self.bare_data_dir(directory),
                        self.bare_refs_dir(directory),
                        self.bare_keys_dir(directory),
                        self.bare_indexes_dir(directory),
                        self.bare_pending_dir(directory),
                        self.bare_branches_dir(directory),
                        self.local_dir(directory)]:
            os.makedirs(sub_dir, exist_ok=True)
        return sg_dir

    def is_v2_vault(self, directory: str) -> bool:
        return os.path.isdir(self.bare_dir(directory))

    def is_v1_vault(self, directory: str) -> bool:
        sg_dir = self.sg_vault_dir(directory)
        return (os.path.isdir(sg_dir) and
                os.path.isfile(os.path.join(sg_dir, 'refs', 'head')) and
                not os.path.isdir(self.bare_dir(directory)))

    def vault_key_path(self, directory: str) -> str:
        return os.path.join(self.local_dir(directory), VAULT_KEY_FILE)

    def local_config_path(self, directory: str) -> str:
        return os.path.join(self.local_dir(directory), 'config.json')

    def remotes_path(self, directory: str) -> str:
        return os.path.join(self.local_dir(directory), 'remotes.json')

    def tracking_path(self, directory: str) -> str:
        return os.path.join(self.local_dir(directory), 'tracking.json')

    def object_path(self, directory: str, object_id: str) -> str:
        return os.path.join(self.bare_data_dir(directory), object_id)

    def ref_path(self, directory: str, ref_id: str) -> str:
        return os.path.join(self.bare_refs_dir(directory), ref_id)

    def key_path(self, directory: str, key_id: str) -> str:
        return os.path.join(self.bare_keys_dir(directory), key_id)

    def index_path(self, directory: str, index_id: str) -> str:
        return os.path.join(self.bare_indexes_dir(directory), index_id)
