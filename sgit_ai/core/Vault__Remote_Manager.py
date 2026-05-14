import json
import os
from osbot_utils.type_safe.Type_Safe                                                  import Type_Safe
from osbot_utils.type_safe.primitives.domains.identifiers.safe_int.Timestamp_Now      import Timestamp_Now
from sgit_ai.schemas.Schema__Remote_Config                                        import Schema__Remote_Config
from sgit_ai.storage.Vault__Storage                                               import Vault__Storage


class Vault__Remote_Manager(Type_Safe):
    storage : Vault__Storage

    def add_remote(self, directory: str, name: str, url: str, vault_id: str,
                   is_default: bool = False, tls_verify: bool = True) -> Schema__Remote_Config:
        remotes = self._load_remotes(directory)
        for r in remotes:
            if str(r.name) == name:
                raise RuntimeError(f'Remote already exists: {name}')

        if is_default or not remotes:
            for r in remotes:
                r.is_default = False
            is_default = True

        remote = Schema__Remote_Config(
            name       = name,
            url        = url,
            vault_id   = vault_id,
            is_default = is_default,
            tls_verify = tls_verify,
            created_at = Timestamp_Now(),
        )
        remotes.append(remote)
        self._save_remotes(directory, remotes)
        return remote

    def remove_remote(self, directory: str, name: str) -> bool:
        remotes     = self._load_remotes(directory)
        new_remotes = [r for r in remotes if str(r.name) != name]
        if len(new_remotes) == len(remotes):
            return False
        if new_remotes and not any(r.is_default for r in new_remotes):
            new_remotes[0].is_default = True
        self._save_remotes(directory, new_remotes)
        return True

    def list_remotes(self, directory: str) -> list:
        remotes = self._load_remotes(directory)
        return [dict(name=str(r.name), url=str(r.url), vault_id=str(r.vault_id),
                     is_default=r.is_default, tls_verify=r.tls_verify)
                for r in remotes]

    def get_remote(self, directory: str, name: str) -> Schema__Remote_Config:
        for r in self._load_remotes(directory):
            if str(r.name) == name:
                return r
        return None

    def get_default(self, directory: str) -> Schema__Remote_Config:
        remotes = self._load_remotes(directory)
        for r in remotes:
            if r.is_default:
                return r
        if remotes:
            return remotes[0]
        return None

    def set_url(self, directory: str, name: str, new_url: str) -> Schema__Remote_Config:
        remotes = self._load_remotes(directory)
        for r in remotes:
            if str(r.name) == name:
                r.url = new_url
                self._save_remotes(directory, remotes)
                return r
        raise RuntimeError(f'Remote not found: {name}')

    def set_default(self, directory: str, name: str) -> Schema__Remote_Config:
        remotes = self._load_remotes(directory)
        found   = None
        for r in remotes:
            if str(r.name) == name:
                r.is_default = True
                found = r
            else:
                r.is_default = False
        if not found:
            raise RuntimeError(f'Remote not found: {name}')
        self._save_remotes(directory, remotes)
        return found

    def rename_remote(self, directory: str, old_name: str, new_name: str) -> Schema__Remote_Config:
        remotes = self._load_remotes(directory)
        if any(str(r.name) == new_name for r in remotes):
            raise RuntimeError(f'Remote already exists: {new_name}')
        for r in remotes:
            if str(r.name) == old_name:
                r.name = new_name
                self._save_remotes(directory, remotes)
                return r
        raise RuntimeError(f'Remote not found: {old_name}')

    def update_health(self, directory: str, name: str, status) -> Schema__Remote_Config:
        remotes = self._load_remotes(directory)
        for r in remotes:
            if str(r.name) == name:
                r.last_health_at     = Timestamp_Now()
                r.last_health_status = status
                self._save_remotes(directory, remotes)
                return r
        return None

    def _load_remotes(self, directory: str) -> list:
        path = self.storage.remotes_path(directory)
        if not os.path.isfile(path):
            return []
        with open(path, 'r') as f:
            data = json.load(f)
        return [Schema__Remote_Config.from_json(r) for r in data]

    def _save_remotes(self, directory: str, remotes: list) -> None:
        path = self.storage.remotes_path(directory)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump([r.json() for r in remotes], f, indent=2)
