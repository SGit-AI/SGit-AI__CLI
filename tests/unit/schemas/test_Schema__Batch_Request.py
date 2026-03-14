from sg_send_cli.schemas.Schema__Batch_Request   import Schema__Batch_Request
from sg_send_cli.schemas.Schema__Batch_Operation import Schema__Batch_Operation
from sg_send_cli.safe_types.Enum__Batch_Op       import Enum__Batch_Op


class Test_Schema__Batch_Request:

    def test_create_empty(self):
        req = Schema__Batch_Request()
        assert req.operations == []

    def test_create_with_operations(self):
        op1 = Schema__Batch_Operation(op=Enum__Batch_Op.WRITE, file_id='bare/data/obj-abc123', data='base64data')
        op2 = Schema__Batch_Operation(op=Enum__Batch_Op.DELETE, file_id='bare/data/obj-def456')
        req = Schema__Batch_Request(operations=[op1, op2])
        assert len(req.operations) == 2
        assert req.operations[0].op == Enum__Batch_Op.WRITE
        assert req.operations[1].op == Enum__Batch_Op.DELETE

    def test_round_trip(self):
        op       = Schema__Batch_Operation(op=Enum__Batch_Op.WRITE, file_id='bare/data/obj-abc123', data='dGVzdA==')
        req      = Schema__Batch_Request(operations=[op])
        restored = Schema__Batch_Request.from_json(req.json())
        assert restored.json() == req.json()
