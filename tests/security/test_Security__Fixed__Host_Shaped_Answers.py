"""Fixed in 0.21.4 — four more answers the client took as control (round-1 ranked claims).

Threat model: TM-F37 (the host's not_found on a branch this clone had synced dropped the
compare-and-swap), TM-F38 (a rewritten chain longer than the rewind guard's fetch limit passed
as "cannot tell" and the pull proceeded), TM-F39 (text in a host's response body flipped a
writable session to the read-only static transport), TM-F40 (a remotes.json that exists but
cannot be read sent the command to the default server). All four came from the round-1
tool-assisted review's ranked queue (`review/findings/ranked.json`: AC-H-002, AC-V-002,
AC-H-004, AC-C-002) and were reproduced on 13 Oct 2026 before the fix.

Every attack test fails on the code before its fix; the controls pass on both.
"""
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sgit_ai.core.Vault__Errors                   import Vault__Ref_Rewind_Error, Vault__Remotes_Unreadable_Error
from sgit_ai.network.api.Vault__API__Auto         import Vault__API__Auto
from sgit_ai.network.api.Vault__API__In_Memory    import Vault__API__In_Memory
from sgit_ai.safe_types.Enum__Fetch_Failure_Class import Enum__Fetch_Failure_Class
from sgit_ai.safe_types.Enum__Transport           import Enum__Transport
from sgit_ai.safe_types.Safe_Str__Error_Message   import Safe_Str__Error_Message
from sgit_ai.schemas.Schema__Fetch_Failure        import Schema__Fetch_Failure
from tests._helpers.vault_adversary               import Vault__Adversary
from tests._helpers.vault_test_env                import Vault__Test_Env


def _write(directory, name, text):
    with open(os.path.join(directory, name), 'w') as f:
        f.write(text)


class Host__Named_Ref_Not_Found(Vault__API__In_Memory):
    """Honest in every answer but one: the named branch's ref reads as the server's own
    not_found (the per-file ABSENT classification a real server's reply produces)."""
    def batch_read(self, vault_id, file_ids, failures=None):
        result = super().batch_read(vault_id, file_ids, failures=failures)
        for file_id in file_ids:
            if '/refs/' in file_id and 'ref-pid-snw' not in file_id:          # the named branch, not a clone branch
                result[file_id] = None
                if failures is not None:
                    failures[file_id] = Schema__Fetch_Failure(file_id       = None,
                                                              classification= Enum__Fetch_Failure_Class.ABSENT,
                                                              error_message = Safe_Str__Error_Message('not_found'))
        return result


