"""Coverage test for sgit_ai/__main__.py.

Lines 1-3: executed when `python -m sgit_ai` is invoked.
We exec the file source so the coverage instrumentation sees lines 1-3 run in
this process (unlike subprocess, which runs in a separate coverage context).
"""
import sys
import importlib.util
import unittest.mock


def test_main_module_executes_lines_1_3():
    """Lines 1-3: load and exec __main__.py with mocked main()."""
    spec = importlib.util.find_spec('sgit_ai.__main__')
    assert spec is not None

    with unittest.mock.patch('sgit_ai.cli.main', side_effect=SystemExit(0)):
        try:
            # Force a fresh load of the module so lines 1-3 are executed
            loader = spec.loader
            module = importlib.util.module_from_spec(spec)
            loader.exec_module(module)
        except SystemExit as e:
            assert e.code == 0
