import os
import time
from urllib.parse                                          import urlparse
from osbot_utils.type_safe.Type_Safe                      import Type_Safe
from sgit_ai.safe_types.Enum__Doctor_Status           import Enum__Doctor_Status
from sgit_ai.schemas.Schema__Doctor__Check            import Schema__Doctor__Check

LOOPBACK_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0', '::1'}


class Check__Loopback_Container_Warn(Type_Safe):

    def execute(self, ctx, tcp_failed: bool = False) -> Schema__Doctor__Check:
        t0     = time.monotonic()
        result = Schema__Doctor__Check(name='loopback_container_warn')
        parsed = urlparse(str(ctx.url))
        host   = (parsed.hostname or '').lower()

        if host not in LOOPBACK_HOSTS:
            result.status      = Enum__Doctor_Status.SKIP
            result.message     = 'n/a'
            result.duration_ms = int((time.monotonic() - t0) * 1000)
            return result

        container_marker, suggested_host = _detect_container()

        if tcp_failed:
            if container_marker:
                hint = (
                    f'🐳 Container detected — {container_marker}\n\n'
                    f'    You appear to be running sgit inside a container.\n'
                    f"    The address '{host}' inside the container is the CONTAINER's own\n"
                    f'    loopback, NOT the host machine\'s. Your SG/API server is on the host.\n\n'
                    f'    Try one of these instead:\n'
                    f'      • {suggested_host}  (container bridge)\n'
                    f'      • host.docker.internal      (Docker Desktop bridge)\n'
                    f'      • Your host\'s LAN IP        (e.g. 192.168.1.42)\n\n'
                    f'    To fix:\n'
                    f'      sgit vault remote set-url origin http://{suggested_host}:{parsed.port or 80}\n'
                    f'      sgit doctor'
                )
            else:
                hint = (
                    f"Cannot reach '{host}:{parsed.port or 80}' — is the server actually running on this port?\n"
                    f'    • Check: curl http://{host}:{parsed.port or 80}/api/info\n'
                    f'    • If the server is inside a container, use the host bridge address instead.'
                )
            result.status  = Enum__Doctor_Status.WARN
            result.message = f'loopback host ({host}) — see hint'
            result.hint    = hint
        else:
            result.status  = Enum__Doctor_Status.PASS
            result.message = f'loopback host ({host}), connection succeeded'

        result.duration_ms = int((time.monotonic() - t0) * 1000)
        return result


def _detect_container() -> tuple:
    if os.path.exists('/run/.containerenv'):
        return '/run/.containerenv present', 'host.containers.internal'
    if os.path.exists('/.dockerenv'):
        return '/.dockerenv present', 'host.docker.internal'
    if os.environ.get('container') == 'oci':
        return '$container=oci', 'host.containers.internal'
    try:
        with open('/proc/1/cgroup') as f:
            content = f.read()
        for runtime in ('docker', 'kubepods', 'containerd'):
            if runtime in content:
                return f'/proc/1/cgroup contains {runtime}', 'host.containers.internal'
    except OSError:
        pass
    return '', ''
