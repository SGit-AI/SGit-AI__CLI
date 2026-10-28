"""What each branch publishes to PyPI (28 Oct): main bumps the minor and publishes the release
(X.Y.0); every dev push bumps the patch and publishes that build as the same plain version as
its GitHub tag (X.Y.N). No `.devN` suffix: the patch number is what marks a dev build, and
`sgit update --stable` pins the newest X.Y.0."""
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _workflow(name: str) -> str:
    with open(os.path.join(REPO, '.github', 'workflows', name)) as f:
        return f.read()


class Test_CI__PyPI_Versions:

    def test_dev_bumps_the_patch_and_publishes_it(self):
        dev = _workflow('ci-pipeline__dev.yml')
        assert "release_type        : 'minor'" in dev                 # OSBot's 'minor' bumps the patch
        assert 'should_publish_pypi       : true' in dev

    def test_main_bumps_the_minor_and_publishes_the_release(self):
        main = _workflow('ci-pipeline__main.yml')
        assert "release_type        : 'major'" in main                # OSBot's 'major' bumps the minor
        assert 'should_publish_pypi       : true' in main

    def test_nothing_rewrites_the_version_before_publishing(self):
        pipeline = _workflow('ci-pipeline.yml')
        assert 'prerelease' not in pipeline
        assert not os.path.exists(os.path.join(REPO, '.github', 'scripts', 'pypi__mark-prerelease.sh'))
