import hashlib
from sgit_ai.schemas.Schema__Transfer_File import Schema__Transfer_File


class Test_Schema__Transfer_File:

    def test_create_with_defaults(self):
        tf = Schema__Transfer_File()
        assert tf.transfer_id is None
        assert tf.file_path   is None
        assert tf.file_size   == 0

    def test_create_with_values(self):
        h = hashlib.sha256(b'file content').hexdigest()
        tf = Schema__Transfer_File(transfer_id='abc123def456',
                                   file_path='documents/report.pdf',
                                   file_hash=h,
                                   file_size=2048)
        assert tf.transfer_id == 'abc123def456'
        assert tf.file_size   == 2048

    def test_round_trip(self):
        h = hashlib.sha256(b'test').hexdigest()
        tf       = Schema__Transfer_File(transfer_id='abc123def456',
                                         file_path='test.txt',
                                         file_hash=h,
                                         file_size=42)
        restored = Schema__Transfer_File.from_json(tf.json())
        assert restored.json() == tf.json()
