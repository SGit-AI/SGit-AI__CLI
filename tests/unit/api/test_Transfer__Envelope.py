from sg_send_cli.api.Transfer__Envelope import Transfer__Envelope, SGMETA_MAGIC


class Test_Transfer__Envelope:

    def setup_method(self):
        self.envelope = Transfer__Envelope()

    def test_package_and_unpackage_roundtrip(self):
        content  = b'Hello, world!'
        filename = 'test.txt'
        packed   = self.envelope.package(content, filename)
        metadata, unpacked_content = self.envelope.unpackage(packed)
        assert metadata == {'filename': 'test.txt'}
        assert unpacked_content == content

    def test_package_starts_with_magic(self):
        packed = self.envelope.package(b'data', 'file.bin')
        assert packed[:7] == SGMETA_MAGIC

    def test_unpackage_raw_bytes_no_envelope(self):
        raw = b'just some raw bytes without envelope'
        metadata, content = self.envelope.unpackage(raw)
        assert metadata is None
        assert content == raw

    def test_unpackage_too_short(self):
        metadata, content = self.envelope.unpackage(b'short')
        assert metadata is None
        assert content == b'short'

    def test_package_empty_content(self):
        packed = self.envelope.package(b'', 'empty.txt')
        metadata, content = self.envelope.unpackage(packed)
        assert metadata == {'filename': 'empty.txt'}
        assert content == b''

    def test_package_binary_content(self):
        binary_content = bytes(range(256))
        packed = self.envelope.package(binary_content, 'binary.bin')
        metadata, content = self.envelope.unpackage(packed)
        assert metadata == {'filename': 'binary.bin'}
        assert content == binary_content

    def test_package_unicode_filename(self):
        content = b'data'
        packed = self.envelope.package(content, 'rapport-2026.pdf')
        metadata, unpacked = self.envelope.unpackage(packed)
        assert metadata['filename'] == 'rapport-2026.pdf'
        assert unpacked == content

    def test_unpackage_corrupted_meta_length(self):
        packed = SGMETA_MAGIC + b'\xff\xff\xff\xff' + b'data'
        metadata, content = self.envelope.unpackage(packed)
        assert metadata is None
        assert content == packed
