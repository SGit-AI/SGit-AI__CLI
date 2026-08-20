"""Vault__API__Auto — transparent (but never silent) transport resolution.

The resolution rule from the static-publishing architecture (01 §1):

    base_url is not http(s)://   ->  local/static folder transport (unambiguous)
    base_url is http(s)://       ->  try the live API once
                                      ├─ works              -> api transport
                                      └─ 404 / 405 / 501    -> static transport (remembered)

The resolved transport is REPORTED by the CLI (command output, `sgit vault
info`) and can be forced with --transport; auto-detection must stay visible so
it cannot hide a deployment mistake. Connection-level failures are NOT a
resolution signal — a dead host raises either way (F5), it never silently
flips the transport.
"""
from   sgit_ai.network.api.Vault__API          import Vault__API
from   sgit_ai.network.api.Vault__API__Static  import Vault__API__Static
from   sgit_ai.safe_types.Enum__Transport      import Enum__Transport

FALLBACK_MARKERS = ('HTTP 404', 'HTTP 405', 'HTTP 501')


class Vault__API__Auto(Vault__API):
    resolved  : Enum__Transport     = None
    static    : Vault__API__Static  = None

    def setup(self):
        base = str(self.base_url or '')
        if base and not (base.startswith('http://') or base.startswith('https://')):
            self.resolved = Enum__Transport.LOCAL      # a folder is unambiguous
            self._static().setup()
            return self
        return super().setup()

    def _static(self) -> Vault__API__Static:
        if self.static is None:
            self.static = Vault__API__Static(base_url     = self.base_url,
                                             access_token = None,          # I2: no key/token to a static host
                                             tls_verify   = self.tls_verify,
                                             debug_log    = self.debug_log)
        return self.static

    def _is_static(self) -> bool:
        return self.resolved in (Enum__Transport.STATIC, Enum__Transport.LOCAL)

    def _resolve_from_error(self, error: Exception) -> bool:
        """True when the API error means 'this host has no live API' —
        the signal to remember the static transport."""
        if self.resolved is not None:
            return False
        message = str(error)
        return any(marker in message for marker in FALLBACK_MARKERS)

    def _call(self, method_name: str, *args, **kwargs):
        if self._is_static():
            return getattr(self._static(), method_name)(*args, **kwargs)
        try:
            result = getattr(super(), method_name)(*args, **kwargs)
            if self.resolved is None:
                self.resolved = Enum__Transport.API
            return result
        except RuntimeError as error:
            if self._resolve_from_error(error):
                import sys
                self.resolved = Enum__Transport.STATIC
                print(f'note: {self.base_url} has no live API (HTTP 404/405/501 on the '
                      f'batch endpoint) — using the static read-only transport.',
                      file=sys.stderr)
                return getattr(self._static(), method_name)(*args, **kwargs)
            raise

    def read(self, vault_id: str, file_id: str) -> bytes:
        return self._call('read', vault_id, file_id)

    def batch_read(self, vault_id: str, file_ids: list, failures: dict = None) -> dict:
        return self._call('batch_read', vault_id, file_ids, failures)

    def presigned_read_url(self, vault_id: str, file_id: str) -> dict:
        return self._call('presigned_read_url', vault_id, file_id)

    def list_files(self, vault_id: str, prefix: str = '') -> list:
        return self._call('list_files', vault_id, prefix)

    def write(self, vault_id: str, file_id: str, write_key: str, payload: bytes) -> dict:
        return self._call('write', vault_id, file_id, write_key, payload)

    def delete(self, vault_id: str, file_id: str, write_key: str) -> dict:
        return self._call('delete', vault_id, file_id, write_key)

    def batch(self, vault_id: str, write_key: str, operations: list) -> dict:
        return self._call('batch', vault_id, write_key, operations)

    def describe(self) -> str:
        """Human-readable transport line for command output / vault info."""
        if self.resolved == Enum__Transport.LOCAL:
            return 'local (folder, read-only)'
        if self.resolved == Enum__Transport.STATIC:
            return 'static-http (GET fan-out, read-only)'
        if self.resolved == Enum__Transport.API:
            return 'api (live SG/API)'
        return 'auto (not yet resolved)'
