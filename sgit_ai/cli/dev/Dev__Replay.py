"""Tool 5: sgit dev replay <trace.json> [--diff <other-trace.json>]

Replays a clone trace offline (no network). The trace is produced by
`sgit dev profile clone --json`. Supports diff mode to compare two traces.
"""
import json

from osbot_utils.type_safe.Type_Safe               import Type_Safe
from sgit_ai.cli.dev.Schema__Replay                import Schema__Replay, Schema__Replay__Phase__Diff
from sgit_ai.cli.dev.Schema__Profile__Clone        import Schema__Profile__Clone


class Dev__Replay(Type_Safe):
    """Offline trace replay — no network, no vault connection required."""

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def load_trace(self, path: str) -> Schema__Profile__Clone:
        """Load a trace JSON file (written by dev profile clone --json)."""
        with open(path, 'r') as f:
            data = json.load(f)
        return Schema__Profile__Clone.from_json(data)

    def replay(self, trace_path: str) -> Schema__Replay:
        """Return a Schema__Replay summarising one trace."""
        trace = self.load_trace(trace_path)
        return self._trace_to_replay(trace, trace_path)

    def replay_diff(self, trace_a_path: str, trace_b_path: str) -> Schema__Replay:
        """Return a Schema__Replay with diff_phases comparing two traces."""
        a     = self.load_trace(trace_a_path)
        b     = self.load_trace(trace_b_path)
        base  = self._trace_to_replay(a, trace_a_path)

        diff_phases = []
        phase_keys  = [('commits', a.t_commits_ms,  b.t_commits_ms),
                       ('trees',   a.t_trees_ms,    b.t_trees_ms),
                       ('blobs',   a.t_blobs_ms,    b.t_blobs_ms),
                       ('checkout',a.t_checkout_ms, b.t_checkout_ms)]

        for name, a_ms, b_ms in phase_keys:
            delta   = int(b_ms) - int(a_ms)
            sign    = '+' if delta >= 0 else ''
            pct     = (delta / max(int(a_ms), 1)) * 100
            diff_phases.append(Schema__Replay__Phase__Diff(
                phase      = name,
                a_ms       = int(a_ms),
                b_ms       = int(b_ms),
                delta_ms   = f'{sign}{delta} ms',
                pct_change = f'{sign}{pct:.0f}%',
            ))

        base.diff_phases = diff_phases
        return base

    def _trace_to_replay(self, trace: Schema__Profile__Clone, path: str) -> Schema__Replay:
        return Schema__Replay(
            trace_file    = path,
            vault_id      = str(trace.vault_id),
            n_commits     = int(trace.n_commits),
            n_trees       = int(trace.n_trees),
            n_blobs       = int(trace.n_blobs),
            total_ms      = int(trace.total_ms),
            t_commits_ms  = int(trace.t_commits_ms),
            t_trees_ms    = int(trace.t_trees_ms),
            t_blobs_ms    = int(trace.t_blobs_ms),
            t_checkout_ms = int(trace.t_checkout_ms),
        )

    # ------------------------------------------------------------------
    # CLI entry point
    # ------------------------------------------------------------------

    def cmd_replay(self, args):
        trace_path = args.trace
        diff_path  = getattr(args, 'diff', None)
        json_out   = getattr(args, 'json', False)

        if diff_path:
            output = self.replay_diff(trace_path, diff_path)
        else:
            output = self.replay(trace_path)

        if json_out:
            print(json.dumps(output.json(), indent=2))
        else:
            self._print_text(output, diff_mode=bool(diff_path))

    def _print_text(self, output: Schema__Replay, diff_mode: bool = False):
        print(f'Replay: {output.trace_file}')
        print(f'  Vault:    {output.vault_id}')
        print(f'  Total:    {output.total_ms} ms')
        print(f'  Commits:  {output.n_commits}   trees: {output.n_trees}   blobs: {output.n_blobs}')
        print()
        print(f'  Phase timing:')
        print(f'    commits:   {output.t_commits_ms:>7} ms')
        print(f'    trees:     {output.t_trees_ms:>7} ms')
        print(f'    blobs:     {output.t_blobs_ms:>7} ms')
        print(f'    checkout:  {output.t_checkout_ms:>7} ms')

        if diff_mode and output.diff_phases:
            print()
            print('  Phase diff (A vs B):')
            print(f'    {"phase":<12}  {"A ms":>8}  {"B ms":>8}  {"delta":>10}  {"change":>8}')
            for d in output.diff_phases:
                print(f'    {str(d.phase):<12}  {d.a_ms:>8}  {d.b_ms:>8}  '
                      f'{str(d.delta_ms):>10}  {str(d.pct_change):>8}')
