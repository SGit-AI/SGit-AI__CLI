"""Shared fixtures for CLI unit tests.

Implements F1 / F2 from
  team/villager/dev/v0.10.30__shared-fixtures-design.md (Section 2).

F1 `pki_keypair_snapshot` (module scope): builds one RSA-4096 + ECDSA-P256
keypair once per module via `CLI__PKI().setup()` +
`key_store.generate_and_store('export-test', 'test-pass')`.  Returns the
snapshot directory path plus metadata.  Also caches a contact bundle
(encrypt + sign public PEMs) for the Import_Contacts class.

F2 `pki_workdir` (function scope factory): copies the F1 snapshot's
`keys/` and `keyring/` into a fresh tempdir and returns a wired
`CLI__PKI` instance.  Build cost ~3 ms.

Mutation contract: tests never touch the snapshot directory.  All
mutation happens inside the per-test workdir returned by the factory.
"""
import os
import shutil
import tempfile

import pytest

from sgit_ai.cli.CLI__PKI import CLI__PKI


@pytest.fixture(scope='module')
def pki_keypair_snapshot():
    """Build one RSA-4096 + ECDSA-P256 keypair, snapshot to disk."""
    snap_dir = tempfile.mkdtemp(prefix='pki_snapshot_')
    try:
        cli_pki  = CLI__PKI()
        cli_pki.setup(sg_send_dir=snap_dir)
        metadata = cli_pki.key_store.generate_and_store('export-test', 'test-pass')

        # Contact bundle for Import_Contacts: a real keypair exported
        # to PEM (no private material kept).
        crypto                 = cli_pki.crypto
        enc_priv, enc_pub      = crypto.generate_encryption_key_pair()
        sig_priv, sig_pub      = crypto.generate_signing_key_pair()
        contact_bundle         = dict(
            encrypt = crypto.export_public_key_pem(enc_pub),
            sign    = crypto.export_public_key_pem(sig_pub),
            label   = 'alice',
        )

        yield {
            'snapshot_dir'   : snap_dir,
            'metadata'       : metadata,
            'fingerprint'    : metadata['encryption_fingerprint'],
            'passphrase'     : 'test-pass',
            'contact_bundle' : contact_bundle,
        }
    finally:
        shutil.rmtree(snap_dir, ignore_errors=True)


@pytest.fixture
def pki_workdir(pki_keypair_snapshot):
    """Factory: copytree the F1 snapshot into a fresh tempdir per call."""
    created = []

    def make():
        tmp_dir = tempfile.mkdtemp(prefix='pki_workdir_')
        created.append(tmp_dir)
        for subdir in ('keys', 'keyring'):
            src = os.path.join(pki_keypair_snapshot['snapshot_dir'], subdir)
            dst = os.path.join(tmp_dir, subdir)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
        cli_pki = CLI__PKI()
        cli_pki.setup(sg_send_dir=tmp_dir)
        return tmp_dir, cli_pki

    yield make

    for tmp_dir in created:
        shutil.rmtree(tmp_dir, ignore_errors=True)
