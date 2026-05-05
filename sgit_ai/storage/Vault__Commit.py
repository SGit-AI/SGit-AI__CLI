import base64
import json
import sys
import time
from   osbot_utils.type_safe.Type_Safe                import Type_Safe
from   sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from   sgit_ai.crypto.PKI__Crypto                 import PKI__Crypto
from   sgit_ai.storage.Vault__Object_Store        import Vault__Object_Store
from   sgit_ai.storage.Vault__Ref_Manager         import Vault__Ref_Manager
from   sgit_ai.schemas.Schema__Object_Commit      import Schema__Object_Commit
from   sgit_ai.schemas.Schema__Object_Tree        import Schema__Object_Tree

_warned_branch_ids: set = set()   # process-level dedup for branch_id warnings


class Vault__Commit(Type_Safe):
    crypto       : Vault__Crypto
    pki          : PKI__Crypto
    object_store : Vault__Object_Store
    ref_manager  : Vault__Ref_Manager

    def create_commit(self, read_key: bytes, tree_id: str,
                      parent_ids: list = None, message: str = '',
                      message_enc: str = None,
                      branch_id: str = None, signing_key=None,
                      timestamp_ms: int = None) -> str:
        """Create a commit object and store it.

        tree_id must be a pre-stored root tree object ID.
        """
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        parents = [p for p in (parent_ids or []) if p]

        if not message_enc and message:
            message_enc = self.crypto.encrypt_metadata(read_key, message)

        commit = Schema__Object_Commit(tree_id      = tree_id,
                                        schema       = 'commit_v1',
                                        timestamp_ms = timestamp_ms,
                                        message_enc  = message_enc,
                                        branch_id    = branch_id or '',
                                        parents      = parents)

        commit_data = json.dumps(commit.json()).encode()

        if signing_key:
            sig_raw          = self.pki.sign(signing_key, commit_data)
            sig_b64          = base64.b64encode(sig_raw).decode()
            commit.signature = sig_b64
            commit_data      = json.dumps(commit.json()).encode()

        encrypted_commit = self.crypto.encrypt(read_key, commit_data)
        return self.object_store.store(encrypted_commit)

    def load_commit(self, commit_id: str, read_key: bytes) -> Schema__Object_Commit:
        ciphertext  = self.object_store.load(commit_id)
        commit_data = self.crypto.decrypt(read_key, ciphertext)
        raw         = json.loads(commit_data)
        try:
            return Schema__Object_Commit.from_json(raw)
        except (ValueError, Exception) as e:
            if 'Safe_Str__Branch_Id' in str(e) and 'does not match required pattern' in str(e):
                # The web UI (or an older client) wrote a branch_id that doesn't match
                # the CLI pattern.  branch_id is metadata only — strip it so that pull
                # can still access tree_id and parents and complete the merge.
                bad_val = raw.get('branch_id', '<unknown>')
                raw['branch_id'] = ''
                if commit_id not in _warned_branch_ids:
                    _warned_branch_ids.add(commit_id)
                    print(f'  warning: commit {commit_id} has unrecognised branch_id '
                          f'"{bad_val}" — treated as anonymous (likely written by web UI)',
                          file=sys.stderr)
                return Schema__Object_Commit.from_json(raw)
            # Any other parse error: re-raise with commit_id + raw JSON for diagnosis
            raw_str = commit_data.decode('utf-8', errors='replace') if isinstance(commit_data, bytes) else str(commit_data)
            raise ValueError(
                f'{e}\n'
                f'  commit_id: {commit_id}\n'
                f'  raw JSON:  {raw_str}'
            ) from e

    def load_tree(self, tree_id: str, read_key: bytes) -> Schema__Object_Tree:
        """Load a tree object (entries have encrypted fields only)."""
        ciphertext = self.object_store.load(tree_id)
        tree_data  = self.crypto.decrypt(read_key, ciphertext)
        return Schema__Object_Tree.from_json(json.loads(tree_data))

    def verify_commit_signature(self, commit: Schema__Object_Commit, public_key) -> bool:
        if not commit.signature:
            return False
        sig_raw     = base64.b64decode(str(commit.signature))
        commit_dict = commit.json()
        commit_dict['signature'] = None
        commit_data = json.dumps(commit_dict).encode()
        try:
            return self.pki.verify(public_key, sig_raw, commit_data)
        except Exception:
            return False
