import json
import os
import tempfile
import shutil
import pytest
from types         import SimpleNamespace
from unittest.mock import patch

from sg_send_cli.crypto.PKI__Crypto import PKI__Crypto
from sg_send_cli.pki.PKI__Key_Store import PKI__Key_Store
from sg_send_cli.pki.PKI__Keyring   import PKI__Keyring
from sg_send_cli.cli.CLI__PKI       import CLI__PKI
from sg_send_cli.cli.CLI__Main      import CLI__Main


class Test_CLI__PKI_Setup:

    def test_setup_creates_key_store_and_keyring(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            cli_pki = CLI__PKI()
            cli_pki.setup(sg_send_dir=tmp_dir)
            assert str(cli_pki.key_store.keys_dir) == os.path.join(tmp_dir, 'keys')
            assert str(cli_pki.keyring.keyring_dir) == os.path.join(tmp_dir, 'keyring')
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_setup_returns_self(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            cli_pki = CLI__PKI()
            result  = cli_pki.setup(sg_send_dir=tmp_dir)
            assert result is cli_pki
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class Test_CLI__PKI_Keygen:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.cli_pki = CLI__PKI()
        self.cli_pki.setup(sg_send_dir=self.tmp_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_keygen_creates_key_pair(self, capsys):
        args = SimpleNamespace(label='test-key')
        with patch.dict(os.environ, {'SG_SEND_PASSPHRASE': 'test-pass'}):
            self.cli_pki.cmd_keygen(args)
        output = capsys.readouterr().out
        assert 'Key pair created'      in output
        assert 'RSA-OAEP 4096-bit'     in output
        assert 'ECDSA P-256'           in output
        assert 'Fingerprint:'          in output
        assert 'Signing fingerprint:'  in output

    def test_keygen_default_label(self, capsys):
        args = SimpleNamespace(label='')
        with patch.dict(os.environ, {'SG_SEND_PASSPHRASE': 'test-pass'}):
            self.cli_pki.cmd_keygen(args)
        keys = self.cli_pki.key_store.list_keys()
        assert len(keys) == 1
        assert keys[0]['label'] == 'default'

    def test_keygen_empty_passphrase_exits(self):
        args = SimpleNamespace(label='test')
        with patch.dict(os.environ, {'SG_SEND_PASSPHRASE': ''}):
            with patch('sg_send_cli.cli.CLI__PKI.getpass', return_value=''):
                with pytest.raises(SystemExit) as exc_info:
                    self.cli_pki.cmd_keygen(args)
                assert exc_info.value.code == 1


class Test_CLI__PKI_List:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.cli_pki = CLI__PKI()
        self.cli_pki.setup(sg_send_dir=self.tmp_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_list_empty(self, capsys):
        self.cli_pki.cmd_list(SimpleNamespace())
        output = capsys.readouterr().out
        assert 'No key pairs found' in output

    def test_list_after_keygen(self, capsys):
        with patch.dict(os.environ, {'SG_SEND_PASSPHRASE': 'test-pass'}):
            self.cli_pki.cmd_keygen(SimpleNamespace(label='my-key'))
        capsys.readouterr()

        self.cli_pki.cmd_list(SimpleNamespace())
        output = capsys.readouterr().out
        assert 'sha256:' in output
        assert 'my-key'  in output


class Test_CLI__PKI_Export_Delete:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.cli_pki = CLI__PKI()
        self.cli_pki.setup(sg_send_dir=self.tmp_dir)
        with patch.dict(os.environ, {'SG_SEND_PASSPHRASE': 'test-pass'}):
            self.metadata = self.cli_pki.key_store.generate_and_store('export-test', 'test-pass')
        self.fingerprint = self.metadata['encryption_fingerprint']

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_export_public_bundle(self, capsys):
        args = SimpleNamespace(fingerprint=self.fingerprint)
        self.cli_pki.cmd_export(args)
        output = capsys.readouterr().out
        bundle = json.loads(output)
        assert bundle['v']     == 1
        assert 'encrypt'       in bundle
        assert 'sign'          in bundle
        assert bundle['label'] == 'export-test'

    def test_export_not_found_exits(self):
        args = SimpleNamespace(fingerprint='sha256:0000000000000000')
        with pytest.raises(SystemExit) as exc_info:
            self.cli_pki.cmd_export(args)
        assert exc_info.value.code == 1

    def test_delete_existing_key(self, capsys):
        args = SimpleNamespace(fingerprint=self.fingerprint)
        self.cli_pki.cmd_delete(args)
        output = capsys.readouterr().out
        assert 'Deleted key' in output

    def test_delete_not_found_exits(self):
        args = SimpleNamespace(fingerprint='sha256:0000000000000000')
        with pytest.raises(SystemExit) as exc_info:
            self.cli_pki.cmd_delete(args)
        assert exc_info.value.code == 1


class Test_CLI__PKI_Import_Contacts:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.cli_pki = CLI__PKI()
        self.cli_pki.setup(sg_send_dir=self.tmp_dir)
        self.crypto  = self.cli_pki.crypto

        self.enc_priv, self.enc_pub = self.crypto.generate_encryption_key_pair()
        self.sig_priv, self.sig_pub = self.crypto.generate_signing_key_pair()

        self.bundle = dict(
            encrypt = self.crypto.export_public_key_pem(self.enc_pub),
            sign    = self.crypto.export_public_key_pem(self.sig_pub),
            label   = 'alice'
        )

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_import_from_file(self, capsys):
        bundle_path = os.path.join(self.tmp_dir, 'alice.json')
        with open(bundle_path, 'w') as f:
            json.dump(self.bundle, f)

        args = SimpleNamespace(file=bundle_path)
        self.cli_pki.cmd_import_contact(args)
        output = capsys.readouterr().out
        assert 'Imported contact' in output
        assert 'alice'            in output

    def test_import_from_stdin(self, capsys):
        args = SimpleNamespace(file='-')
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.read.return_value = json.dumps(self.bundle)
            self.cli_pki.cmd_import_contact(args)
        output = capsys.readouterr().out
        assert 'Imported contact' in output

    def test_import_file_not_found_exits(self):
        args = SimpleNamespace(file='/nonexistent/file.json')
        with pytest.raises(SystemExit) as exc_info:
            self.cli_pki.cmd_import_contact(args)
        assert exc_info.value.code == 1

    def test_contacts_empty(self, capsys):
        self.cli_pki.cmd_contacts(SimpleNamespace())
        output = capsys.readouterr().out
        assert 'No contacts imported' in output

    def test_contacts_after_import(self, capsys):
        bundle_path = os.path.join(self.tmp_dir, 'alice.json')
        with open(bundle_path, 'w') as f:
            json.dump(self.bundle, f)
        self.cli_pki.cmd_import_contact(SimpleNamespace(file=bundle_path))
        capsys.readouterr()

        self.cli_pki.cmd_contacts(SimpleNamespace())
        output = capsys.readouterr().out
        assert 'sha256:' in output


class Test_CLI__PKI_Sign_Verify:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.cli_pki = CLI__PKI()
        self.cli_pki.setup(sg_send_dir=self.tmp_dir)
        self.passphrase = 'test-pass'
        self.metadata   = self.cli_pki.key_store.generate_and_store('signer', self.passphrase)
        self.enc_fp     = self.metadata['encryption_fingerprint']
        self.sig_fp     = self.metadata['signing_fingerprint']

        self.test_file = os.path.join(self.tmp_dir, 'message.txt')
        with open(self.test_file, 'w') as f:
            f.write('hello world')

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_sign_creates_sig_file(self, capsys):
        args = SimpleNamespace(file=self.test_file, fingerprint=self.enc_fp)
        with patch.dict(os.environ, {'SG_SEND_PASSPHRASE': self.passphrase}):
            self.cli_pki.cmd_sign(args)
        output = capsys.readouterr().out
        assert 'Signature written to' in output
        assert os.path.isfile(self.test_file + '.sig')

    def test_sign_then_verify(self, capsys):
        args = SimpleNamespace(file=self.test_file, fingerprint=self.enc_fp)
        with patch.dict(os.environ, {'SG_SEND_PASSPHRASE': self.passphrase}):
            self.cli_pki.cmd_sign(args)
        capsys.readouterr()

        bundle = self.cli_pki.key_store.export_public_bundle(self.enc_fp)
        enc_pub = self.cli_pki.crypto.import_public_key_pem(bundle['encrypt'])
        sig_pub_pem = bundle['sign']
        sig_pub = self.cli_pki.crypto.import_public_key_pem(sig_pub_pem)
        fp = self.cli_pki.crypto.compute_fingerprint(enc_pub)
        sig_fp_actual = self.cli_pki.crypto.compute_fingerprint(sig_pub)

        self.cli_pki.keyring.add_contact(
            label='signer', fingerprint=fp,
            public_key_pem=bundle['encrypt'],
            signing_key_pem=sig_pub_pem,
            signing_fingerprint=sig_fp_actual
        )

        verify_args = SimpleNamespace(file=self.test_file, signature=self.test_file + '.sig')
        self.cli_pki.cmd_verify(verify_args)
        output = capsys.readouterr().out
        assert 'Signature valid' in output

    def test_sign_key_not_found_exits(self):
        args = SimpleNamespace(file=self.test_file, fingerprint='sha256:0000000000000000')
        with patch.dict(os.environ, {'SG_SEND_PASSPHRASE': self.passphrase}):
            with pytest.raises(SystemExit) as exc_info:
                self.cli_pki.cmd_sign(args)
            assert exc_info.value.code == 1

    def test_verify_no_contact_exits(self):
        args = SimpleNamespace(file=self.test_file, fingerprint=self.enc_fp)
        with patch.dict(os.environ, {'SG_SEND_PASSPHRASE': self.passphrase}):
            self.cli_pki.cmd_sign(args)

        verify_args = SimpleNamespace(file=self.test_file, signature=self.test_file + '.sig')
        with pytest.raises(SystemExit) as exc_info:
            self.cli_pki.cmd_verify(verify_args)
        assert exc_info.value.code == 1


class Test_CLI__PKI_Encrypt_Decrypt:

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.cli_pki = CLI__PKI()
        self.cli_pki.setup(sg_send_dir=self.tmp_dir)
        self.passphrase = 'test-pass'

        self.sender_meta   = self.cli_pki.key_store.generate_and_store('sender',   self.passphrase)
        self.receiver_meta = self.cli_pki.key_store.generate_and_store('receiver', self.passphrase)
        self.sender_fp     = self.sender_meta['encryption_fingerprint']
        self.receiver_fp   = self.receiver_meta['encryption_fingerprint']

        sender_bundle = self.cli_pki.key_store.export_public_bundle(self.sender_fp)
        receiver_bundle = self.cli_pki.key_store.export_public_bundle(self.receiver_fp)

        crypto = self.cli_pki.crypto
        enc_pub = crypto.import_public_key_pem(receiver_bundle['encrypt'])
        self.cli_pki.keyring.add_contact(
            label='receiver', fingerprint=self.receiver_fp,
            public_key_pem=receiver_bundle['encrypt'],
            signing_key_pem=receiver_bundle.get('sign', ''),
            signing_fingerprint=self.receiver_meta['signing_fingerprint']
        )

        sig_pub = crypto.import_public_key_pem(sender_bundle['sign'])
        sig_fp  = crypto.compute_fingerprint(sig_pub)
        self.cli_pki.keyring.add_contact(
            label='sender', fingerprint=self.sender_fp,
            public_key_pem=sender_bundle['encrypt'],
            signing_key_pem=sender_bundle['sign'],
            signing_fingerprint=sig_fp
        )

        self.test_file = os.path.join(self.tmp_dir, 'secret.txt')
        with open(self.test_file, 'w') as f:
            f.write('top secret message')

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_encrypt_creates_enc_file(self, capsys):
        args = SimpleNamespace(file=self.test_file, recipient=self.receiver_fp, fingerprint=None)
        self.cli_pki.cmd_encrypt(args)
        output = capsys.readouterr().out
        assert 'Encrypted to' in output
        assert os.path.isfile(self.test_file + '.enc')

    def test_encrypt_recipient_not_found_exits(self):
        args = SimpleNamespace(file=self.test_file, recipient='sha256:0000000000000000', fingerprint=None)
        with pytest.raises(SystemExit) as exc_info:
            self.cli_pki.cmd_encrypt(args)
        assert exc_info.value.code == 1

    def test_encrypt_then_decrypt(self, capsys):
        args = SimpleNamespace(file=self.test_file, recipient=self.receiver_fp, fingerprint=self.sender_fp)
        with patch.dict(os.environ, {'SG_SEND_PASSPHRASE': self.passphrase}):
            self.cli_pki.cmd_encrypt(args)
        capsys.readouterr()

        enc_file = self.test_file + '.enc'
        dec_args = SimpleNamespace(file=enc_file, fingerprint=self.receiver_fp)
        with patch.dict(os.environ, {'SG_SEND_PASSPHRASE': self.passphrase}):
            self.cli_pki.cmd_decrypt(dec_args)
        output = capsys.readouterr().out
        assert 'Decrypted to' in output

        dec_file = self.test_file
        with open(dec_file, 'r') as f:
            assert f.read() == 'top secret message'

    def test_decrypt_key_not_found_exits(self):
        with open(self.test_file + '.enc', 'w') as f:
            f.write('dummy')
        args = SimpleNamespace(file=self.test_file + '.enc', fingerprint='sha256:0000000000000000')
        with patch.dict(os.environ, {'SG_SEND_PASSPHRASE': self.passphrase}):
            with pytest.raises(SystemExit) as exc_info:
                self.cli_pki.cmd_decrypt(args)
            assert exc_info.value.code == 1

    def test_encrypt_with_signing(self, capsys):
        args = SimpleNamespace(file=self.test_file, recipient=self.receiver_fp, fingerprint=self.sender_fp)
        with patch.dict(os.environ, {'SG_SEND_PASSPHRASE': self.passphrase}):
            self.cli_pki.cmd_encrypt(args)
        output = capsys.readouterr().out
        assert 'Encrypted to' in output

        enc_file = self.test_file + '.enc'
        dec_args = SimpleNamespace(file=enc_file, fingerprint=self.receiver_fp)
        with patch.dict(os.environ, {'SG_SEND_PASSPHRASE': self.passphrase}):
            self.cli_pki.cmd_decrypt(dec_args)
        output = capsys.readouterr().out
        assert 'Signature verified' in output


class Test_CLI__Main_PKI_Parser:

    def test_pki_keygen_command_registered(self):
        cli_main = CLI__Main()
        parser   = cli_main.build_parser()
        args     = parser.parse_args(['pki', 'keygen', '--label', 'test'])
        assert args.command     == 'pki'
        assert args.pki_command == 'keygen'
        assert args.label       == 'test'

    def test_pki_list_command_registered(self):
        cli_main = CLI__Main()
        parser   = cli_main.build_parser()
        args     = parser.parse_args(['pki', 'list'])
        assert args.command     == 'pki'
        assert args.pki_command == 'list'

    def test_pki_encrypt_command_registered(self):
        cli_main = CLI__Main()
        parser   = cli_main.build_parser()
        args     = parser.parse_args(['pki', 'encrypt', 'file.txt', '--recipient', 'sha256:abc123'])
        assert args.command   == 'pki'
        assert args.recipient == 'sha256:abc123'

    def test_pki_decrypt_command_registered(self):
        cli_main = CLI__Main()
        parser   = cli_main.build_parser()
        args     = parser.parse_args(['pki', 'decrypt', 'file.enc', '--fingerprint', 'sha256:abc123'])
        assert args.command     == 'pki'
        assert args.fingerprint == 'sha256:abc123'

    def test_pki_sign_command_registered(self):
        cli_main = CLI__Main()
        parser   = cli_main.build_parser()
        args     = parser.parse_args(['pki', 'sign', 'file.txt', '--fingerprint', 'sha256:abc123'])
        assert args.command     == 'pki'
        assert args.fingerprint == 'sha256:abc123'

    def test_pki_verify_command_registered(self):
        cli_main = CLI__Main()
        parser   = cli_main.build_parser()
        args     = parser.parse_args(['pki', 'verify', 'file.txt', 'file.txt.sig'])
        assert args.command   == 'pki'
        assert args.file      == 'file.txt'
        assert args.signature == 'file.txt.sig'

    def test_pki_import_command_registered(self):
        cli_main = CLI__Main()
        parser   = cli_main.build_parser()
        args     = parser.parse_args(['pki', 'import', 'bundle.json'])
        assert args.command == 'pki'
        assert args.file    == 'bundle.json'

    def test_pki_no_subcommand_shows_help(self):
        cli_main = CLI__Main()
        with pytest.raises(SystemExit) as exc_info:
            cli_main.run(['pki'])
        assert exc_info.value.code == 0
