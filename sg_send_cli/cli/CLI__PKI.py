import base64
import json
import os
import sys
from getpass                                       import getpass
from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sg_send_cli.crypto.PKI__Crypto                import PKI__Crypto
from sg_send_cli.pki.PKI__Key_Store                import PKI__Key_Store
from sg_send_cli.pki.PKI__Keyring                  import PKI__Keyring
from sg_send_cli.safe_types.Safe_Str__Vault_Path   import Safe_Str__Vault_Path

DEFAULT_SG_SEND_DIR = '~/.sg-send'


class CLI__PKI(Type_Safe):
    crypto    : PKI__Crypto
    key_store : PKI__Key_Store
    keyring   : PKI__Keyring

    def setup(self, sg_send_dir: str = None):
        base = os.path.expanduser(sg_send_dir or DEFAULT_SG_SEND_DIR)
        self.key_store = PKI__Key_Store(keys_dir=os.path.join(base, 'keys'), crypto=self.crypto)
        self.keyring   = PKI__Keyring(keyring_dir=os.path.join(base, 'keyring'))
        return self

    def cmd_keygen(self, args):
        label      = getattr(args, 'label', '') or 'default'
        passphrase = os.environ.get('SG_SEND_PASSPHRASE') or getpass('Enter passphrase to protect private keys: ')
        if not passphrase:
            print('Error: passphrase is required.', file=sys.stderr)
            sys.exit(1)

        print('Generating RSA-4096 encryption key... ', end='', flush=True)
        metadata = self.key_store.generate_and_store(label, passphrase)
        print('done')

        print()
        print(f'Key pair created:')
        print(f'  Label:                {metadata["label"]}')
        print(f'  Encryption:           RSA-OAEP 4096-bit')
        print(f'  Signing:              ECDSA P-256')
        print(f'  Fingerprint:          {metadata["encryption_fingerprint"]}')
        print(f'  Signing fingerprint:  {metadata["signing_fingerprint"]}')

    def cmd_list(self, args):
        keys = self.key_store.list_keys()
        if not keys:
            print('No key pairs found.')
            return
        for key in keys:
            print(f'  {key["encryption_fingerprint"]}  {key["label"]}  ({key["algorithm"]} {key["key_size"]})')

    def cmd_export(self, args):
        bundle = self.key_store.export_public_bundle(args.fingerprint)
        if not bundle:
            print(f'Error: key {args.fingerprint} not found.', file=sys.stderr)
            sys.exit(1)
        print(json.dumps(bundle, indent=2))

    def cmd_delete(self, args):
        if not self.key_store.delete_key(args.fingerprint):
            print(f'Error: key {args.fingerprint} not found.', file=sys.stderr)
            sys.exit(1)
        print(f'Deleted key {args.fingerprint}')

    def cmd_import_contact(self, args):
        source = args.file
        if source == '-':
            data = sys.stdin.read()
        else:
            if not os.path.isfile(source):
                print(f'Error: file not found: {source}', file=sys.stderr)
                sys.exit(1)
            with open(source, 'r') as f:
                data = f.read()

        bundle = json.loads(data)
        enc_pub = self.crypto.import_public_key_pem(bundle['encrypt'])
        fp      = self.crypto.compute_fingerprint(enc_pub)

        sig_pem = bundle.get('sign', '')
        sig_fp  = ''
        if sig_pem:
            sig_pub = self.crypto.import_public_key_pem(sig_pem)
            sig_fp  = self.crypto.compute_fingerprint(sig_pub)

        label = bundle.get('label', '')
        self.keyring.add_contact(label=label, fingerprint=fp,
                                 public_key_pem=bundle['encrypt'],
                                 signing_key_pem=sig_pem,
                                 signing_fingerprint=sig_fp)
        print(f'Imported contact: {label or fp}')
        print(f'  Fingerprint: {fp}')

    def cmd_contacts(self, args):
        contacts = self.keyring.list_contacts()
        if not contacts:
            print('No contacts imported.')
            return
        for c in contacts:
            print(f'  {c["fingerprint"]}  {c.get("label", "")}')

    def cmd_sign(self, args):
        passphrase  = os.environ.get('SG_SEND_PASSPHRASE') or getpass('Enter passphrase: ')
        fingerprint = args.fingerprint
        loaded      = self.key_store.load_key_pair(fingerprint, passphrase)
        if not loaded:
            print(f'Error: key {fingerprint} not found.', file=sys.stderr)
            sys.exit(1)

        with open(args.file, 'rb') as f:
            data = f.read()

        sig_raw = self.crypto.sign(loaded['signing_private'], data)
        sig_b64 = base64.b64encode(sig_raw).decode()
        sig_fp  = loaded['metadata']['signing_fingerprint']

        sig_out = json.dumps(dict(signature=sig_b64, fingerprint=sig_fp), indent=2)
        sig_path = args.file + '.sig'
        with open(sig_path, 'w') as f:
            f.write(sig_out)
        print(f'Signature written to {sig_path}')

    def cmd_verify(self, args):
        with open(args.file, 'rb') as f:
            data = f.read()
        with open(args.signature, 'r') as f:
            sig_info = json.load(f)

        sig_raw = base64.b64decode(sig_info['signature'])
        sig_fp  = sig_info['fingerprint']

        contact = self.keyring.lookup_by_signing_fingerprint(sig_fp)
        if not contact:
            print(f'Error: no contact found with signing fingerprint {sig_fp}', file=sys.stderr)
            sys.exit(1)

        pub = self.crypto.import_public_key_pem(contact['signing_key_pem'])
        try:
            self.crypto.verify(pub, sig_raw, data)
            print(f'Signature valid (signer: {contact.get("label", sig_fp)})')
        except Exception:
            print('Signature INVALID', file=sys.stderr)
            sys.exit(1)

    def cmd_encrypt(self, args):
        with open(args.file, 'rb') as f:
            data = f.read()

        contact = self.keyring.get_contact(args.recipient)
        if not contact:
            print(f'Error: recipient {args.recipient} not found in contacts.', file=sys.stderr)
            sys.exit(1)

        enc_pub = self.crypto.import_public_key_pem(contact['public_key_pem'])

        signing_priv = None
        signing_fp   = None
        if args.fingerprint:
            passphrase = os.environ.get('SG_SEND_PASSPHRASE') or getpass('Enter passphrase for signing key: ')
            loaded     = self.key_store.load_key_pair(args.fingerprint, passphrase)
            if loaded:
                signing_priv = loaded['signing_private']
                signing_fp   = loaded['metadata']['signing_fingerprint']

        encoded  = self.crypto.hybrid_encrypt(enc_pub, data,
                                              signing_private_key=signing_priv,
                                              signing_fingerprint=signing_fp)
        out_path = args.file + '.enc'
        with open(out_path, 'w') as f:
            f.write(encoded)
        print(f'Encrypted to {out_path}')

    def cmd_decrypt(self, args):
        passphrase  = os.environ.get('SG_SEND_PASSPHRASE') or getpass('Enter passphrase: ')
        fingerprint = args.fingerprint

        loaded = self.key_store.load_key_pair(fingerprint, passphrase)
        if not loaded:
            print(f'Error: key {fingerprint} not found.', file=sys.stderr)
            sys.exit(1)

        with open(args.file, 'r') as f:
            encoded = f.read().strip()

        result = self.crypto.hybrid_decrypt(loaded['encryption_private'], encoded,
                                            contacts_keyring=self.keyring)
        out_path = args.file.removesuffix('.enc') if args.file.endswith('.enc') else args.file + '.dec'
        with open(out_path, 'w') as f:
            f.write(result['plaintext'])

        print(f'Decrypted to {out_path}')
        if result['signed']:
            if result['verified']:
                print(f'  Signature verified (signer: {result["signer"]})')
            else:
                print('  Signature present but UNVERIFIED')
