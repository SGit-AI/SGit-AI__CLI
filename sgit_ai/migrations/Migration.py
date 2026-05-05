from osbot_utils.type_safe.Type_Safe import Type_Safe
from sgit_ai.safe_types.Safe_Str__Migration_Name import Safe_Str__Migration_Name

class Migration(Type_Safe):
    name : Safe_Str__Migration_Name = None

    def is_applied(self, sg_dir: str, read_key: bytes) -> bool:
        raise NotImplementedError

    def apply(self, sg_dir: str, read_key: bytes) -> dict:
        """Apply the migration. Returns stats dict with n_trees, n_commits, n_refs."""
        raise NotImplementedError

    def migration_name(self) -> str:
        return str(self.name)
