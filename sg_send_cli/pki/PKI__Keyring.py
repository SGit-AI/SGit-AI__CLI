import json
import os
from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sg_send_cli.safe_types.Safe_Str__Vault_Path   import Safe_Str__Vault_Path


class PKI__Keyring(Type_Safe):
    keyring_dir : Safe_Str__Vault_Path = None

    def add_contact(self, label: str, fingerprint: str,
                    public_key_pem: str, signing_key_pem: str = '',
                    signing_fingerprint: str = '') -> None:
        contact = dict(label               = label,
                       fingerprint         = fingerprint,
                       signing_fingerprint = signing_fingerprint,
                       public_key_pem      = public_key_pem,
                       signing_key_pem     = signing_key_pem)
        path = self._contact_path(fingerprint)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(contact, f, indent=2)

    def get_contact(self, fingerprint: str) -> dict:
        path = self._contact_path(fingerprint)
        if not os.path.isfile(path):
            return None
        with open(path, 'r') as f:
            return json.load(f)

    def remove_contact(self, fingerprint: str) -> bool:
        path = self._contact_path(fingerprint)
        if not os.path.isfile(path):
            return False
        os.remove(path)
        return True

    def list_contacts(self) -> list:
        keyring_dir = str(self.keyring_dir) if self.keyring_dir else ''
        if not keyring_dir or not os.path.isdir(keyring_dir):
            return []
        contacts = []
        for filename in sorted(os.listdir(keyring_dir)):
            if filename.endswith('.json'):
                path = os.path.join(keyring_dir, filename)
                with open(path, 'r') as f:
                    contacts.append(json.load(f))
        return contacts

    def lookup_by_signing_fingerprint(self, signing_fingerprint: str) -> dict:
        for contact in self.list_contacts():
            if contact.get('signing_fingerprint') == signing_fingerprint:
                return contact
        return None

    def _contact_path(self, fingerprint: str) -> str:
        safe_name = fingerprint.replace(':', '_')
        return os.path.join(str(self.keyring_dir), f'{safe_name}.json')
