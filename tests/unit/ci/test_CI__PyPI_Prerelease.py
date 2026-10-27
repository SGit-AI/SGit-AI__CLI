"""Every dev push is published to PyPI as a pre-release (27 Oct): the dev pipeline tags vX.Y.Z and
publishes X.Y.Z.dev0, which a plain `pip install sgit-ai` skips; only main publishes releases.
These tests run the script the pipeline runs, on a copy of this repository's files, and check the
workflow wiring, so a change that would let dev publish a release fails here first."""
import os
import shutil
import subprocess

import pytest

REPO   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SCRIPT = os.path.join(REPO, '.github', 'scripts', 'pypi__mark-prerelease.sh')


def _workflow(name: str) -> str:
    with open(os.path.join(REPO, '.github', 'workflows', name)) as f:
        return f.read()


class Test_CI__PyPI_Prerelease:

    def _copy(self, tmp_path, version: str) -> str:
        root = str(tmp_path / 'repo')
        os.makedirs(os.path.join(root, 'sgit_ai'))
        shutil.copy(os.path.join(REPO, 'pyproject.toml'), os.path.join(root, 'pyproject.toml'))
        with open(os.path.join(root, 'sgit_ai', 'version'), 'w') as f:
            f.write(version + '\n')
        return root

    def _run(self, root: str):
        return subprocess.run(['bash', SCRIPT, 'sgit_ai', root], capture_output=True, text=True)

    def _read(self, root: str, rel: str) -> str:
        with open(os.path.join(root, rel)) as f:
            return f.read()

    def test_the_dev_tag_becomes_a_dev0_pre_release_in_pyproject_and_the_version_file(self, tmp_path):
        root   = self._copy(tmp_path, 'v0.26.1')
        before = self._read(root, 'pyproject.toml')
        r = self._run(root)
        assert r.returncode == 0, r.stderr
        after = self._read(root, 'pyproject.toml')
        assert 'version     = "0.26.1.dev0"' in after
        assert [l for l in after.splitlines() if not l.startswith('version')] == \
               [l for l in before.splitlines() if not l.startswith('version')]   # nothing else changes
        assert self._read(root, 'sgit_ai/version').strip() == 'v0.26.1.dev0'
        assert 'pip install --pre sgit-ai' in r.stdout

    def test_the_result_sorts_above_the_release_and_below_the_next_and_pip_skips_it(self):
        from pip._vendor.packaging.version import Version
        dev = Version('0.26.1.dev0')
        assert dev.is_prerelease and Version('0.26.0') < dev < Version('0.26.2.dev0') < Version('0.27.0')

    @pytest.mark.parametrize('version', ['v0.26.1.dev0', 'v0.26', 'release', ''])
    def test_anything_but_a_plain_tag_is_refused_and_nothing_changes(self, tmp_path, version):
        root   = self._copy(tmp_path, version)
        before = self._read(root, 'pyproject.toml')
        r = self._run(root)
        assert r.returncode != 0 and 'error' in r.stderr
        assert self._read(root, 'pyproject.toml') == before and self._read(root, 'sgit_ai/version').strip() == version

    def test_dev_publishes_pre_releases_and_main_publishes_releases(self):
        dev, main, base = _workflow('ci-pipeline__dev.yml'), _workflow('ci-pipeline__main.yml'), _workflow('ci-pipeline.yml')
        assert 'should_publish_pypi       : true' in dev and 'pypi_prerelease           : true' in dev
        assert 'should_publish_dockerhub  : false' in dev
        assert 'should_publish_pypi       : true' in main and 'pypi_prerelease' not in main     # default false: a release
        step = base.index('- name: Mark this build as a pre-release')
        assert base.index('- name: Git Update Current Branch', base.index('publish-to-pypi:')) < step < base.index('- name: publish-to-pypi')
        assert 'if: inputs.pypi_prerelease' in base[step:base.index('- name: publish-to-pypi')]
        assert 'bash .github/scripts/pypi__mark-prerelease.sh "$PACKAGE_NAME"' in base
