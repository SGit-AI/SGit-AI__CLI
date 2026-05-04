"""Tool 4: sgit dev step-clone <vault-key> <directory>

A clone that pauses between phases. After each phase it prints what
happened and waits for <Enter> to proceed (--no-pause skips interactive).

The existing on_progress callback is the only hook; no main-command code
is modified.
"""
import json
import sys
import time

from osbot_utils.type_safe.Type_Safe                    import Type_Safe
from sgit_ai.cli.dev.Schema__Step__Clone                import Schema__Step__Clone, Schema__Step__Clone__Event
from sgit_ai.crypto.Vault__Crypto                       import Vault__Crypto
from sgit_ai.core.Vault__Sync                           import Vault__Sync


class Dev__Step__Clone(Type_Safe):
    """Pausable clone with per-phase progress output."""

    crypto : Vault__Crypto
    api    : object = None
    sync   : Vault__Sync

    def setup(self):
        if self.api is None:
            from sgit_ai.network.api.Vault__API import Vault__API
            self.api = Vault__API()
        self.sync = Vault__Sync(crypto=self.crypto, api=self.api)
        return self

    # ------------------------------------------------------------------
    # Core step-clone logic
    # ------------------------------------------------------------------

    def step_clone(self, vault_key: str, directory: str,
                   no_pause: bool = True,
                   on_pause: callable = None) -> Schema__Step__Clone:
        """Clone with per-step pauses; on_pause(event) replaces input() when no_pause=False."""
        tracker   = _StepTracker(no_pause=no_pause, on_pause=on_pause)
        t0        = time.monotonic()
        result    = self.sync.clone(vault_key, directory, on_progress=tracker.on_progress)
        total_ms  = int((time.monotonic() - t0) * 1000)

        return Schema__Step__Clone(
            vault_id  = result.get('vault_id', ''),
            directory = directory,
            commit_id = result.get('commit_id', ''),
            total_ms  = total_ms,
            n_steps   = len(tracker.events),
            events    = tracker.events,
        )

    # ------------------------------------------------------------------
    # CLI entry point
    # ------------------------------------------------------------------

    def cmd_step_clone(self, args):
        vault_key = args.vault_key
        directory = args.directory
        no_pause  = getattr(args, 'no_pause', True)
        json_out  = getattr(args, 'json',     False)

        self.setup()
        output = self.step_clone(vault_key, directory, no_pause=no_pause)

        if json_out:
            print(json.dumps(output.json(), indent=2))
        else:
            self._print_text(output)

    def _print_text(self, output: Schema__Step__Clone):
        print(f'Step-clone: {output.vault_id}  →  {output.directory}')
        print(f'  Total: {output.total_ms} ms   Steps: {output.n_steps}')
        print()
        for ev in output.events:
            label  = str(ev.label)
            detail = str(ev.detail)
            ms     = ev.elapsed_ms
            suffix = f'  [{detail}]' if detail else ''
            print(f'  [{ms:>6} ms]  {label}{suffix}')


class _StepTracker:
    """Collects step/scan_done/stats events for the step-clone record."""

    def __init__(self, no_pause: bool = True, on_pause: callable = None):
        self.events   : list = []
        self.no_pause = no_pause
        self.on_pause = on_pause
        self._t0      = time.monotonic()

    def on_progress(self, event: str, label: str, detail: str = ''):
        if event not in ('step', 'scan_done', 'stats'):
            return
        elapsed = int((time.monotonic() - self._t0) * 1000)
        ev = Schema__Step__Clone__Event(
            index      = len(self.events),
            event      = event,
            label      = label,
            detail     = detail,
            elapsed_ms = elapsed,
        )
        self.events.append(ev)

        if not self.no_pause:
            self._pause(ev)

    def _pause(self, ev: Schema__Step__Clone__Event):
        msg = f'[step {ev.index}] {ev.label}'
        if str(ev.detail):
            msg += f': {ev.detail}'
        if self.on_pause:
            self.on_pause(ev)
        else:
            print(f'\n{msg}')
            print('Press <Enter> to continue...', end='', flush=True)
            sys.stdin.readline()
