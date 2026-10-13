"""Unit tests for CLI__Mirror — `sgit vault mirror <source> <dest>` and `--verify <dir>`.

A real published vault (Vault__Publish over the in-memory host, its publish/ surface and
bare/ store composed into a site folder) is mirrored from a local folder through the real
argparse path of CLI__Main; nothing leaves the machine."""
import json
import os
import shutil
import tempfile

import pytest

from sgit_ai.cli.CLI__Main                          import CLI__Main
from sgit_ai.cli.CLI__Mirror                        import CLI__Mirror
from sgit_ai.core.Vault__Sync                       import Vault__Sync
from sgit_ai.core.actions.publish.Vault__Publish    import Vault__Publish
from sgit_ai.crypto.Vault__Crypto                   import Vault__Crypto
from sgit_ai.network.api.Vault__API__In_Memory      import Vault__API__In_Memory


@pytest.fixture(scope='module')
def published_site():
    tmp    = tempfile.mkdtemp(prefix='cli_mirror_')
    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    sync   = Vault__Sync(crypto=crypto, api=api)
    vault  = os.path.join(tmp, 'vault')
    result = sync.init(vault)
    with open(os.path.join(vault, 'hello.txt'), 'w') as f:
        f.write('mirrored content')
    sync.commit(vault, 'initial')
    sync.push(vault)
    Vault__Publish(crypto=crypto, api=api).publish(vault)
    site = os.path.join(tmp, 'site')
    os.makedirs(site)
    for name in os.listdir(os.path.join(vault, '.sg_vault', 'publish')):
        shutil.copy(os.path.join(vault, '.sg_vault', 'publish', name), site)
    shutil.copytree(os.path.join(vault, '.sg_vault', 'bare'), os.path.join(site, 'bare'))
    yield dict(tmp=tmp, site=site, vault_id=result['vault_id'], crypto=crypto)
    shutil.rmtree(tmp, ignore_errors=True)


