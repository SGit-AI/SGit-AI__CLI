import sys
import time

from osbot_utils.type_safe.Type_Safe import Type_Safe


class CLI__Progress(Type_Safe):

    def callback(self, phase: str, message: str, detail: str = ''):
        if phase == 'header':
            print(message, flush=True)
        elif phase == 'step':
            if detail:
                print(f'  ▸ {message} ({detail})', flush=True)
            else:
                print(f'  ▸ {message}', flush=True)
        elif phase == 'done':
            print(message, flush=True)
        elif phase == 'file_add':
            print(f'  + {message}', flush=True)
        elif phase == 'file_mod':
            print(f'  ~ {message}', flush=True)
        elif phase == 'file_del':
            print(f'  - {message}', flush=True)
        elif phase == 'warn':
            print(f'  ⚠ {message}', flush=True)
        elif phase == 'upload':
            self._render_progress_bar(message, detail)
        elif phase == 'download':
            self._render_progress_bar(message, detail)
        elif phase == 'scan':
            line = f'  ▸ {message}: {detail}'
            print(f'\r{line:<79}', end='', flush=True)
        elif phase == 'scan_done':
            line = f'  ▸ {message}: {detail}'
            print(f'\r{line:<79}', flush=True)
        elif phase == 'commit':
            entry = f'  ↳ {message}  {detail}'
            if len(entry) > 79:
                entry = entry[:76] + '...'
            print(entry, flush=True)
        elif phase == 'stats':
            print(f'  ⏱ {message}', flush=True)

    def _render_progress_bar(self, label: str, fraction_str: str):
        try:
            current, total = fraction_str.split('/')
            current = int(current)
            total   = int(total)
        except (ValueError, AttributeError):
            print(f'  ▸ {label}', flush=True)
            return

        bar_width = 20
        filled    = int(bar_width * current / max(total, 1))
        bar       = '█' * filled + '░' * (bar_width - filled)

        line = f'\r  ▸ {label} [{bar}] {current}/{total}'
        if current >= total:
            print(line, flush=True)
        else:
            print(line, end='', flush=True)
