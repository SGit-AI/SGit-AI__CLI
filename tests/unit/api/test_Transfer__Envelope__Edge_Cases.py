import struct
from sg_send_cli.api.Transfer__Envelope import Transfer__Envelope, SGMETA_MAGIC


class Test_Transfer__Envelope__Edge_Cases:

    def setup_method(self):
        self.envelope = Transfer__Envelope()

    def test_package__large_metadata_filename(self):
        filename = 'a' * 10000 + '.txt'
        packed   = self.envelope.package(b'content', filename)
        metadata, content = self.envelope.unpackage(packed)
        assert metadata['filename'] == filename
        assert content == b'content'

    def test_unpackage__truncated_at_magic(self):
        truncated = SGMETA_MAGIC[:4]
        metadata, content = self.envelope.unpackage(truncated)
        assert metadata is None
        assert content == truncated

    def test_unpackage__truncated_at_length(self):
        truncated = SGMETA_MAGIC + b'\x00'
        metadata, content = self.envelope.unpackage(truncated)
        assert metadata is None
        assert content == truncated

    def test_unpackage__zero_length_metadata(self):
        # BUG-001: Zero-length metadata causes empty bytes json.loads('') to fail,
        # so unpackage falls through to the except branch returning None + full data
        data = SGMETA_MAGIC + struct.pack('>I', 0) + b'content-after'
        metadata, content = self.envelope.unpackage(data)
        assert metadata is None
        assert content == data

    def test_package__binary_filename_chars(self):
        packed   = self.envelope.package(b'data', 'file-name_v2.tar.gz')
        metadata, content = self.envelope.unpackage(packed)
        assert metadata['filename'] == 'file-name_v2.tar.gz'

    def test_package__large_content(self):
        large = b'\xAB' * 1_000_000
        packed = self.envelope.package(large, 'big.bin')
        metadata, content = self.envelope.unpackage(packed)
        assert metadata['filename'] == 'big.bin'
        assert content == large

    def test_unpackage__invalid_json_metadata(self):
        invalid_meta = b'not-json{{'
        meta_len     = struct.pack('>I', len(invalid_meta))
        data         = SGMETA_MAGIC + meta_len + invalid_meta + b'content'
        metadata, content = self.envelope.unpackage(data)
        assert metadata is None

    def test_package__unicode_filename(self):
        packed   = self.envelope.package(b'data', 'rapport-2026.pdf')
        metadata, _ = self.envelope.unpackage(packed)
        assert metadata['filename'] == 'rapport-2026.pdf'

    def test_magic_bytes_value(self):
        assert SGMETA_MAGIC == b'SGMETA\x00'

    def test_package_unpackage__empty_filename(self):
        packed   = self.envelope.package(b'data', '')
        metadata, content = self.envelope.unpackage(packed)
        assert metadata['filename'] == ''
        assert content == b'data'
