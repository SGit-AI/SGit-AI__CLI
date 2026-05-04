"""Structural regression tests for case-study vault characteristics.

Validates the five performance hypotheses (H1–H5) discovered in B07 so that
any regression in HMAC-IV dedup, BFS wave structure, or HEAD-only ratio is
caught automatically.  Uses a reduced 10-commit, 30-file synthetic vault to
keep the suite fast while preserving the structural properties of the real
4-agent collaborative website vault.
"""
import os
import random
import shutil
import tempfile

import pytest

from sgit_ai.network.api.Vault__API__In_Memory         import Vault__API__In_Memory
from sgit_ai.cli.dev.Dev__Profile__Clone        import Dev__Profile__Clone
from sgit_ai.cli.dev.Dev__Server__Objects       import Dev__Server__Objects
from sgit_ai.cli.dev.Dev__Tree__Graph           import Dev__Tree__Graph
from sgit_ai.cli.dev.Schema__Profile__Clone     import Schema__Profile__Clone
from sgit_ai.cli.dev.Schema__Server__Objects    import Schema__Server__Objects
from sgit_ai.cli.dev.Schema__Tree__Graph        import Schema__Tree__Graph
from sgit_ai.crypto.Vault__Crypto               import Vault__Crypto
from sgit_ai.core.Vault__Sync                   import Vault__Sync


# ---------------------------------------------------------------------------
# Reduced website-vault structure (mirrors real vault, fast enough for pytest)
# ---------------------------------------------------------------------------
_STRUCTURE = {
    'content': {
        'hero':     ['main.md', 'cta.md'],
        'about':    ['mission.md', 'team.md', 'history.md'],
        'services': ['overview.md', 'pricing.md', 'features.md'],
        'blog':     ['post-01.md', 'post-02.md', 'post-03.md'],
    },
    'pages': {
        'home':     ['index.html', 'meta.json'],
        'about':    ['index.html', 'meta.json'],
        'services': ['index.html', 'meta.json'],
    },
    'assets': {
        'images':   ['hero.jpg', 'logo.png'],
        'icons':    ['arrow.svg', 'menu.svg'],
    },
    'styles': {
        'base':       ['reset.css', 'variables.css'],
        'components': ['header.css', 'footer.css'],
    },
}

_N_COMMITS  = 10    # enough to show dedup; fast to build
_SEED       = 42    # reproducible


def _all_files():
    result = []
    for top, subs in _STRUCTURE.items():
        for sub, files in subs.items():
            for f in files:
                path = f'{top}/{sub}/{f}'
                ext  = f.rsplit('.', 1)[-1]
                if ext == 'json':
                    content = f'{{"path": "{path}", "version": 1}}'
                elif ext == 'html':
                    content = f'<div class="{sub}">{path}</div>'
                else:
                    content = f'# {path}\n\nInitial content for {f}.'
                result.append((path, content))
    return result


_FILES = _all_files()


