"""Vault__Atomic_Write and the object-store writes that use it (phase 0, F8/B4).

A second sgit process on the same store must see an object whole or not at all,
and a temp file must never land where a store walk would upload it."""
import os
import shutil
import tempfile
import threading

import pytest

from sgit_ai.crypto.Vault__Crypto                import Vault__Crypto
from sgit_ai.safe_types.Safe_Str__Vault_Path     import Safe_Str__Vault_Path
from sgit_ai.storage.Vault__Atomic_Write         import Vault__Atomic_Write, TMP_PREFIX
from sgit_ai.storage.Vault__Object_Store         import Vault__Object_Store
from sgit_ai.storage.Vault__Verified_Write       import Vault__Verified_Write


class Test_Vault__Atomic_Write:

    def setup_method(self):
        self.tmp    = tempfile.mkdtemp()
        self.writer = Vault__Atomic_Write()

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writes_the_bytes_and_leaves_no_temp_file(self):
        path = os.path.join(self.tmp, 'a', 'b', 'file.bin')
        self.writer.write(path, b'payload')
        with open(path, 'rb') as f:
            assert f.read() == b'payload'
        assert os.listdir(os.path.dirname(path)) == ['file.bin']

    def test_replaces_an_existing_file(self):
        path = os.path.join(self.tmp, 'file.bin')
        self.writer.write(path, b'one')
        self.writer.write(path, b'two')
        with open(path, 'rb') as f:
            assert f.read() == b'two'

    def test_stages_in_the_tmp_dir_and_leaves_it_empty(self):
        path    = os.path.join(self.tmp, 'store', 'file.bin')
        staging = os.path.join(self.tmp, 'local', 'tmp')
        self.writer.write(path, b'x' * 1000, tmp_dir=staging)
        assert os.path.isdir(staging)
        assert os.listdir(staging) == []
        assert os.listdir(os.path.dirname(path)) == ['file.bin']

    def test_mode_is_what_a_plain_open_gives(self):
        plain = os.path.join(self.tmp, 'plain.bin')
        with open(plain, 'wb') as f:
            f.write(b'x')
        path = os.path.join(self.tmp, 'atomic.bin')
        self.writer.write(path, b'x')
        assert os.stat(path).st_mode & 0o777 == os.stat(plain).st_mode & 0o777

    def test_a_failed_rename_leaves_no_temp_file(self):
        path = os.path.join(self.tmp, 'is_a_dir')
        os.makedirs(os.path.join(path, 'child'))                       # os.replace onto a non-empty folder fails
        staging = os.path.join(self.tmp, 'staging')
        with pytest.raises(OSError):
            self.writer.write(path, b'x', tmp_dir=staging)
        assert os.listdir(staging) == []

    def test_temp_names_never_collide_with_an_existing_file(self):
        names = {os.path.basename(self.writer.write_temp(self.tmp, b'x')) for _ in range(50)}
        assert len(names) == 50
        assert all(name.startswith(TMP_PREFIX) for name in names)

    def test_tmp_dir_of_is_inside_local(self):
        assert self.writer.tmp_dir_of('/v/.sg_vault') == os.path.join('/v/.sg_vault', 'local', 'tmp')


class Test_Vault__Atomic_Write__Object_Store:

    def setup_method(self):
        self.tmp    = tempfile.mkdtemp()
        self.sg_dir = os.path.join(self.tmp, '.sg_vault')
        self.store  = Vault__Object_Store(vault_path=Safe_Str__Vault_Path(self.sg_dir), crypto=Vault__Crypto())
        self.data   = os.path.join(self.sg_dir, 'bare', 'data')
        self.stage  = os.path.join(self.sg_dir, 'local', 'tmp')

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_store_leaves_only_the_object(self):
        object_id = self.store.store(b'ciphertext-1')
        assert os.listdir(self.data) == [object_id]
        assert os.listdir(self.stage) == []
        assert self.store.load(object_id) == b'ciphertext-1'

    def test_store_raw_and_store_at_leave_only_the_objects(self):
        self.store.store_raw('obj-cas-imm-aaaaaaaaaaaa', b'raw')
        self.store.store_at ('obj-cas-imm-bbbbbbbbbbbb', b'at')
        self.store.store_at ('obj-cas-imm-bbbbbbbbbbbb', b'at-2', force=True)
        assert sorted(os.listdir(self.data)) == ['obj-cas-imm-aaaaaaaaaaaa', 'obj-cas-imm-bbbbbbbbbbbb']
        assert os.listdir(self.stage) == []
        assert self.store.load('obj-cas-imm-bbbbbbbbbbbb') == b'at-2'

    def test_a_reader_never_sees_part_of_an_object(self):
        """A reader polling the path while large objects are written sees either no
        file or the whole of one: never a prefix."""
        blobs   = [bytes([i]) * (4 * 1024 * 1024) for i in range(1, 9)]
        targets = [os.path.join(self.data, f'obj-cas-imm-{i:012x}') for i in range(len(blobs))]
        seen    = []
        done    = threading.Event()

        def reader():
            while not done.is_set():
                for path in targets:
                    try:
                        with open(path, 'rb') as f:
                            seen.append(len(f.read()))
                    except FileNotFoundError:
                        pass

        thread = threading.Thread(target=reader)
        thread.start()
        try:
            for path, blob in zip(targets, blobs):
                self.store.store_at(os.path.basename(path), blob)
        finally:
            done.set()
            thread.join()
        assert seen                                                         # the reader did race the writer
        assert set(seen) == {4 * 1024 * 1024}

    def test_verified_write_stages_in_local_tmp(self):
        crypto    = Vault__Crypto()
        data      = b'some ciphertext'
        file_id   = 'bare/data/' + crypto.compute_object_id(data)
        verdict   = Vault__Verified_Write(crypto=crypto).save(self.sg_dir, file_id, data)
        assert verdict == Vault__Verified_Write.VERIFIED
        assert os.listdir(self.data) == [file_id.rsplit('/', 1)[-1]]
        assert os.listdir(self.stage) == []
