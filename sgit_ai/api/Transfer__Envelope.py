import json
import struct
from osbot_utils.type_safe.Type_Safe import Type_Safe

SGMETA_MAGIC       = bytes([0x53, 0x47, 0x4D, 0x45, 0x54, 0x41, 0x00])  # SGMETA\0 — binary format
SGMETA_TEXT_PREFIX = b'SGMETA.'                                            # text-mode variant from web


class Transfer__Envelope(Type_Safe):

    def package(self, content: bytes, filename: str) -> bytes:
        meta_bytes = json.dumps({"filename": filename}).encode('utf-8')
        meta_len   = struct.pack('>I', len(meta_bytes))
        return SGMETA_MAGIC + meta_len + meta_bytes + content

    def unpackage(self, data: bytes) -> tuple:
        # ── Binary format: SGMETA\0 + 4-byte big-endian length + JSON + content ──
        if (len(data) >= len(SGMETA_MAGIC) + 4 and
                data[:len(SGMETA_MAGIC)] == SGMETA_MAGIC):
            meta_start    = len(SGMETA_MAGIC)
            meta_len      = struct.unpack('>I', data[meta_start:meta_start + 4])[0]
            content_start = meta_start + 4 + meta_len
            if content_start > len(data):
                return None, data
            try:
                metadata = json.loads(data[meta_start + 4:content_start].decode('utf-8'))
                return metadata, data[content_start:]
            except Exception:
                return None, data

        # ── Text format: SGMETA. + self-delimiting JSON object + content ──
        # Used by the SG/Send web app. The JSON object is self-delimiting so no
        # length prefix is needed. Example: SGMETA.{"filename":"foo.txt"}hello
        if (len(data) >= len(SGMETA_TEXT_PREFIX) and
                data[:len(SGMETA_TEXT_PREFIX)] == SGMETA_TEXT_PREFIX):
            json_start = len(SGMETA_TEXT_PREFIX)
            try:
                json_str          = data[json_start:].decode('utf-8')
                decoder           = json.JSONDecoder()
                metadata, end_chr = decoder.raw_decode(json_str)
                # end_chr is a character offset — convert to byte offset (handles non-ASCII)
                end_byte = len(json_str[:end_chr].encode('utf-8'))
                return metadata, data[json_start + end_byte:]
            except Exception:
                return None, data

        return None, data
