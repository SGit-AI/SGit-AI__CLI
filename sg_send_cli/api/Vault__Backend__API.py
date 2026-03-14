from sg_send_cli.api.Vault__Backend                import Vault__Backend
from sg_send_cli.api.Vault__API                    import Vault__API
from sg_send_cli.safe_types.Safe_Str__Vault_Id     import Safe_Str__Vault_Id
from sg_send_cli.safe_types.Safe_Str__Write_Key    import Safe_Str__Write_Key


class Vault__Backend__API(Vault__Backend):
    """SG/Send Transfer API backend — proxies storage to the remote server."""
    api       : Vault__API
    vault_id  : Safe_Str__Vault_Id  = None
    write_key : Safe_Str__Write_Key = None

    def read(self, file_id: str) -> bytes:
        return self.api.read(str(self.vault_id), file_id)

    def write(self, file_id: str, data: bytes) -> dict:
        return self.api.write(str(self.vault_id), file_id, str(self.write_key), data)

    def delete(self, file_id: str) -> dict:
        return self.api.delete(str(self.vault_id), file_id, str(self.write_key))

    def list_files(self, prefix: str = '') -> list:
        result = self.api.list_files(str(self.vault_id), prefix)
        if isinstance(result, list):
            return result
        return result.get('files', [])

    def batch(self, operations: list) -> dict:
        return self.api.batch(str(self.vault_id), str(self.write_key), operations)
