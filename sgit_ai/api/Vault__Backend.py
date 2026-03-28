from osbot_utils.type_safe.Type_Safe import Type_Safe


class Vault__Backend(Type_Safe):
    """Abstract backend interface for vault storage.

    All vault storage operations go through this interface, allowing
    pluggable backends: SG/Send API, local folder, zip archive, etc.

    Subclasses must implement: read, write, delete, list_files, batch.
    """

    def read(self, file_id: str) -> bytes:
        raise NotImplementedError(f'{type(self).__name__}.read() not implemented')

    def write(self, file_id: str, data: bytes) -> dict:
        raise NotImplementedError(f'{type(self).__name__}.write() not implemented')

    def delete(self, file_id: str) -> dict:
        raise NotImplementedError(f'{type(self).__name__}.delete() not implemented')

    def list_files(self, prefix: str = '') -> list:
        raise NotImplementedError(f'{type(self).__name__}.list_files() not implemented')

    def batch(self, operations: list) -> dict:
        """Execute a list of operations atomically (best-effort).

        Default implementation executes operations one-by-one.
        Subclasses may override to provide true atomic batching.
        """
        import base64
        results = []
        for op in operations:
            op_type = op['op']
            file_id = op['file_id']
            if op_type in ('write', 'write-if-match'):
                payload = base64.b64decode(op['data'])
                self.write(file_id, payload)
                results.append(dict(file_id=file_id, status='ok'))
            elif op_type == 'delete':
                self.delete(file_id)
                results.append(dict(file_id=file_id, status='ok'))
        return dict(status='ok', results=results)

    def exists(self, file_id: str) -> bool:
        try:
            self.read(file_id)
            return True
        except (FileNotFoundError, RuntimeError):
            return False
