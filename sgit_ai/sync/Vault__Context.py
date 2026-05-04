"""Vault__Context — detect whether cwd is outside, inside a working vault, or inside a bare vault."""
import json
import os
from enum import Enum

from osbot_utils.type_safe.Type_Safe           import Type_Safe
from sgit_ai.safe_types.Safe_Str__Vault_Id     import Safe_Str__Vault_Id
from sgit_ai.safe_types.Safe_Str__File_Path    import Safe_Str__File_Path


class Enum__Vault_Context(Enum):
    OUTSIDE        = 'outside'
    INSIDE_WORKING = 'inside-working'
    INSIDE_BARE    = 'inside-bare'


class Vault__Context(Type_Safe):
    state            : Enum__Vault_Context
    vault_path       : Safe_Str__File_Path = None
    vault_id         : Safe_Str__Vault_Id  = None
    has_working_copy : bool                = False

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def detect(cls, cwd: str = None) -> 'Vault__Context':
        """Walk parent directories from cwd looking for .sg_vault/. Returns a Vault__Context."""
        from sgit_ai.sync.Vault__Storage import Vault__Storage, SG_VAULT_DIR

        start = os.path.abspath(cwd or os.getcwd())
        path  = start
        while True:
            sg_vault = os.path.join(path, SG_VAULT_DIR)
            if os.path.isdir(sg_vault):
                vault_id = cls._read_vault_id(path)
                bare     = cls._is_bare(path, sg_vault)
                state    = Enum__Vault_Context.INSIDE_BARE if bare else Enum__Vault_Context.INSIDE_WORKING
                return cls(state            = state,
                           vault_path       = Safe_Str__File_Path(path),
                           vault_id         = Safe_Str__Vault_Id(vault_id) if vault_id else None,
                           has_working_copy = not bare)
            parent = os.path.dirname(path)
            if parent == path:
                break
            path = parent

        return cls(state            = Enum__Vault_Context.OUTSIDE,
                   vault_path       = None,
                   vault_id         = None,
                   has_working_copy = False)

    @classmethod
    def detect_with_override(cls, cwd: str = None, vault_path_arg: str = None) -> 'Vault__Context':
        """Detect context, but if vault_path_arg is provided use that path directly."""
        if vault_path_arg:
            return cls.detect(vault_path_arg)
        return cls.detect(cwd)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _is_bare(cls, directory: str, sg_vault_dir: str) -> bool:
        """A bare vault has refs but no vault_key in local/."""
        vault_key_path = os.path.join(sg_vault_dir, 'local', 'vault_key')
        refs_dir       = os.path.join(sg_vault_dir, 'bare', 'refs')
        has_vault_key  = os.path.isfile(vault_key_path)
        if has_vault_key:
            return False
        if not os.path.isdir(refs_dir):
            return False
        return any(f.startswith('ref-pid-') for f in os.listdir(refs_dir))

    @classmethod
    def _read_vault_id(cls, directory: str) -> str:
        """Read vault_id from .sg_vault/local/config.json, or return empty string."""
        config_path = os.path.join(directory, '.sg_vault', 'local', 'config.json')
        if os.path.isfile(config_path):
            try:
                with open(config_path) as f:
                    data = json.load(f)
                return data.get('vault_id', '') or ''
            except Exception:
                pass
        return ''

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def is_outside(self) -> bool:
        return self.state == Enum__Vault_Context.OUTSIDE

    def is_inside(self) -> bool:
        return self.state in (Enum__Vault_Context.INSIDE_WORKING, Enum__Vault_Context.INSIDE_BARE)

    def is_inside_working(self) -> bool:
        return self.state == Enum__Vault_Context.INSIDE_WORKING

    def is_inside_bare(self) -> bool:
        return self.state == Enum__Vault_Context.INSIDE_BARE
