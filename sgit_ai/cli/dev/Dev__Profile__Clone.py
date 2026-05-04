"""Tool 1: sgit dev profile clone <vault-key> <directory>

Runs the clone path and emits per-phase timing without touching existing code.
The existing on_progress callback mechanism is the only hook used.
"""
import json
import sys
import time

from osbot_utils.type_safe.Type_Safe                        import Type_Safe
from sgit_ai.api.Vault__API__In_Memory                      import Vault__API__In_Memory
from sgit_ai.cli.dev.Schema__Profile__Clone                 import Schema__Profile__Clone, Schema__Profile__Clone__Phase
from sgit_ai.crypto.Vault__Crypto                           import Vault__Crypto
from sgit_ai.core.Vault__Sync                               import Vault__Sync


class Dev__Profile__Clone(Type_Safe):
    """Instrumented clone that emits per-phase wall-clock timing."""

    crypto : Vault__Crypto
    api    : object = None   # Vault__API or None → real server
    sync   : Vault__Sync

    def setup(self):
        if self.api is None:
            from sgit_ai.api.Vault__API import Vault__API
            self.api = Vault__API()
        self.sync = Vault__Sync(crypto=self.crypto, api=self.api)
        return self

    # ------------------------------------------------------------------
    # Core profiling logic
    # ------------------------------------------------------------------

    def profile(self, vault_key: str, directory: str, sparse: bool = False) -> Schema__Profile__Clone:
        """Clone vault_key into directory and return a filled Schema__Profile__Clone."""
        tracker = _PhaseTracker()

        t_total_start = time.monotonic()
        result = self.sync.clone(vault_key, directory,
                                 on_progress=tracker.on_progress, sparse=sparse)
        total_ms = int((time.monotonic() - t_total_start) * 1000)

        phases = []
        for name, dur_ms, count in tracker.phases:
            phases.append(Schema__Profile__Clone__Phase(
                name        = name,
                duration_ms = dur_ms,
                count       = count,
            ))

        output = Schema__Profile__Clone(
            vault_id      = result.get('vault_id', ''),
            directory     = directory,
            sparse        = 1 if sparse else 0,
            total_ms      = total_ms,
            n_commits     = tracker.n_commits,
            n_trees       = tracker.n_trees,
            n_blobs       = tracker.n_blobs,
            t_commits_ms  = tracker.t_commits_ms,
            t_trees_ms    = tracker.t_trees_ms,
            t_blobs_ms    = tracker.t_blobs_ms,
            t_checkout_ms = tracker.t_checkout_ms,
            phases        = phases,
        )
        return output

    # ------------------------------------------------------------------
    # CLI entry point
    # ------------------------------------------------------------------

    def cmd_profile_clone(self, args):
        vault_key = args.vault_key
        directory = args.directory
        sparse    = getattr(args, 'sparse', False)
        json_out  = getattr(args, 'json',   False)
        out_file  = getattr(args, 'output', None)

        self.setup()
        output = self.profile(vault_key, directory, sparse=sparse)

        if json_out:
            data = output.json()
            text = json.dumps(data, indent=2)
            if out_file:
                with open(out_file, 'w') as f:
                    f.write(text)
                print(f'Profile written to {out_file}')
            else:
                print(text)
        else:
            self._print_text(output)

    def _print_text(self, output: Schema__Profile__Clone):
        print(f'Clone profile: {output.vault_id}  →  {output.directory}')
        print(f'  Mode:      {"sparse" if output.sparse else "full"}')
        print(f'  Total:     {output.total_ms} ms')
        print()
        print(f'  Phase breakdown:')
        print(f'    commits:  {output.n_commits:>6} objects   {output.t_commits_ms:>7} ms')
        print(f'    trees:    {output.n_trees:>6} objects   {output.t_trees_ms:>7} ms')
        print(f'    blobs:    {output.n_blobs:>6} objects   {output.t_blobs_ms:>7} ms')
        print(f'    checkout:                   {output.t_checkout_ms:>7} ms')


class _PhaseTracker:
    """Stateful callback that accumulates timing by listening to on_progress events."""

    def __init__(self):
        self.phases        = []            # list of (name, dur_ms, count)
        self.n_commits     = 0
        self.n_trees       = 0
        self.n_blobs       = 0
        self.t_commits_ms  = 0
        self.t_trees_ms    = 0
        self.t_blobs_ms    = 0
        self.t_checkout_ms = 0
        self._phase_start  = {}            # phase_name → t0

    def on_progress(self, event: str, label: str, detail: str = ''):
        if event == 'scan':
            if label not in self._phase_start:
                self._phase_start[label] = time.monotonic()
        elif event == 'scan_done':
            t0  = self._phase_start.pop(label, time.monotonic())
            dur = int((time.monotonic() - t0) * 1000)
            # parse count from detail like "42 commits"
            count = 0
            try:
                count = int(detail.split()[0])
            except (ValueError, IndexError):
                pass

            key = label.lower().split()[-1]   # 'Walking commits' → 'commits'
            self.phases.append((key, dur, count))

            if key == 'commits':
                self.n_commits    = count
                self.t_commits_ms = dur
            elif key == 'trees':
                self.n_trees    = count
                self.t_trees_ms = dur
            elif key == 'blobs':
                self.n_blobs    = count
                self.t_blobs_ms = dur
        elif event == 'stats':
            # Parse from 'commits Xs  trees Xs  blobs Xs  checkout Xs  (N commits, M blobs)'
            for part in label.split('  '):
                part = part.strip()
                if part.startswith('checkout'):
                    try:
                        secs = float(part.split()[1].rstrip('s'))
                        self.t_checkout_ms = int(secs * 1000)
                    except (ValueError, IndexError):
                        pass
                elif part.startswith('(') and 'blobs' in part:
                    # e.g. '(1 commits, 2 blobs)'
                    import re as _re
                    m = _re.search(r'(\d+)\s+blobs', part)
                    if m:
                        self.n_blobs = int(m.group(1))
