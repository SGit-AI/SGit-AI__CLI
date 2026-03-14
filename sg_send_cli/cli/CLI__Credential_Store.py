import os
import json
import time
from osbot_utils.type_safe.Type_Safe        import Type_Safe
from sg_send_cli.secrets.Secrets__Store     import Secrets__Store
from sg_send_cli.crypto.Vault__Crypto                  import Vault__Crypto
from sg_send_cli.safe_types.Safe_UInt__Lock_Timeout    import Safe_UInt__Lock_Timeout

SG_SEND_HOME         = os.path.expanduser('~/.sg-send')
VAULTS_ENC_FILE      = 'vaults.enc'
LOCK_STATE_FILE      = 'lock-state.json'
DEFAULT_LOCK_TIMEOUT = 1800                                               # 30 minutes


class CLI__Credential_Store(Type_Safe):
    secrets      : Secrets__Store
    lock_timeout : Safe_UInt__Lock_Timeout = DEFAULT_LOCK_TIMEOUT

    def setup(self, sg_send_dir: str = None):
        home = sg_send_dir or SG_SEND_HOME
        os.makedirs(home, exist_ok=True)
        if not self.secrets.store_path:
            self.secrets = Secrets__Store(store_path=os.path.join(home, VAULTS_ENC_FILE),
                                          crypto=Vault__Crypto())
        self._sg_send_dir = home
        return self

    def add_vault(self, passphrase: str, alias: str, vault_key: str):
        self.secrets.store(passphrase, alias, vault_key)
        self._touch_activity()

    def get_vault_key(self, passphrase: str, alias: str) -> str:
        self._check_auto_lock()
        result = self.secrets.get(passphrase, alias)
        self._touch_activity()
        return result

    def list_vaults(self, passphrase: str) -> list:
        self._check_auto_lock()
        result = self.secrets.list_keys(passphrase)
        self._touch_activity()
        return result

    def remove_vault(self, passphrase: str, alias: str) -> bool:
        return self.secrets.delete(passphrase, alias)

    def resolve_vault_key(self, alias_or_key: str, passphrase: str = None) -> str:
        if ':' in alias_or_key:
            return alias_or_key
        if not passphrase:
            passphrase = self._prompt_passphrase()
        vault_key = self.get_vault_key(passphrase, alias_or_key)
        if not vault_key:
            raise RuntimeError(f'No vault key found for alias "{alias_or_key}"')
        return vault_key

    def _prompt_passphrase(self, confirm: bool = False) -> str:
        passphrase = os.environ.get('SG_SEND_PASSPHRASE')
        if passphrase:
            return passphrase
        import getpass
        passphrase = getpass.getpass('Passphrase: ')
        if confirm:
            confirm_pp = getpass.getpass('Confirm passphrase: ')
            if passphrase != confirm_pp:
                raise RuntimeError('Passphrases do not match')
        return passphrase

    # --- Auto-lock on inactivity ---

    def _lock_state_path(self) -> str:
        home = getattr(self, '_sg_send_dir', SG_SEND_HOME)
        return os.path.join(home, LOCK_STATE_FILE)

    def _touch_activity(self):
        state = {'last_activity': time.time()}
        lock_path = self._lock_state_path()
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        with open(lock_path, 'w') as f:
            json.dump(state, f)

    def _check_auto_lock(self):
        lock_path = self._lock_state_path()
        if not os.path.isfile(lock_path):
            return
        with open(lock_path, 'r') as f:
            state = json.load(f)
        last = state.get('last_activity', 0)
        if time.time() - last > self.lock_timeout:
            self._lock()

    def _lock(self):
        lock_path = self._lock_state_path()
        if os.path.isfile(lock_path):
            os.remove(lock_path)
