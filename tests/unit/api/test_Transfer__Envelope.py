from sgit_ai.network.api.Transfer__Envelope import Transfer__Envelope, SGMETA_MAGIC, SGMETA_TEXT_PREFIX, SGMETA_PREFIX


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

    def test_unpackage_text_format_from_web(self):
        # The SG/Send web app sends: SGMETA. + self-delimiting JSON + content
        # (no null byte, no 4-byte length prefix — JSON is self-delimiting)
        # This is the exact format observed from sgit receive dodge-amber-8030:
        #   SGMETA.{"filename":"message-2026-04-16T14-10-28.txt"}abc
        data = b'SGMETA.{"filename":"message-2026-04-16T14-10-28.txt"}abc'
        metadata, content = self.envelope.unpackage(data)
        assert metadata == {'filename': 'message-2026-04-16T14-10-28.txt'}
        assert content == b'abc'

    def test_unpackage_text_format_binary_content(self):
        # Text-format envelope with binary (non-UTF-8) content after the JSON
        data = SGMETA_TEXT_PREFIX + b'{"filename":"photo.jpg"}' + bytes(range(16))
        metadata, content = self.envelope.unpackage(data)
        assert metadata == {'filename': 'photo.jpg'}
        assert content == bytes(range(16))

    def test_unpackage_text_format_empty_content(self):
        data = b'SGMETA.{"filename":"empty.txt"}'
        metadata, content = self.envelope.unpackage(data)
        assert metadata == {'filename': 'empty.txt'}
        assert content == b''

    def test_unpackage_6byte_magic_variant(self):
        # Some senders use 6-byte magic (SGMETA, no null byte) + 4-byte length + JSON + content
        # This is the format observed from thorn-raven-0356: SGMETA + \x00\x00\x00\x2E + JSON
        meta_bytes = b'{"filename":"message-2026-04-16T16-48-54.txt"}'
        meta_len   = len(meta_bytes).to_bytes(4, 'big')   # \x00\x00\x00\x2E = 46
        data       = SGMETA_PREFIX + meta_len + meta_bytes + b'Hi, the token is: abc'
        metadata, content = self.envelope.unpackage(data)
        assert metadata == {'filename': 'message-2026-04-16T16-48-54.txt'}
        assert content == b'Hi, the token is: abc'

    def test_unpackage_corrupted_meta_length(self):
        packed = SGMETA_MAGIC + b'\xff\xff\xff\xff' + b'data'
        metadata, content = self.envelope.unpackage(packed)
        assert metadata is None
        assert content == packed
