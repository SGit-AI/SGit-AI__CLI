"""Container__Runtimes — which runtimes this machine has, and which one `sgit serve` uses.

Order of preference, per OS, among the runtimes that apply:
  macOS   : Apple container, Docker, Podman, nerdctl, Finch, then uv (no container)
  Linux   : Docker, Podman, nerdctl, Finch, then uv
  Windows : Docker, Podman, then uv
One that is installed and answering wins; then one that is installed and can be started
(Podman's machine, Apple container's service); `--runtime NAME` overrides the order.
"""
from   osbot_utils.type_safe.Type_Safe                  import Type_Safe
from   sgit_ai.core.serve.Container__Command_Runner      import Container__Command_Runner
from   sgit_ai.core.serve.Container__Host                import Container__Host
from   sgit_ai.core.serve.Container__Runtime__Apple      import Container__Runtime__Apple
from   sgit_ai.core.serve.Container__Runtime__Docker     import Container__Runtime__Docker
from   sgit_ai.core.serve.Container__Runtime__Uv         import Container__Runtime__Uv


class Container__Runtimes(Type_Safe):
    runner : Container__Command_Runner
    host   : Container__Host

    def all(self) -> list:
        """Every runtime that applies to this OS, in order of preference."""
        def docker_like(cli):
            return Container__Runtime__Docker(cli=cli, runner=self.runner, host=self.host)
        apple = Container__Runtime__Apple(runner=self.runner, host=self.host)
        uv    = Container__Runtime__Uv   (runner=self.runner, host=self.host)
        if self.host.is_windows():
            order = [docker_like('docker'), docker_like('podman'), uv]
        else:
            order = [apple, docker_like('docker'), docker_like('podman'), docker_like('nerdctl'),
                     docker_like('finch'), uv]
        return [r for r in order if r.applies()]

    def by_name(self, name: str):
        for runtime in self.all():
            if runtime.name() == name:
                return runtime
        return None

    def report(self) -> list:
        """[dict(name, describe, installed, ready)] for `sgit serve runtimes`."""
        rows = []
        for runtime in self.all():
            installed = runtime.available()
            rows.append(dict(name=runtime.name(), describe=runtime.describe(), installed=installed,
                             ready=installed and runtime.ready()))
        return rows

    def pick(self, name: str = None, start: bool = True):
        """The runtime to use, started if needed; None when nothing usable is installed.
        Raises ValueError for an unknown or unusable `name`."""
        if name:
            runtime = self.by_name(name)
            if runtime is None:
                raise ValueError(f'unknown runtime {name!r} on this machine (one of: '
                                 f'{", ".join(r.name() for r in self.all())})')
            if not runtime.available():
                raise ValueError(f'{runtime.describe()} is not installed: sgit serve install {runtime.name()}')
            if not runtime.ready() and not (start and runtime.start_service()):
                raise ValueError(runtime.not_ready_hint())
            return runtime
        installed  = [r for r in self.all() if r.available()]
        containers = [r for r in installed if r.is_container_runtime()]
        for runtime in containers:                                      # a container runtime that answers
            if runtime.ready():
                return runtime
        if start:
            for runtime in containers:                                  # one whose service/VM can be started
                if runtime.start_service_argvs() and runtime.start_service():
                    return runtime
        for runtime in installed:                                       # then the no-container engine
            if not runtime.is_container_runtime() and runtime.ready():
                return runtime
        return None
