"""Keys__Derivation — shared helper for deriving vault keys from a vault_key string."""
from osbot_utils.type_safe.Type_Safe import Type_Safe


class Keys__Derivation(Type_Safe):
    """Utility: extracts vault_id, read_key, write_key, branch_index_file_id from a vault_key."""

    def derive(self, vault_key: str, sync_client) -> dict:
        """Return dict with vault_id, read_key_hex, write_key_hex, branch_index_file_id."""
        keys = sync_client._derive_keys_from_stored_key(vault_key)
        return {
            'vault_id'             : keys.get('vault_id', ''),
            'read_key_hex'         : keys.get('read_key', ''),
            'write_key_hex'        : keys.get('write_key', ''),
            'branch_index_file_id' : keys.get('branch_index_file_id', ''),
        }
