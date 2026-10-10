"""Vault__Key_Fetch — bring a teammate's public key file into a clone that predates it.

Clone downloads bare/keys/<id> for every branch in the index at clone time.
A clone that lives on never saw the keys of branches registered after it, so
every commit signed by a newer teammate classified as 'no-key' (and
`signatures-required` refused it). Pull and `check verify` now fetch the
missing key files. A key file is encrypted under the vault's read key, so a
host cannot substitute one: a file that does not decrypt to a public key PEM
is not saved.
"""
import json
import os
from   osbot_utils.type_safe.Type_Safe              import Type_Safe
from   sgit_ai.crypto.Vault__Crypto                 import Vault__Crypto
from   sgit_ai.network.api.Vault__API               import Vault__API
from   sgit_ai.safe_types.Safe_Str__Key_Id          import KEY_ID__REGEX, Safe_Str__Key_Id


class Vault__Key_Fetch(Type_Safe):
    crypto : Vault__Crypto = None
    api    : Vault__API    = None
    tried  : list[Safe_Str__Key_Id]                       # asked for once per run, found or not

    def branch_key_ids(self, index) -> list:
        return [str(b.public_key_id) for b in (getattr(index, 'branches', None) or []) if b.public_key_id]

    def fetch_missing(self, c, key_ids) -> int:
        """Download the key files in key_ids this clone lacks, in one batch read.
        Returns how many were saved. Never raises: verification falls back to
        'no-key' exactly as before when the server cannot be reached."""
        tried  = {str(k) for k in self.tried}
        wanted = sorted({str(k) for k in (key_ids or [])
                         if k and KEY_ID__REGEX.match(str(k)) and str(k) not in tried
                         and not c.key_manager.key_exists(str(k))})
        if not wanted or self.api is None:
            return 0
        self.tried.extend(Safe_Str__Key_Id(k) for k in wanted)
        try:
            blobs = self.api.batch_read(str(c.vault_id), [f'bare/keys/{k}' for k in wanted]) or {}
        except Exception:
            return 0
        saved = 0
        for fid, blob in blobs.items():
            kid = str(fid).rsplit('/', 1)[-1]
            if not blob or kid not in wanted or not self._is_public_key(blob, c.read_key):
                continue
            path = c.key_manager._key_path(kid)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(blob)
            saved += 1
        return saved

    def _is_public_key(self, blob: bytes, read_key: bytes) -> bool:
        try:
            data = json.loads(self.crypto.decrypt(read_key, blob))
            return isinstance(data, dict) and data.get('type') == 'public' and 'PUBLIC KEY' in str(data.get('pem', ''))
        except Exception:
            return False