class Test_Fixed__Named_Ref_Not_Found_After_Sync:
    """TM-F37. A branch created here and never pushed has nothing on the server to
    compare-and-swap against, so the server's not_found rightly drops the CAS for it. For
    a branch this clone has already accepted a head of, the same word from the host turned
    a guarded push into a blind write of this clone's stale head: the shared branch rewound
    under a legitimate key, exactly what TM-F34 closed for the empty listing."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'a.md': 'v1'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s = self._env.restore()
        _write(self.s.alice_dir, 'a.md', 'alice-v2'); self.s.sync.commit(self.s.alice_dir, 'alice v2')
        self.s.sync.push(self.s.alice_dir)
        self.named  = [k for k in self.s.api._store if '/bare/refs/' in k and 'ref-pid-snw' not in k]
        self.before = {k: self.s.api._store[k] for k in self.named}
        _write(self.s.bob_dir, 'b.md', 'bob'); self.s.sync.commit(self.s.bob_dir, 'bob, never pulled alice')
        self.lying = Host__Named_Ref_Not_Found(); self.lying.setup(); self.lying._store = self.s.api._store

    def teardown_method(self):
        self.s.cleanup()

    def test_TM_F37__a_not_found_on_a_synced_branch_is_refused_and_the_ref_stays(self):
        """Before: status 'pushed', and the named ref on the host now pointed at Bob's head
        (Alice's v2 gone from the branch)."""
        self.s.sync.api = self.lying
        with pytest.raises(RuntimeError, match='already synced|compare-and-swap'):
            self.s.sync.push(self.s.bob_dir)
        assert {k: self.s.api._store.get(k) for k in self.named} == self.before

    def test_control__force_still_recreates_a_branch_the_server_lost(self):
        """`sgit push --force` says the overwrite is deliberate: the one way through."""
        self.s.sync.api = self.lying
        assert self.s.sync.push(self.s.bob_dir, force=True)['status'] == 'pushed'

    def test_control__an_honest_host_makes_bob_pull_first_then_push(self):
        assert self.s.sync.push(self.s.bob_dir)['status'] == 'pushed'
        assert {k: self.s.api._store.get(k) for k in self.named} != self.before      # moved by a guarded push


class Test_Fixed__Rewrite_Longer_Than_The_Fetch_Limit:
    """TM-F38. The rewind guard fetches at most `commit_fetch_limit` (50) commits to connect
    the server's head to the last accepted one; past that it answered UNKNOWN and the pull
    proceeded, merging with an empty base. So a host (with a read-key holder, TM-R01) that
    replaced the branch with an unrelated chain of 51+ commits was not a rewind to the guard,
    while a 3-commit rewrite was refused. Now UNKNOWN walks the whole chain, then refuses."""

    _env = None

    @classmethod
    def setup_class(cls):
        cls._env = Vault__Test_Env()
        cls._env.setup_two_clones(files={'policy.md': 'pay alice'})

    @classmethod
    def teardown_class(cls):
        cls._env.cleanup_snapshot()

    def setup_method(self):
        self.s     = self._env.restore()
        self.adv   = Vault__Adversary(self.s.api, self.s.vault_key)
        self.named = self.adv.named_branch()
        self.head  = self.adv.head_of(self.named)

    def teardown_method(self):
        self.adv.cleanup(); self.s.cleanup()

    def _chain(self, length: int, parent: str) -> str:
        for i in range(length):
            parent = self.adv.forge_commit({'policy.md': f'pay mallory {i}'.encode()}, parent=parent,
                                           branch_id=str(self.named.branch_id), sign=True)
        return parent

    def test_TM_F38__an_unrelated_chain_past_the_limit_is_a_rewind(self):
        """Before: pull returned status 'conflicts' and accepted the chain as the branch."""
        self.adv.move_branch(self.named, self._chain(60, parent=''))
        with pytest.raises(Vault__Ref_Rewind_Error, match='rewound or rewritten|could not connect'):
            self.s.sync.pull(self.s.bob_dir)
        assert open(os.path.join(self.s.bob_dir, 'policy.md')).read() == 'pay alice'

    def test_control__a_short_unrelated_chain_was_already_refused(self):
        self.adv.move_branch(self.named, self._chain(3, parent=''))
        with pytest.raises(Vault__Ref_Rewind_Error):
            self.s.sync.pull(self.s.bob_dir)

    def test_control__sixty_honest_commits_on_top_of_the_known_head_still_pull(self):
        """A teammate who pushed more than the limit is behind, not rewound: the full walk
        reaches the known head and the pull proceeds (the commits are fetched anyway)."""
        self.adv.move_branch(self.named, self._chain(60, parent=self.head))
        result = self.s.sync.pull(self.s.bob_dir)
        assert result['status'] in ('merged', 'updated', 'fast_forward', 'conflicts')
        assert 'pay mallory 59' in open(os.path.join(self.s.bob_dir, 'policy.md')).read()


class Test_Fixed__Transport_Flip_By_Body_Text:
    """TM-F39. The auto transport remembers a host as static when the batch route answers
    404/405/501. It decided that by searching the whole error text, which embeds the host's
    response body: a 500 on any route whose body mentioned `/api/vault/batch/` and `HTTP 404`
    flipped the session to the read-only transport, so every later write in the process was
    refused as 'a plain file server' and the token was sent nowhere. Now only the request
    line (the route this client called) and the status it observed decide."""

    def _serve(self, status: int, body: bytes):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
        server = HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def test_TM_F39__a_body_that_names_the_batch_route_does_not_flip_the_transport(self):
        """Before: resolved became STATIC after one such read, and write raised the
        read-only transport error."""
        body   = b'{"detail": "see /api/vault/batch/ which returned HTTP 404 earlier"}'
        server = self._serve(500, body)
        try:
            api = Vault__API__Auto(base_url=f'http://127.0.0.1:{server.server_port}', access_token='t').setup()
            with pytest.raises(RuntimeError, match='HTTP 500'):
                api.read('vault-1', 'bare/refs/x')
            assert api.resolved is None                                            # still the live API
        finally:
            server.shutdown()

    def test_control__the_batch_route_itself_answering_404_still_resolves(self):
        api   = Vault__API__Auto(base_url='https://vault.example.invalid', access_token='')
        error = RuntimeError('API Error: HTTP 404 Not Found\n  Request:  POST https://vault.example.invalid'
                             '/api/vault/batch/abcd\n  Headers:  {}\n  Response: anything')
        assert api._resolve_from_error(error) is True

    def test_TM_F39__a_read_404_whose_body_mentions_the_batch_route_does_not_resolve(self):
        api   = Vault__API__Auto(base_url='https://vault.example.invalid', access_token='')
        error = RuntimeError('API Error: HTTP 404 Not Found\n  Request:  GET https://vault.example.invalid'
                             '/api/vault/read/abcd/bare/refs/x\n  Headers:  {}\n  Response: /api/vault/batch/ HTTP 404')
        assert api._resolve_from_error(error) is False


class Test_Fixed__Unreadable_Remotes_Refuse:
    """TM-F40. `resolve_remote` swallowed any error from reading remotes.json and fell
    through to the legacy base_url file and then the default server: a vault that recorded
    `origin` was sent to dev.send.sgraph.ai, token and all, because its record was damaged
    (or an A6 damaged it). Now a remotes.json that exists but cannot be read refuses the
    command, naming the file; only an absent file falls through."""

    def setup_method(self, tmp_path=None):
        import tempfile
        from sgit_ai.core.Vault__Remote_Manager import Vault__Remote_Manager
        self.directory = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.directory, '.sg_vault', 'local'))
        Vault__Remote_Manager().add_remote(self.directory, 'origin', 'https://vault.example.invalid', 'vault-1')
        self.path = os.path.join(self.directory, '.sg_vault', 'local', 'remotes.json')

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.directory, ignore_errors=True)

    def _resolve(self):
        import argparse
        from sgit_ai.cli.CLI__Token_Store import CLI__Token_Store
        return CLI__Token_Store().resolve_remote(argparse.Namespace(), self.directory)

    @pytest.mark.parametrize('damage', ['{not json', '', '[{"name": "origin"', 'null', '[1, 2]'])
    def test_TM_F40__a_damaged_remotes_file_refuses_the_command(self, damage):
        """Before: {'name': '', 'base_url': DEFAULT_BASE_URL} — the default server."""
        with open(self.path, 'w') as f:
            f.write(damage)
        with pytest.raises(Vault__Remotes_Unreadable_Error, match='remotes.json'):
            self._resolve()

    def test_TM_F40__the_per_command_server_pin_refuses_too(self, capsys, monkeypatch):
        """CLI__Main decides the server once per command (TM-F22); it swallowed the read
        error and pinned the default. Now the command refuses before anything runs."""
        from sgit_ai.cli.CLI__Main import CLI__Main
        with open(self.path, 'w') as f:
            f.write('{not json')
        monkeypatch.chdir(self.directory)
        try:
            CLI__Main().run(['status'])
            outcome = 'ran'
        except SystemExit as exc:
            outcome = exc.code
        except Vault__Remotes_Unreadable_Error:
            outcome = 'refused'
        assert outcome in (1, 'refused')
        assert outcome == 'refused' or 'remotes.json' in capsys.readouterr().err

    def test_control__an_absent_file_still_falls_through(self):
        os.remove(self.path)
        assert self._resolve()['name'] == ''

    def test_control__an_honest_file_resolves_its_remote(self):
        assert self._resolve() == {'name': 'origin', 'base_url': 'https://vault.example.invalid', 'tls_verify': True}

    def test_TM_F40__status_still_reports_a_remote_as_configured(self):
        from sgit_ai.core.actions.status.Vault__Sync__Status import Vault__Sync__Status
        from sgit_ai.storage.Vault__Storage                 import Vault__Storage
        with open(self.path, 'w') as f:
            f.write('{not json')
        assert Vault__Sync__Status()._has_remotes(self.directory, Vault__Storage()) is True
