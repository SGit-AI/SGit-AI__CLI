import base64
import json
import os
import sys
from getpass                                       import getpass
from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.crypto.PKI__Crypto                import PKI__Crypto
from sgit_ai.crypto.pki.PKI__Key_Store                import PKI__Key_Store
from sgit_ai.crypto.pki.PKI__Keyring                  import PKI__Keyring
from sgit_ai.crypto.pki.PKI__Known_Keys               import PKI__Known_Keys
from sgit_ai.crypto.Vault__Secret_File                import Vault__Secret_File
from sgit_ai.safe_types.Safe_Str__Vault_Path   import Safe_Str__Vault_Path

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
        loaded = self._load_key_pair_or_exit(args.fingerprint, 'Enter passphrase: ')

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

    def known_keys(self) -> PKI__Known_Keys:
        return PKI__Known_Keys(keyring=self.keyring, key_store=self.key_store)

    def cmd_verify(self, args):
        """Exit 0 only for a valid signature by a known key. The signing fingerprint is
        printed with the label (a label is whatever the importer typed; scripts pin the
        fingerprint), and --json gives scripts both without parsing text."""
        as_json = getattr(args, 'json', False)
        with open(args.file, 'rb') as f:
            data = f.read()
        with open(args.signature, 'r') as f:
            sig_info = json.load(f)

        sig_raw = base64.b64decode(sig_info['signature'])
        sig_fp  = sig_info['fingerprint']
        signer  = self.known_keys().lookup_by_signing_fingerprint(sig_fp)
        report  = dict(valid=False, signing_fingerprint=sig_fp, signer_label=None, signer_source=None)
        if not signer:
            self._verify_failed(report, f'no contact or own key with signing fingerprint {sig_fp}', as_json)

        report.update(signer_label=signer.get('label', ''), signer_source=signer['source'])
        try:
            self.crypto.verify(self.crypto.import_public_key_pem(signer['signing_key_pem']), sig_raw, data)
        except Exception:
            self._verify_failed(report, 'Signature INVALID', as_json)
        report['valid'] = True
        if as_json:
            print(json.dumps(report, indent=2))
        else:
            print(f'Signature valid (signer: {report["signer_label"] or "(no label)"}, {sig_fp}, {signer["source"]})')

    def _verify_failed(self, report: dict, message: str, as_json: bool):
        if as_json:
            print(json.dumps(dict(report, error=message), indent=2))
        else:
            print(message if message == 'Signature INVALID' else f'Error: {message}', file=sys.stderr)
        sys.exit(1)

    def cmd_encrypt(self, args):
        with open(args.file, 'rb') as f:
            data = f.read()

        recipient = self.known_keys().lookup_by_fingerprint(args.recipient)
        if not recipient:
            print(f'Error: recipient {args.recipient} is neither a contact nor one of your key pairs.',
                  file=sys.stderr)
            sys.exit(1)

        enc_pub = self.crypto.import_public_key_pem(recipient['public_key_pem'])

        signing_priv = None
        signing_fp   = None
        if args.fingerprint:                            # asked to sign: never fall back to unsigned
            loaded = self._load_key_pair_or_exit(args.fingerprint, 'Enter passphrase for signing key: ')
            signing_priv = loaded['signing_private']
            signing_fp   = loaded['metadata']['signing_fingerprint']

        encoded  = self.crypto.hybrid_encrypt(enc_pub, data,
                                              signing_private_key=signing_priv,
                                              signing_fingerprint=signing_fp)
        out_path = getattr(args, 'output', None) or args.file + '.enc'
        with open(out_path, 'w') as f:
            f.write(encoded)
        print(f'Encrypted to {out_path}')

    def cmd_decrypt(self, args):
        """Writes the exact plaintext bytes (0600) next to the input with .enc removed, to
        --output PATH, or to stdout with --output - (messages then go to stderr), so a
        script need not leave a plaintext file on disk."""
        loaded  = self._load_key_pair_or_exit(args.fingerprint, 'Enter passphrase: ')
        with open(args.file, 'r') as f:
            encoded = f.read().strip()

        result   = self.crypto.hybrid_decrypt(loaded['encryption_private'], encoded,
                                              contacts_keyring=self.known_keys())
        out_path = getattr(args, 'output', None) or (args.file.removesuffix('.enc') if args.file.endswith('.enc')
                                                     else args.file + '.dec')
        notes    = sys.stdout
        if out_path == '-':
            sys.stdout.buffer.write(result['plaintext_bytes'])
            sys.stdout.flush()
            notes = sys.stderr
        else:
            Vault__Secret_File().write(out_path, result['plaintext_bytes'])
            print(f'Decrypted to {out_path}')
        if result['signed']:
            if result['verified']:
                print(f'  Signature verified (signer: {result["signer"]}, {result["signing_fingerprint"]})', file=notes)
            else:
                print(f'  Signature present but UNVERIFIED ({result["signing_fingerprint"]})', file=notes)

    def _load_key_pair_or_exit(self, fingerprint: str, prompt: str) -> dict:
        passphrase = os.environ.get('SG_SEND_PASSPHRASE') or getpass(prompt)
        try:
            loaded = self.key_store.load_key_pair(fingerprint, passphrase)
        except (ValueError, TypeError):
            print(f'Error: wrong passphrase for key {fingerprint}.', file=sys.stderr)
            sys.exit(1)
        if not loaded:
            print(f'Error: key {fingerprint} not found.', file=sys.stderr)
            sys.exit(1)
        return loaded
