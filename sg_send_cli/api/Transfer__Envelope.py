import json
import struct
from osbot_utils.type_safe.Type_Safe import Type_Safe

SGMETA_MAGIC = bytes([0x53, 0x47, 0x4D, 0x45, 0x54, 0x41, 0x00])   # ASCII: SGMETA\0


class Transfer__Envelope(Type_Safe):

    def package(self, content: bytes, filename: str) -> bytes:
        meta_bytes = json.dumps({"filename": filename}).encode('utf-8')
        meta_len   = struct.pack('>I', len(meta_bytes))
        return SGMETA_MAGIC + meta_len + meta_bytes + content

    def unpackage(self, data: bytes) -> tuple:
        if len(data) < len(SGMETA_MAGIC) + 4:
            return None, data
        if data[:len(SGMETA_MAGIC)] != SGMETA_MAGIC:
            return None, data
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
