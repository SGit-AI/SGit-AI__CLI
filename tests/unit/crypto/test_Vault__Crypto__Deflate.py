"""Blob envelope v2 (pack vaults, feature 'blob-deflate'): deflate, then encrypt, keep the
smaller. Decryption reads both envelopes by inspection, so every read path in the CLI is
unchanged; the deterministic tree path never compresses (rebuilt trees must match byte for
byte across clients, and a browser's deflate is not zlib's)."""
import os
import zlib

from sgit_ai.crypto.Vault__Crypto import Vault__Crypto, DEFLATE_MAGIC, GCM_IV_BYTES

KEY  = bytes(range(32))
TEXT = (b'{"event": "read", "page": "/articles/scion-and-sgit", "reader": "r-0042"}\n' * 200)


class Test_Vault__Crypto__Deflate:

    def test_off_by_default_and_v1_unchanged(self):
        c = Vault__Crypto()
        assert c.deflate_blobs is False
        data = c.encrypt(KEY, TEXT, deflate=True)
        assert not data.startswith(DEFLATE_MAGIC)
        assert len(data) == GCM_IV_BYTES + len(TEXT) + 16
        assert c.decrypt(KEY, data) == TEXT

    def test_compressible_text_gets_the_v2_envelope_and_round_trips(self):
        c = Vault__Crypto(deflate_blobs=True)
        data = c.encrypt(KEY, TEXT, deflate=True)
        assert data.startswith(DEFLATE_MAGIC)
        assert len(data) < len(TEXT) // 10                                   # 200 repeated lines
        assert c.decrypt(KEY, data) == TEXT
        assert Vault__Crypto().decrypt(KEY, data) == TEXT                    # a reader with the flag off reads it too

    def test_incompressible_bytes_stay_v1(self):
        c = Vault__Crypto(deflate_blobs=True)
        blob = os.urandom(50_000)
        data = c.encrypt(KEY, blob, deflate=True)
        assert not data.startswith(DEFLATE_MAGIC)
        assert c.decrypt(KEY, data) == blob

    def test_v1_objects_still_decrypt_with_the_flag_on(self):
        v1 = Vault__Crypto().encrypt(KEY, TEXT)
        assert Vault__Crypto(deflate_blobs=True).decrypt(KEY, v1) == TEXT

    def test_deterministic_path_never_compresses(self):
        c = Vault__Crypto(deflate_blobs=True)
        a = c.encrypt_deterministic(KEY, TEXT)
        b = c.encrypt_deterministic(KEY, TEXT)
        assert a == b and not a.startswith(DEFLATE_MAGIC)
        assert a == Vault__Crypto().encrypt_deterministic(KEY, TEXT)        # identical to a non-pack client's tree

    def test_a_v1_object_that_happens_to_start_with_the_magic_is_read_as_v1(self):
        c  = Vault__Crypto(deflate_blobs=True)
        iv = DEFLATE_MAGIC + os.urandom(GCM_IV_BYTES - len(DEFLATE_MAGIC))   # a random iv with those 5 bytes
        v1 = Vault__Crypto().encrypt(KEY, TEXT, iv=iv)
        assert v1.startswith(DEFLATE_MAGIC)
        assert c.decrypt(KEY, v1) == TEXT                                    # GCM tag fails the v2 reading; v1 wins

    def test_tampered_v2_envelope_is_refused(self):
        import pytest
        c    = Vault__Crypto(deflate_blobs=True)
        data = bytearray(c.encrypt(KEY, TEXT, deflate=True)); data[-1] ^= 1
        with pytest.raises(Exception):
            c.decrypt(KEY, bytes(data))

    def test_object_id_covers_the_whole_envelope(self):
        c    = Vault__Crypto(deflate_blobs=True)
        data = c.encrypt(KEY, TEXT, deflate=True)
        assert c.object_id_matches(c.compute_object_id(data), data)
        assert not c.object_id_matches(c.compute_object_id(data), data[len(DEFLATE_MAGIC):])

    def test_empty_and_tiny_plaintexts(self):
        c = Vault__Crypto(deflate_blobs=True)
        for p in (b'', b'x', b'hello'):
            data = c.encrypt(KEY, p, deflate=True)
            assert not data.startswith(DEFLATE_MAGIC)                        # never longer than v1
            assert c.decrypt(KEY, data) == p

    def test_the_ratio_on_real_shapes(self):
        c = Vault__Crypto(deflate_blobs=True)
        json_like = ('{"id": %d, "name": "person %d", "tags": ["a", "b"]}\n' % (i, i) for i in range(2000))
        plain = ''.join(json_like).encode()
        data  = c.encrypt(KEY, plain, deflate=True)
        assert len(plain) / len(data) > 2.5                                  # JSON measured 2.8x on the comms vault