class Test_CLI__Mirror:

    def setup_method(self):
        self.cli = CLI__Main()
        self.tmp = tempfile.mkdtemp(prefix='cli_mirror_dest_')

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _hostile_copy(self, published_site, name: str) -> str:
        site = os.path.join(self.tmp, name)
        shutil.copytree(published_site['site'], site)
        return site

    def _manifest(self, site: str) -> dict:
        with open(os.path.join(site, 'manifest.json')) as f:
            return json.load(f)

    def _put_manifest(self, site: str, manifest: dict) -> None:
        with open(os.path.join(site, 'manifest.json'), 'w') as f:
            json.dump(manifest, f, indent=2)

    # ── wiring ──────────────────────────────────────────────────────────
    def test_mirror_is_a_context_free_vault_subcommand(self, published_site, capsys):
        """`sgit vault mirror` runs from outside any vault (it touches no vault directory)."""
        dest = os.path.join(self.tmp, 'copy')
        self.cli.run(['vault', 'mirror', published_site['site'], dest])
        out = capsys.readouterr().out
        assert isinstance(self.cli.mirror, CLI__Mirror)
        assert os.path.isfile(os.path.join(dest, 'manifest.json'))
        assert 'Custody without access.' in out

    # ── mirror ──────────────────────────────────────────────────────────
    def test_mirror_reports_counts_vault_id_and_the_next_steps(self, published_site, capsys):
        dest = os.path.join(self.tmp, 'copy')
        self.cli.run(['vault', 'mirror', published_site['site'], dest])
        out = capsys.readouterr()
        lines = out.out.splitlines()
        assert lines[0].startswith('  Mirroring   ') and lines[0].endswith('   done')
        n, total = lines[0].split()[1].split('/')
        assert n == total and int(n) > 0
        assert lines[1].startswith('  note: ') and 'host-attested' in lines[1]    # refs/indexes/keys
        assert '  Custody without access.' in lines
        assert f'  You now hold a complete, verifiable copy of vault {published_site["vault_id"]}.' in lines
        assert '  You cannot read it: no key was used, and none is stored here.' in lines
        assert f'  Verify:  sgit vault mirror --verify {dest}     (checks every object hash)' in lines
        assert f'  Read it: sgit clone <read-key>:{published_site["vault_id"]} ./work   (when you have a key)' in lines
        assert out.err == ''
        assert not any(name.startswith('sgit_') for name in os.listdir(dest))

    def test_mirror_without_source_and_dest_prints_usage_and_exits_1(self, capsys):
        with pytest.raises(SystemExit) as exc:
            self.cli.run(['vault', 'mirror', '/nonexistent/source'])
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert err.startswith('usage: sgit vault mirror <source-url-or-folder> <dest>  |  sgit vault mirror --verify <dest>')

    def test_mirror_of_a_folder_with_nothing_to_list_fails_honestly(self, capsys):
        empty = os.path.join(self.tmp, 'empty'); os.makedirs(empty)
        with pytest.raises(SystemExit) as exc:
            self.cli.run(['vault', 'mirror', empty, os.path.join(self.tmp, 'copy')])
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert err.startswith('error: cannot mirror without a listing.')
        assert not os.path.exists(os.path.join(self.tmp, 'copy'))

    def test_refused_objects_are_listed_on_stderr_and_the_run_continues(self, published_site, capsys):
        """A CAS object whose bytes match neither its id nor the manifest hash is refused per
        object; the rest is copied, the count line shows copied/total, exit code stays 0."""
        site     = self._hostile_copy(published_site, 'rot')
        data_dir = os.path.join(site, 'bare', 'data')
        victim   = sorted(os.listdir(data_dir))[0]
        with open(os.path.join(data_dir, victim), 'wb') as f:
            f.write(b'rotted bytes')
        dest = os.path.join(self.tmp, 'copy')
        self.cli.run(['vault', 'mirror', site, dest])
        out = capsys.readouterr()
        n, total = out.out.splitlines()[0].split()[1].split('/')
        assert int(total) - int(n) == 1
        assert out.err.splitlines()[0] == '  Refused     1 (per object — run continued):'
        assert out.err.splitlines()[1] == f'    bare/data/{victim}: bytes do not match'
        assert not os.path.exists(os.path.join(dest, 'bare', 'data', victim))

    def test_mirror_without_a_vault_id_in_the_manifest_omits_the_id_lines(self, published_site, capsys):
        site = self._hostile_copy(published_site, 'anon')
        m = self._manifest(site); m['vault_id'] = ''; self._put_manifest(site, m)
        self.cli.run(['vault', 'mirror', site, os.path.join(self.tmp, 'copy')])
        out = capsys.readouterr().out
        assert 'You now hold a complete' not in out and 'Read it:' not in out
        assert 'Custody without access.' in out

    # ── verify ──────────────────────────────────────────────────────────
    def test_verify_an_intact_mirror(self, published_site, capsys):
        dest = os.path.join(self.tmp, 'copy')
        self.cli.run(['vault', 'mirror', published_site['site'], dest])
        capsys.readouterr()
        self.cli.run(['vault', 'mirror', '--verify', dest])
        out = capsys.readouterr()
        lines = out.out.splitlines()
        assert lines[0].startswith('  Verified   ') and lines[0].endswith(' object(s)')
        assert lines[1].startswith('  Host-attested only (not content-addressed): ')
        assert lines[-1] == '  Mirror is intact.'
        assert out.err == ''

    def test_verify_lists_failures_on_stderr_and_exits_1(self, published_site, capsys):
        dest = os.path.join(self.tmp, 'copy')
        self.cli.run(['vault', 'mirror', published_site['site'], dest])
        capsys.readouterr()
        data_dir = os.path.join(dest, 'bare', 'data')
        rotted   = sorted(os.listdir(data_dir))[0]
        gone     = sorted(os.listdir(data_dir))[1]
        with open(os.path.join(data_dir, rotted), 'wb') as f:
            f.write(b'rotted bytes')
        os.remove(os.path.join(data_dir, gone))
        with pytest.raises(SystemExit) as exc:
            self.cli.run(['vault', 'mirror', '--verify', dest])
        assert exc.value.code == 1
        out = capsys.readouterr()
        assert 'Mirror is intact.' not in out.out
        assert out.err.splitlines()[0] == '  FAILED     2:'
        assert set(out.err.splitlines()[1:]) == {f'    bare/data/{rotted}: bytes do not match',
                                                 f'    bare/data/{gone}: missing'}

    def test_verify_of_a_folder_that_is_not_a_mirror_exits_1(self, capsys):
        plain = os.path.join(self.tmp, 'plain'); os.makedirs(plain)
        with pytest.raises(SystemExit) as exc:
            self.cli.run(['vault', 'mirror', '--verify', plain])
        assert exc.value.code == 1
        assert capsys.readouterr().err == f'error: no manifest.json in {plain} — not a mirror\n'

    def test_verify_wins_over_source_and_dest(self, published_site, capsys):
        """--verify with positional args: the verify runs and the positionals are ignored."""
        dest = os.path.join(self.tmp, 'copy')
        self.cli.run(['vault', 'mirror', published_site['site'], dest])
        capsys.readouterr()
        self.cli.run(['vault', 'mirror', '/nonexistent', '/nonexistent2', '--verify', dest])
        assert capsys.readouterr().out.rstrip().endswith('  Mirror is intact.')
