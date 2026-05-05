#!/usr/bin/env python3
"""
Build a synthetic case-study vault that replicates the structural
characteristics of the real 4-agent website vault:
  - 42 commits, 2375 trees, 165 blobs
  - Deep directory tree (content, pages, assets, components, styles, data, docs)
  - Each commit touches 2-5 files across different subtrees
  - Uses the in-memory API so no network required
  - Runs all B01 tools and saves output to tests/fixtures/perf/
"""
import json
import os
import random
import shutil
import sys
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sgit_ai.network.api.Vault__API__In_Memory  import Vault__API__In_Memory
from sgit_ai.crypto.Vault__Crypto       import Vault__Crypto
from sgit_ai.core.Vault__Sync           import Vault__Sync
from sgit_ai.plugins.dev.Dev__Profile__Clone import Dev__Profile__Clone
from sgit_ai.plugins.dev.Dev__Tree__Graph   import Dev__Tree__Graph
from sgit_ai.plugins.dev.Dev__Server__Objects import Dev__Server__Objects

random.seed(42)   # reproducible

# -----------------------------------------------------------------------
# Vault structure mirrors a 4-agent collaborative website
# -----------------------------------------------------------------------
STRUCTURE = {
    'content': {
        'hero': ['main.md', 'cta.md', 'background.md'],
        'about': ['mission.md', 'team.md', 'history.md', 'values.md'],
        'services': ['overview.md', 'pricing.md', 'features.md', 'faq.md'],
        'blog': ['post-01.md', 'post-02.md', 'post-03.md', 'post-04.md',
                 'post-05.md', 'post-06.md', 'post-07.md', 'post-08.md'],
        'case-studies': ['cs-01.md', 'cs-02.md', 'cs-03.md'],
        'contact': ['form.md', 'map.md'],
    },
    'pages': {
        'home': ['index.html', 'meta.json'],
        'about': ['index.html', 'meta.json'],
        'services': ['index.html', 'meta.json'],
        'blog': ['index.html', 'meta.json', 'archive.html'],
        'contact': ['index.html', 'meta.json'],
    },
    'assets': {
        'images': ['hero.jpg', 'logo.png', 'team-photo.jpg', 'bg.jpg'],
        'icons': ['arrow.svg', 'close.svg', 'menu.svg', 'search.svg'],
        'fonts': ['main.woff2', 'heading.woff2'],
    },
    'components': {
        'header': ['nav.html', 'logo.html', 'search.html'],
        'footer': ['links.html', 'legal.html', 'social.html'],
        'cards': ['service-card.html', 'blog-card.html', 'team-card.html'],
        'forms': ['contact-form.html', 'search-form.html'],
        'hero': ['hero.html', 'cta-button.html'],
    },
    'styles': {
        'base': ['reset.css', 'variables.css', 'typography.css'],
        'components': ['header.css', 'footer.css', 'cards.css', 'forms.css'],
        'pages': ['home.css', 'about.css', 'services.css', 'blog.css'],
        'themes': ['light.css', 'dark.css'],
    },
    'data': {
        'nav': ['main-nav.json', 'footer-nav.json'],
        'content': ['team-members.json', 'services.json', 'case-studies.json'],
        'config': ['site.json', 'seo.json', 'analytics.json'],
    },
    'docs': {
        'agents': ['agent-01-brief.md', 'agent-02-brief.md',
                   'agent-03-brief.md', 'agent-04-brief.md'],
        'guides': ['setup.md', 'workflow.md', 'style-guide.md'],
        'decisions': ['d01.md', 'd02.md', 'd03.md', 'd04.md', 'd05.md'],
    },
    'instructions': {
        'home': ['home.json'],
        'about': ['about.json'],
        'services': ['services.json'],
        'blog': ['blog.json'],
    },
}

def all_files():
    """Return list of all (rel_path, content) pairs."""
    result = []
    for top, subs in STRUCTURE.items():
        for sub, files in subs.items():
            for f in files:
                path = f'{top}/{sub}/{f}'
                ext  = f.rsplit('.', 1)[-1]
                if ext == 'json':
                    content = json.dumps({'path': path, 'version': 1})
                elif ext in ('html',):
                    content = f'<div class="{sub}">{path}</div>'
                else:
                    content = f'# {path}\n\nInitial content for {f}.'
                result.append((path, content))
    return result

FILES = all_files()

def write_file(vault_dir, rel_path, content):
    full   = os.path.join(vault_dir, rel_path)
    parent = os.path.dirname(full)
    os.makedirs(parent, exist_ok=True)
    with open(full, 'w') as f:
        f.write(content)