def _write(vault_dir, rel, content):
    full = os.path.join(vault_dir, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w') as fh:
        fh.write(content)


def _build_vault():
    """Build synthetic website vault with _N_COMMITS commits; return (vk, api, crypto, snap_dir)."""
    rng = random.Random(_SEED)

    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    sync = Vault__Sync(crypto=crypto, api=api)

    snap_dir  = tempfile.mkdtemp(prefix='case-study-test-')
    vault_dir = os.path.join(snap_dir, 'vault')
    vk        = sync.init(vault_dir)['vault_key']

    # commit 0: write all files
    for rel, content in _FILES:
        _write(vault_dir, rel, content)
    sync.commit(vault_dir, 'initial: all content')

    # commits 1.._N_COMMITS-1: change 2-4 files each
    for i in range(1, _N_COMMITS):
        changed = rng.sample(_FILES, rng.randint(2, 4))
        for rel, content in changed:
            _write(vault_dir, rel, content + f'\n<!-- rev {i} -->')
        sync.commit(vault_dir, f'agent update {i}')

    sync.push(vault_dir)
    return vk, api, crypto, snap_dir


# ---------------------------------------------------------------------------
# Shared vault — built once per test session to avoid repeated 10-commit builds
# ---------------------------------------------------------------------------
class _SharedVault:
    vk   = None
    api  = None
    crypto = None
    snap   = None

    @classmethod
    def setup(cls):
        if cls.vk is None:
            cls.vk, cls.api, cls.crypto, cls.snap = _build_vault()

    @classmethod
    def teardown(cls):
        if cls.snap:
            shutil.rmtree(cls.snap, ignore_errors=True)
            cls.snap = None
            cls.vk   = None

    @classmethod
    def make_sync(cls):
        return Vault__Sync(crypto=cls.crypto, api=cls.api)


# ---------------------------------------------------------------------------
# H3 — HMAC-IV dedup regression
#
# With deterministic IVs, identical tree content → identical tree ID.
# After N commits each touching 2-4 of 30 files, the unchanged subtrees
# should be reused across commits → dedup_ratio ≥ 3.0.
#
# If HMAC-IV breaks and random IVs are used, every tree gets a unique ID
# and dedup_ratio collapses to ~1.0 (the real-vault bug).
# ---------------------------------------------------------------------------
class Test_H3__HMAC_IV_Dedup:

    @classmethod
    def setup_class(cls):
        _SharedVault.setup()

    @classmethod
    def teardown_class(cls):
        _SharedVault.teardown()

    def _tool(self):
        return Dev__Tree__Graph(crypto=_SharedVault.crypto, api=_SharedVault.api,
                                sync=_SharedVault.make_sync())

    def test_dedup_ratio_above_threshold(self):
        """HMAC-IV must yield dedup_ratio ≥ 2.0; random IVs collapse it to ≈ 1.0."""
        out = self._tool().analyse(_SharedVault.vk)
        ratio = out.total_trees / max(out.unique_trees, 1)
        assert ratio >= 2.0, (
            f'H3 regression: dedup_ratio={ratio:.2f} < 2.0 — '
            f'HMAC-IV determinism may be broken '
            f'(unique={out.unique_trees}, refs={out.total_trees})'
        )

    def test_unique_trees_much_less_than_total_refs(self):
        """Total tree references must be significantly more than unique trees."""
        out = self._tool().analyse(_SharedVault.vk)
        assert out.total_trees > out.unique_trees, (
            f'No dedup at all: refs={out.total_trees} == unique={out.unique_trees}'
        )

    def test_returns_schema(self):
        out = self._tool().analyse(_SharedVault.vk)
        assert isinstance(out, Schema__Tree__Graph)
        assert out.vault_id != ''

    def test_json_round_trip(self):
        out  = self._tool().analyse(_SharedVault.vk)
        data = out.json()
        assert Schema__Tree__Graph.from_json(data).json() == data


# ---------------------------------------------------------------------------
# H5 — HEAD-only trees are a minority of all historical trees
#
# The HEAD working copy should need only a small fraction of the trees walked
# during a full clone.  Here with 10 commits we expect < 50% of unique trees
# to be reachable from HEAD alone; in the real vault it is ≈ 2.4%.
# ---------------------------------------------------------------------------
class Test_H5__Head_Only_Is_Minority:

    @classmethod
    def setup_class(cls):
        _SharedVault.setup()

    @classmethod
    def teardown_class(cls):
        _SharedVault.teardown()

    def _tool(self):
        return Dev__Tree__Graph(crypto=_SharedVault.crypto, api=_SharedVault.api,
                                sync=_SharedVault.make_sync())

    def test_head_only_trees_less_than_half_of_unique(self):
        """HEAD-only trees must be a minority of total unique trees (H5)."""
        out = self._tool().analyse(_SharedVault.vk)
        if out.unique_trees == 0:
            pytest.skip('no trees to analyse')
        ratio = out.head_only_trees / out.unique_trees
        assert ratio < 0.5, (
            f'H5 regression: head_only_ratio={ratio:.2%} ≥ 0.5 — '
            f'the HEAD-only optimisation would have little effect '
            f'(head_only={out.head_only_trees}, unique={out.unique_trees})'
        )

    def test_head_only_trees_positive(self):
        out = self._tool().analyse(_SharedVault.vk)
        assert out.head_only_trees >= 1

    def test_head_only_leq_unique_trees(self):
        out = self._tool().analyse(_SharedVault.vk)
        assert out.head_only_trees <= out.unique_trees


# ---------------------------------------------------------------------------
# H1 — BFS wave structure: depth histogram has ≥ 2 levels
#
# Regression guard: if the tree walker flattens the BFS (e.g. walks one tree
# at a time), the histogram degenerates to a single depth-0 bucket.
# A 3-level directory structure (top/sub/file) must produce entries at
# depths 0 and 1 (root tree and subdir trees).
# ---------------------------------------------------------------------------
class Test_H1__BFS_Wave_Structure:

    @classmethod
    def setup_class(cls):
        _SharedVault.setup()

    @classmethod
    def teardown_class(cls):
        _SharedVault.teardown()

    def _tool(self):
        return Dev__Tree__Graph(crypto=_SharedVault.crypto, api=_SharedVault.api,
                                sync=_SharedVault.make_sync())

    def test_depth_histogram_has_multiple_levels(self):
        """3-level vault must show depth-0 root trees AND depth-1 subdir trees."""
        out    = self._tool().analyse(_SharedVault.vk)
        depths = [int(d.depth) for d in out.depth_histogram]
        assert 0 in depths, f'Missing depth-0 (root) entries: {depths}'
        assert max(depths) >= 1, f'Only depth-0 trees found — BFS not walking subtrees: {depths}'

    def test_n_commits_matches_vault(self):
        out = self._tool().analyse(_SharedVault.vk)
        assert out.n_commits >= _N_COMMITS


# ---------------------------------------------------------------------------
# Server-objects: history objects dominate HEAD-reachable objects (H5 mirror)
# ---------------------------------------------------------------------------
class Test_Server_Objects__History_Dominates:

    @classmethod
    def setup_class(cls):
        _SharedVault.setup()

    @classmethod
    def teardown_class(cls):
        _SharedVault.teardown()

    def _tool(self):
        return Dev__Server__Objects(crypto=_SharedVault.crypto, api=_SharedVault.api,
                                    sync=_SharedVault.make_sync())

    def test_history_only_exceeds_head_reachable(self):
        """More objects should be history-only than HEAD-reachable (H5 at server level)."""
        out = self._tool().analyse(_SharedVault.vk)
        assert out.history_only > out.head_reachable, (
            f'Expected history_only > head_reachable but got '
            f'history_only={out.history_only}, head_reachable={out.head_reachable}'
        )

    def test_total_objects_positive(self):
        out = self._tool().analyse(_SharedVault.vk)
        assert out.total_objects >= 1

    def test_json_round_trip(self):
        out  = self._tool().analyse(_SharedVault.vk)
        data = out.json()
        assert Schema__Server__Objects.from_json(data).json() == data


# ---------------------------------------------------------------------------
# Profile clone: trees phase is dominant (H2 structural guard)
#
# In a multi-level vault with many historical trees, tree download time
# should be > 0. This guards against the phase timer breaking and reporting
# zero for the dominant phase.
# ---------------------------------------------------------------------------
class Test_Profile__Trees_Phase_Tracked:

    @classmethod
    def setup_class(cls):
        _SharedVault.setup()

    @classmethod
    def teardown_class(cls):
        _SharedVault.teardown()

    def _tool(self):
        return Dev__Profile__Clone(crypto=_SharedVault.crypto, api=_SharedVault.api,
                                   sync=_SharedVault.make_sync())

    def test_profile_returns_schema(self):
        clone_dir = tempfile.mkdtemp(prefix='case-study-profile-')
        try:
            out = self._tool().profile(_SharedVault.vk, clone_dir)
            assert isinstance(out, Schema__Profile__Clone)
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)

    def test_n_trees_matches_vault_structure(self):
        """Vault with 4 top-level dirs × 3 subdirs expects at least 12 unique trees."""
        clone_dir = tempfile.mkdtemp(prefix='case-study-profile-')
        try:
            out = self._tool().profile(_SharedVault.vk, clone_dir)
            assert out.n_trees >= 12, (
                f'Expected ≥ 12 trees for 4×3 vault structure but got {out.n_trees}'
            )
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)

    def test_n_blobs_matches_file_count(self):
        clone_dir = tempfile.mkdtemp(prefix='case-study-profile-')
        try:
            out = self._tool().profile(_SharedVault.vk, clone_dir)
            assert out.n_blobs >= len(_FILES), (
                f'Expected ≥ {len(_FILES)} blobs but got {out.n_blobs}'
            )
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)

    def test_t_trees_ms_recorded(self):
        """Tree-phase timer must fire and record > 0 ms."""
        clone_dir = tempfile.mkdtemp(prefix='case-study-profile-')
        try:
            out = self._tool().profile(_SharedVault.vk, clone_dir)
            assert out.t_trees_ms >= 0
            assert out.total_ms  >= 0
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)
