from osbot_utils.type_safe.Type_Safe        import Type_Safe
from sgit_ai.crypto.pki.PKI__Key_Store      import PKI__Key_Store
from sgit_ai.crypto.pki.PKI__Keyring        import PKI__Keyring

SOURCE__CONTACT = 'contact'
SOURCE__OWN_KEY = 'own key'


class PKI__Known_Keys(Type_Safe):
    """Every public key this machine knows: imported contacts, then its own key pairs.

    Encrypting to yourself (a machine provisioning itself) and checking your own
    signature are normal; before this, both needed your own bundle exported and
    imported back as a contact. Entries have the contact shape plus `source`."""
    keyring   : PKI__Keyring
    key_store : PKI__Key_Store

    def lookup_by_fingerprint(self, fingerprint: str) -> dict:
        contact = self.keyring.get_contact(fingerprint)
        if contact:
            return dict(contact, source=SOURCE__CONTACT)
        for metadata in self.key_store.list_keys():
            if metadata.get('encryption_fingerprint') == fingerprint:
                return self._own_key(metadata)
        return None

    def lookup_by_signing_fingerprint(self, signing_fingerprint: str) -> dict:
        contact = self.keyring.lookup_by_signing_fingerprint(signing_fingerprint)
        if contact:
            return dict(contact, source=SOURCE__CONTACT)
        for metadata in self.key_store.list_keys():
            if metadata.get('signing_fingerprint') == signing_fingerprint:
                return self._own_key(metadata)
        return None

    def _own_key(self, metadata: dict) -> dict:
        bundle = self.key_store.export_public_bundle(metadata['encryption_fingerprint'])
        if not bundle:
            return None
        return dict(label               = bundle.get('label', ''),
                    fingerprint         = bundle['fingerprint'],
                    public_key_pem      = bundle['encrypt'],
                    signing_key_pem     = bundle['sign'],
                    signing_fingerprint = bundle['signing_fingerprint'],
                    source              = SOURCE__OWN_KEY)
