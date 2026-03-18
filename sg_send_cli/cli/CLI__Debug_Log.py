import sys
import time
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
        url         = self._truncate_url(entry['url'])
        sent        = self._format_size(entry['data_size'])
        recv        = self._format_size(entry['resp_size'])
        error       = entry.get('error', '')

        status_str = f'{status}' if status else '???'
        line = f'  [{method:<6}] {status_str:>3}  {duration_ms:>7.0f}ms  sent={sent:<8}  recv={recv:<8}  {url}'
        if error:
            line += f'  ERR: {error[:60]}'
        print(line, file=sys.stderr, flush=True)

    def _truncate_url(self, url: str) -> str:
        if len(url) <= 80:
            return url
        return url[:77] + '...'

    def _format_size(self, size: int) -> str:
        if size == 0:
            return '-'
        if size < 1024:
            return f'{size}B'
        if size < 1024 * 1024:
            return f'{size / 1024:.1f}KB'
        return f'{size / (1024 * 1024):.1f}MB'

    def print_summary(self):
        if not self.enabled or not self.entries:
            return
        total_duration = sum(e['duration'] for e in self.entries)
        total_sent     = sum(e['data_size'] for e in self.entries)
        total_recv     = sum(e['resp_size'] for e in self.entries)
        errors         = sum(1 for e in self.entries if e.get('error'))
        print(f'\n  --- Network Summary ---', file=sys.stderr)
        print(f'  Requests: {len(self.entries)}  |  Errors: {errors}  |  '
              f'Total: {total_duration * 1000:.0f}ms  |  '
              f'Sent: {self._format_size(total_sent)}  |  Recv: {self._format_size(total_recv)}',
              file=sys.stderr, flush=True)
