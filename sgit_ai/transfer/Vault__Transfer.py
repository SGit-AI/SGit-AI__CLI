import io
import json
import os
import zipfile
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.api.API__Transfer                   import API__Transfer
from sgit_ai.api.Transfer__Envelope              import Transfer__Envelope
from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from sgit_ai.objects.Vault__Object_Store         import Vault__Object_Store
from sgit_ai.objects.Vault__Ref_Manager          import Vault__Ref_Manager
from sgit_ai.objects.Vault__Commit               import Vault__Commit
from sgit_ai.sync.Vault__Storage                 import Vault__Storage
from sgit_ai.sync.Vault__Sub_Tree                import Vault__Sub_Tree
from sgit_ai.transfer.Simple_Token               import Simple_Token
from sgit_ai.transfer.Simple_Token__Wordlist     import Simple_Token__Wordlist

GCM_IV_BYTES = 12


class Vault__Transfer(Type_Safe):
    api    : API__Transfer
    crypto : Vault__Crypto

    def setup(self):
        self.api.setup()
        return self

    def collect_head_files(self, directory: str) -> dict:
        """Read committed files at HEAD.

        Returns a dict of {relative_path: bytes}.
        """
        storage  = Vault__Storage()
        sg_dir   = storage.sg_vault_dir(directory)
        vault_key_path = storage.vault_key_path(directory)

        if not os.path.isfile(vault_key_path):
            raise RuntimeError(f'No vault key found in {directory} — is this a vault?')

        with open(vault_key_path, 'r') as f:
            vault_key = f.read().strip()

        keys      = self.crypto.derive_keys_from_vault_key(vault_key)
        read_key  = keys['read_key_bytes']

        obj_store   = Vault__Object_Store(vault_path=sg_dir, crypto=self.crypto)
        ref_manager = Vault__Ref_Manager(vault_path=sg_dir, crypto=self.crypto)
        sub_tree    = Vault__Sub_Tree(crypto=self.crypto, obj_store=obj_store)

        from sgit_ai.crypto.PKI__Crypto import PKI__Crypto
        from sgit_ai.sync.Vault__Storage import SG_VAULT_DIR
        pki = PKI__Crypto()

        vault_commit = Vault__Commit(crypto=self.crypto, pki=pki,
                                     object_store=obj_store, ref_manager=ref_manager)

        local_config_path = storage.local_config_path(directory)
        if not os.path.isfile(local_config_path):
            raise RuntimeError(f'No local config found in {directory}')

        with open(local_config_path, 'r') as f:
            local_config = json.load(f)
        branch_id = local_config.get('my_branch_id', '')

        from sgit_ai.sync.Vault__Branch_Manager import Vault__Branch_Manager
        from sgit_ai.crypto.Vault__Key_Manager  import Vault__Key_Manager

        key_manager    = Vault__Key_Manager(vault_path=sg_dir, crypto=self.crypto, pki=pki)
        branch_manager = Vault__Branch_Manager(vault_path    = sg_dir,
                                               crypto        = self.crypto,
                                               key_manager   = key_manager,
                                               ref_manager   = ref_manager,
                                               storage       = storage)

        vault_id = keys['vault_id']
        branch_index_file_id = 'idx-pid-muw-' + self.crypto.derive_branch_index_file_id(
            read_key, vault_id)
        branch_index = branch_manager.load_branch_index(directory, branch_index_file_id, read_key)
        branch_meta  = branch_manager.get_branch_by_id(branch_index, branch_id)
        if not branch_meta:
            raise RuntimeError(f'Branch not found: {branch_id}')

        ref_id    = str(branch_meta.head_ref_id)
        commit_id = ref_manager.read_ref(ref_id, read_key)
        if not commit_id:
            return {}

        commit   = vault_commit.load_commit(commit_id, read_key)
        tree_id  = str(commit.tree_id)
        flat_map = sub_tree.flatten(tree_id, read_key)

        files = {}
        for path, entry in flat_map.items():
            blob_id    = entry['blob_id']
            ciphertext = obj_store.load(blob_id)
            plaintext  = self.crypto.decrypt(read_key, ciphertext)
            files[path] = plaintext
        return files

    def zip_files(self, files: dict) -> bytes:
        """Zip a dict of {relative_path: bytes} into a flat zip archive."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
            for path, content in sorted(files.items()):
                zf.writestr(path, content)
        return buf.getvalue()

    def encrypt_payload(self, key_bytes: bytes, plaintext: bytes) -> bytes:
        """Encrypt plaintext with AES-256-GCM. Returns iv + ciphertext+tag."""
        import os as _os
        iv     = _os.urandom(GCM_IV_BYTES)
        aesgcm = AESGCM(key_bytes)
        return iv + aesgcm.encrypt(iv, plaintext, None)

    def upload(self, encrypted_blob: bytes, transfer_id: str = None,
               content_type: str = 'application/octet-stream') -> str:
        """Upload encrypted blob to the Transfer API and return the transfer_id."""
        return self.api.upload_file(encrypted_blob, transfer_id=transfer_id,
                                    content_type=content_type)

    def receive(self, token_str: str) -> dict:
        """Download and decrypt a SG/Send transfer identified by a Simple Token.

        Returns a dict with:
            files        : dict[str, bytes]  — {relative_path: file_bytes}
            transfer_id  : str
            file_count   : int
        """
        from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token
        st          = Simple_Token(token=Safe_Str__Simple_Token(token_str))
        transfer_id = st.transfer_id()
        key_bytes   = st.aes_key()

        encrypted_blob   = self.api.download_file(transfer_id)
        decrypted        = self.crypto.decrypt(key_bytes, encrypted_blob)
        _, zip_bytes     = Transfer__Envelope().unpackage(decrypted)

        import io
        import zipfile as _zipfile
        files = {}
        buf   = io.BytesIO(zip_bytes)
        with _zipfile.ZipFile(buf, mode='r') as zf:
            for name in zf.namelist():
                files[name] = zf.read(name)

        return dict(files       = files,
                    transfer_id = transfer_id,
                    file_count  = len(files))

    def share(self, directory: str, token_str: str = None) -> dict:
        """Package and upload a vault snapshot, returning share metadata.

        Returns a dict with:
            token       : str  — the Simple Token
            transfer_id : str  — 12-char hex ID
            file_count  : int
            total_bytes : int  — size of zip (plaintext)
        """
        wordlist = Simple_Token__Wordlist()
        wordlist.setup()

        if token_str:
            from sgit_ai.safe_types.Safe_Str__Simple_Token import Safe_Str__Simple_Token
            token_val = Safe_Str__Simple_Token(token_str)
        else:
            token_val = wordlist.generate()

        st              = Simple_Token(token=token_val)
        derived_xfer_id = st.transfer_id()
        key_bytes       = st.aes_key()

        files        = self.collect_head_files(directory)
        zip_bytes    = self.zip_files(files)
        envelope     = Transfer__Envelope().package(zip_bytes, 'vault-snapshot.zip')
        encrypted    = self.encrypt_payload(key_bytes, envelope)

        actual_xfer_id = self.upload(encrypted, transfer_id=derived_xfer_id,
                                     content_type='application/zip')

        return dict(token           = str(token_val),
                    transfer_id     = actual_xfer_id,
                    derived_xfer_id = derived_xfer_id,
                    aes_key_hex     = key_bytes.hex(),
                    file_count      = len(files),
                    total_bytes     = len(zip_bytes))
