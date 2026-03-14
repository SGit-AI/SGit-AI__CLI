import json
import os
from   osbot_utils.type_safe.Type_Safe               import Type_Safe
from   sg_send_cli.schemas.Schema__Remote_Config     import Schema__Remote_Config
from   sg_send_cli.sync.Vault__Storage               import Vault__Storage


class Vault__Remote_Manager(Type_Safe):
    storage : Vault__Storage

    def add_remote(self, directory: str, name: str, url: str, vault_id: str) -> Schema__Remote_Config:
        """Add a named remote configuration."""
        remotes = self._load_remotes(directory)
        for r in remotes:
            if str(r.name) == name:
                raise RuntimeError(f'Remote already exists: {name}')

        remote = Schema__Remote_Config(name=name, url=url, vault_id=vault_id)
        remotes.append(remote)
        self._save_remotes(directory, remotes)
        return remote

    def remove_remote(self, directory: str, name: str) -> bool:
        """Remove a named remote. Returns True if found and removed."""
        remotes = self._load_remotes(directory)
        new_remotes = [r for r in remotes if str(r.name) != name]
        if len(new_remotes) == len(remotes):
            return False
        self._save_remotes(directory, new_remotes)
        return True

    def list_remotes(self, directory: str) -> list:
        """Return list of configured remotes as dicts."""
        remotes = self._load_remotes(directory)
        return [dict(name=str(r.name), url=str(r.url), vault_id=str(r.vault_id))
                for r in remotes]

    def get_remote(self, directory: str, name: str) -> Schema__Remote_Config:
        """Get a specific remote by name. Returns None if not found."""
        remotes = self._load_remotes(directory)
        for r in remotes:
            if str(r.name) == name:
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
