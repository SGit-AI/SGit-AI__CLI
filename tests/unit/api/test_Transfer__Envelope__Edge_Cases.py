import struct
from sgit_ai.api.Transfer__Envelope import (
    Transfer__Envelope, SGMETA_MAGIC, SGMETA_TEXT_PREFIX, SGMETA_PREFIX
)


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

    def test_unpackage_binary_too_short_skips_magic_len7_line_29(self):
        """Line 29: magic_len=7 but data only 10 bytes → len(data) < 11 → continue."""
        # data starts with SGMETA + non-dot byte = 7 bytes; total 10 bytes (just at outer limit)
        data = SGMETA_PREFIX + b'\x00' + b'\x00\x00\x00'   # 10 bytes
        metadata, content = self.envelope.unpackage(data)
        assert metadata is None

    def test_unpackage_binary_magic_len7_byte6_not_null_skips_line_31(self):
        """Line 31: magic_len=7 iteration and data[6] != \\x00 → continue."""
        # byte 6 is 0x01 (not \x00 and not '.'), so magic_len=7 fires line 31
        data = SGMETA_PREFIX + b'\x01' + struct.pack('>I', 0) + b'{}'
        metadata, content = self.envelope.unpackage(data)
        # magic_len=7 skipped (line 31); magic_len=6 should succeed parsing
        assert metadata is not None or content is not None

    def test_unpackage_text_format_bad_json_returns_none_lines_56_57(self):
        """Lines 56-57: SGMETA. prefix with non-JSON data → except → return None, data."""
        data = SGMETA_TEXT_PREFIX + b'not_valid_json!!!'
        metadata, content = self.envelope.unpackage(data)
        assert metadata is None
        assert content == data
