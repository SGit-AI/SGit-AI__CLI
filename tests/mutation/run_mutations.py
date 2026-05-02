#!/usr/bin/env python3
"""Mutation test orchestrator using git worktree isolation.

Usage:
    python tests/mutation/run_mutations.py [--report PATH] [--ids M1,M7,B5]

Each mutation is run in an isolated git worktree so:
  - The main working tree is never mutated.
  - Python's import cache (sys.modules) cannot see a mutation from a prior run.
  - Signal interrupts cannot leave a live mutation in the main tree.

Output:
  - A human-readable summary table to stdout.
  - A JSON report written to --report (default: mutation-report.json).

Exit code:
  0 — all mutations were detected (all tests failed under mutation, as expected).
  1 — at least one mutation was NOT detected (test gap) OR could not be applied
      (stale catalogue — old string not found in the target file).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Import the mutation catalogue from the same package
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))  # repo root

from tests.mutation.mutations import MUTATIONS  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_root() -> str:
    """Return the absolute path to the repository root."""
    result = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],
        capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _worktree_path(mutation_id: str) -> str:
    return os.path.join(tempfile.gettempdir(), f'mut-{mutation_id}')


def _create_worktree(repo_root: str, worktree: str) -> bool:
    """Create a detached worktree at HEAD.  Returns True on success."""
    # Remove stale worktree if it exists from a previous interrupted run.
    if os.path.isdir(worktree):
        subprocess.run(
            ['git', 'worktree', 'remove', '--force', worktree],
            capture_output=True, cwd=repo_root
        )
    result = subprocess.run(
        ['git', 'worktree', 'add', '--detach', worktree, 'HEAD'],
        capture_output=True, text=True, cwd=repo_root
    )
    return result.returncode == 0


def _remove_worktree(repo_root: str, worktree: str) -> None:
    """Remove the worktree unconditionally."""
    subprocess.run(
        ['git', 'worktree', 'remove', '--force', worktree],
        capture_output=True, cwd=repo_root
    )


def _apply_mutation(worktree: str, mutation: dict) -> bool:
    """Apply mutation via str.replace; returns True if old string was found."""
    rel_file  = mutation['file']
    full_path = os.path.join(worktree, rel_file)
    if not os.path.isfile(full_path):
        return False
    with open(full_path, 'r', encoding='utf-8') as fh:
        original = fh.read()
    if mutation['old'] not in original:
        return False
    mutated = original.replace(mutation['old'], mutation['new'], 1)
    with open(full_path, 'w', encoding='utf-8') as fh:
        fh.write(mutated)
    return True


def _run_tests(worktree: str) -> subprocess.CompletedProcess:
    """Run the unit test suite in the worktree.  Returns the CompletedProcess."""
    # Use the same pytest that is on PATH; fall back to 'python -m pytest'.
    pytest_cmd = shutil_which('pytest') or [sys.executable, '-m', 'pytest']
    if isinstance(pytest_cmd, str):
        pytest_cmd = [pytest_cmd]
    cmd = pytest_cmd + ['tests/unit/', '-x', '--tb=no', '-q']

    # CRITICAL: Set PYTHONPATH to the worktree root so the mutated source
    # takes precedence over any editable-install pointing at the main tree.
    env = os.environ.copy()
    existing_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = worktree + ((':' + existing_pythonpath) if existing_pythonpath else '')

    return subprocess.run(
        cmd,
        capture_output=True, text=True,
        cwd=worktree,
        env=env,
        timeout=300,  # 5-minute ceiling per mutation
    )


def shutil_which(name: str):
    """Return the full path to *name* on PATH, or None."""
    import shutil
    return shutil.which(name)


# ---------------------------------------------------------------------------
# Core orchestration
# ---------------------------------------------------------------------------

def run_mutations(
    mutations: list,
    repo_root: str,
    report_path: str,
    verbose: bool = False,
) -> list:
    """Run each mutation in its own worktree.  Return a list of result dicts."""
    results = []
    total   = len(mutations)

    print(f'\n{"="*64}')
    print(f'Mutation test suite — {total} mutations')
    print(f'Repo: {repo_root}')
    print(f'{"="*64}\n')
    print(f'{"ID":<6} {"STATUS":<12} {"NOTES":<44}')
    print(f'{"-"*6} {"-"*12} {"-"*44}')

    for idx, mut in enumerate(mutations, 1):
        mid      = mut['id']
        worktree = _worktree_path(mid)
        result   = {
            'id'          : mid,
            'description' : mut['description'],
            'file'        : mut['file'],
            'detected'    : False,
            'applied'     : False,
            'error'       : None,
            'returncode'  : None,
        }

        try:
            # 1. Create isolated worktree
            if not _create_worktree(repo_root, worktree):
                result['error'] = 'failed to create worktree'
                print(f'{mid:<6} {"ERROR":<12} worktree creation failed')
                results.append(result)
                continue

            # 2. Apply mutation
            applied = _apply_mutation(worktree, mut)
            result['applied'] = applied
            if not applied:
                result['error'] = f"old string not found in {mut['file']}"
                print(f'{mid:<6} {"SKIP":<12} old string not found in {mut["file"]}')
                results.append(result)
                continue

            # 3. Run tests
            proc = _run_tests(worktree)
            result['returncode'] = proc.returncode
            detected             = proc.returncode != 0
            result['detected']   = detected

            status = 'DETECTED' if detected else 'MISSED'
            notes  = ''
            if verbose and not detected:
                notes = '← test gap!'
            print(f'{mid:<6} {status:<12} {notes}')

        except subprocess.TimeoutExpired:
            result['error'] = 'pytest timed out (>300 s)'
            print(f'{mid:<6} {"TIMEOUT":<12} pytest exceeded 5-minute limit')

        except Exception as exc:
            result['error'] = str(exc)
            print(f'{mid:<6} {"ERROR":<12} {exc}')

        finally:
            # Always remove the worktree — even if tests crashed
            _remove_worktree(repo_root, worktree)

        results.append(result)

    # Summary
    detected_count = sum(1 for r in results if r['detected'])
    missed         = [r['id'] for r in results if not r['detected'] and r['applied'] and not r['error']]
    skipped        = [r['id'] for r in results if not r['applied']]
    errors         = [r['id'] for r in results if r['error'] and r['applied'] is not False]

    print(f'\n{"="*64}')
    print(f'Detected : {detected_count}/{len(results)}')
    if missed:
        print(f'MISSED   : {", ".join(missed)}  ← test gaps!')
    if skipped:
        print(f'SKIPPED  : {", ".join(skipped)}  ← stale catalogue (old string not found)!')
    if errors:
        print(f'Errors   : {", ".join(errors)}')
    print(f'{"="*64}\n')

    # Write JSON report
    with open(report_path, 'w', encoding='utf-8') as fh:
        json.dump({
            'total'    : len(results),
            'detected' : detected_count,
            'missed'   : missed,
            'skipped'  : skipped,
            'errors'   : errors,
            'results'  : results,
        }, fh, indent=2)
    print(f'Report written to: {report_path}')

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Run mutation tests using git worktree isolation.'
    )
    parser.add_argument(
        '--report',
        default='mutation-report.json',
        help='Path for the JSON result report (default: mutation-report.json)',
    )
    parser.add_argument(
        '--ids',
        default='',
        help='Comma-separated list of mutation IDs to run (default: all). '
             'Example: --ids M1,M7,B5',
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print extra diagnostic info for missed mutations.',
    )
    args = parser.parse_args()

    repo_root = _repo_root()

    # Filter to requested IDs if given
    mutations = MUTATIONS
    if args.ids:
        requested = {mid.strip().upper() for mid in args.ids.split(',')}
        mutations = [m for m in MUTATIONS if m['id'].upper() in requested]
        if not mutations:
            print(f'No mutations matched: {args.ids}', file=sys.stderr)
            sys.exit(1)

    results = run_mutations(
        mutations  = mutations,
        repo_root  = repo_root,
        report_path= args.report,
        verbose    = args.verbose,
    )

    # Exit 1 if any mutation was missed (test gap) or skipped (stale catalogue)
    missed  = [r for r in results if not r['detected'] and r['applied'] and not r['error']]
    skipped = [r for r in results if not r['applied']]
    sys.exit(1 if (missed or skipped) else 0)


if __name__ == '__main__':
    main()