def build_vault(n_commits=42):
    crypto = Vault__Crypto()
    api    = Vault__API__In_Memory()
    api.setup()
    sync   = Vault__Sync(crypto=crypto, api=api)

    snap_dir  = tempfile.mkdtemp(prefix='case-study-vault-')
    vault_dir = os.path.join(snap_dir, 'vault')
    vk        = sync.init(vault_dir)['vault_key']

    # Commit 0: write all files
    print(f'  Commit 0: writing {len(FILES)} initial files...')
    for rel, content in FILES:
        write_file(vault_dir, rel, content)
    sync.commit(vault_dir, 'initial: all content')

    # Commits 1..n_commits-1: modify 2-5 randomly chosen files
    for i in range(1, n_commits):
        n_changes = random.randint(2, 5)
        changed   = random.sample(FILES, n_changes)
        for rel, content in changed:
            new_content = content + f'\n\n<!-- revision {i} -->'
            write_file(vault_dir, rel, new_content)
        msg = f'agent update {i}: modified {len(changed)} files'
        sync.commit(vault_dir, msg)
        if i % 10 == 0:
            print(f'  Commit {i}/{n_commits - 1}...')

    sync.push(vault_dir)
    print(f'  Pushed. vault_key = {vk}')
    return vk, api, crypto, snap_dir, vault_dir

def run_analysis(vk, api, crypto, snap_dir):
    out_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'tests', 'fixtures', 'perf')
    os.makedirs(out_dir, exist_ok=True)

    sync = Vault__Sync(crypto=crypto, api=api)

    # --- profile clone ---
    print('\n[1/3] sgit dev profile clone ...')
    clone_dir = os.path.join(snap_dir, 'clone1')
    profiler  = Dev__Profile__Clone(crypto=crypto, api=api, sync=Vault__Sync(crypto=crypto, api=api))
    profile   = profiler.profile(vk, clone_dir)
    trace_path = os.path.join(out_dir, 'case-study-clone-baseline.json')
    with open(trace_path, 'w') as f:
        json.dump(profile.json(), f, indent=2)
    print(f'  Saved trace → {trace_path}')
    print(f'  total={profile.total_ms}ms  commits={profile.n_commits}  trees={profile.n_trees}  blobs={profile.n_blobs}')
    print(f'  t_commits={profile.t_commits_ms}ms  t_trees={profile.t_trees_ms}ms  t_blobs={profile.t_blobs_ms}ms  t_checkout={profile.t_checkout_ms}ms')

    # --- tree graph ---
    print('\n[2/3] sgit dev tree-graph ...')
    tg_tool = Dev__Tree__Graph(crypto=crypto, api=api, sync=Vault__Sync(crypto=crypto, api=api))
    tg      = tg_tool.analyse(vk)
    tg_path = os.path.join(out_dir, 'case-study-tree-graph.json')
    with open(tg_path, 'w') as f:
        json.dump(tg.json(), f, indent=2)
    print(f'  Saved tree-graph → {tg_path}')
    print(f'  n_commits={tg.n_commits}  unique_trees={tg.unique_trees}  total_tree_refs={tg.total_trees}  head_only={tg.head_only_trees}')
    dedup = tg.total_trees / max(tg.unique_trees, 1)
    h5_ratio = tg.head_only_trees / max(tg.unique_trees, 1)
    print(f'  dedup_ratio={dedup:.2f}x  h5_head_only_ratio={h5_ratio:.2%}')

    # --- server objects ---
    print('\n[3/3] sgit dev server-objects ...')
    so_tool = Dev__Server__Objects(crypto=crypto, api=api, sync=Vault__Sync(crypto=crypto, api=api))
    so      = so_tool.analyse(vk)
    so_path = os.path.join(out_dir, 'case-study-server-objects.json')
    with open(so_path, 'w') as f:
        json.dump(so.json(), f, indent=2)
    print(f'  Saved server-objects → {so_path}')
    print(f'  total={so.total_objects}  head_reachable={so.head_reachable}  history_only={so.history_only}')
    for t in so.by_type:
        print(f'    {t.obj_type:<12} {t.count}')

    return profile, tg, so

if __name__ == '__main__':
    print('=== Building synthetic case-study vault ===')
    print(f'  Structure: {len(FILES)} files, 42 commits')
    vk, api, crypto, snap_dir, vault_dir = build_vault(n_commits=42)
    try:
        print('\n=== Running B01 analysis tools ===')
        profile, tg, so = run_analysis(vk, api, crypto, snap_dir)
        print('\n=== Done ===')
    finally:
        shutil.rmtree(snap_dir, ignore_errors=True)
