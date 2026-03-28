import sys
import time
from urllib.parse import unquote
from osbot_utils.type_safe.Type_Safe import Type_Safe


class CLI__Debug_Log(Type_Safe):
    enabled  : bool
    entries  : list

    def log_request(self, method: str, url: str, data_size: int = 0) -> dict:
        entry = {'method'    : method,
                 'url'       : url,
                 'data_size' : data_size,
                 'start'     : time.monotonic(),
                 'status'    : 0,
                 'resp_size' : 0,
                 'duration'  : 0.0,
                 'error'     : ''}
        self.entries.append(entry)
        return entry

    def log_response(self, entry: dict, status: int, resp_size: int):
        entry['status']   = status
        entry['resp_size'] = resp_size
        entry['duration'] = time.monotonic() - entry['start']
        self._print_entry(entry)

    def log_error(self, entry: dict, status: int, error_msg: str):
        entry['status']   = status
        entry['error']    = error_msg
        entry['duration'] = time.monotonic() - entry['start']
        self._print_entry(entry)

    def _print_entry(self, entry: dict):
        if not self.enabled:
            return
        duration_ms = entry['duration'] * 1000
        status      = entry['status']
        method      = entry['method']
        path        = self._format_path(entry['url'])
        sent        = self._format_size(entry['data_size'])
        recv        = self._format_size(entry['resp_size'])
        error       = entry.get('error', '')

        status_str = f'{status}' if status else '???'
        line = f'    [{method:<6}] {status_str:>3}  {duration_ms:>6.0f}ms  {sent:>6}  {recv:>6}  {path}'
        if error:
            line += f'  ERR: {error[:60]}'
        print(line, file=sys.stderr, flush=True)

    def _format_path(self, url: str) -> str:
        path = url
        for prefix in ['https://', 'http://']:
            if path.startswith(prefix):
                path = path[len(prefix):]
                slash = path.find('/')
                if slash >= 0:
                    path = path[slash:]
                break
        if path.startswith('/api/'):
            path = path[5:]
        path = unquote(path)
        if len(path) > 70:
            path = path[:67] + '...'
        return path

    def _format_size(self, size: int) -> str:
        if size == 0:
            return '-'
        if size < 1024:
            return f'{size} B'
        if size < 1024 * 1024:
            return f'{size / 1024:.1f} KB'
        return f'{size / (1024 * 1024):.1f} MB'

    def print_header(self):
        if not self.enabled:
            return
        print('', file=sys.stderr)
        print('  ┌─────────────────────────────────────────────────────────────────┐', file=sys.stderr)
        print('  │  SG/Send CLI — Network Debug                                    │', file=sys.stderr)
        print('  └─────────────────────────────────────────────────────────────────┘', file=sys.stderr)
        print('    Method  Status    Time    Sent    Recv  Path', file=sys.stderr)
        print('    ──────  ──────  ──────  ──────  ──────  ─────────────────────────', file=sys.stderr, flush=True)

    def print_summary(self):
        if not self.enabled or not self.entries:
            return
        # Wall-clock elapsed = span from first request start to last request end
        wall_elapsed = (max(e['start'] + e['duration'] for e in self.entries)
                        - min(e['start'] for e in self.entries))
        total_sent   = sum(e['data_size'] for e in self.entries)
        total_recv   = sum(e['resp_size'] for e in self.entries)
        errors       = sum(1 for e in self.entries if e.get('error'))
        print('    ──────  ──────  ──────  ──────  ──────  ─────────────────────────', file=sys.stderr)
        print(f'    Reqs: {len(self.entries)}  |  Errors: {errors}  |  '
              f'Elapsed: {wall_elapsed * 1000:.0f}ms  |  '
              f'Sent: {self._format_size(total_sent)}  |  Recv: {self._format_size(total_recv)}',
              file=sys.stderr, flush=True)
