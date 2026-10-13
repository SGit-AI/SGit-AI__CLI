"""Container__Runtime — one container runtime, as `sgit serve` drives it.

`sgit serve` runs the SG/Send vault image (UI + API + disk store) on the user's machine.
Each runtime is an adapter that turns the same few intentions into its own argv:
ready? start its service, pull, run, is it running, logs, stop, which digest ran. The
argv-building methods are separate from the running so the exact command lines are tested.

A run spec is a plain dict: image, name, bind, host_port, data_dir, user, env.
"""
from   osbot_utils.type_safe.Type_Safe                  import Type_Safe
from   sgit_ai.core.serve.Container__Command_Runner      import Container__Command_Runner
from   sgit_ai.core.serve.Container__Host                import Container__Host

CONTAINER_PORT = 8080                                 # the port the SG/Send image listens on
PULL_TIMEOUT   = 900


class Container__Runtime(Type_Safe):
    runner : Container__Command_Runner
    host   : Container__Host

    # ------------------------------------------------------------- identity
    def name(self) -> str:
        raise NotImplementedError

    def binary(self) -> str:
        return self.name()

    def describe(self) -> str:
        return self.name()

    def is_container_runtime(self) -> bool:
        return True

    # --------------------------------------------------------------- probing
    def applies(self) -> bool:
        """Can this runtime exist on this OS at all?"""
        return True

    def available(self) -> bool:
        return self.applies() and bool(self.runner.which(self.binary()))

    def ready_argv(self) -> list:
        return [self.binary(), 'info']

    def ready(self) -> bool:
        return self.available() and self.runner.run(self.ready_argv(), timeout=60)['code'] == 0

    def start_service_argvs(self) -> list:
        """Commands that bring the runtime's service or VM up, in order ([] = nothing to start)."""
        return []

    def not_ready_hint(self) -> str:
        return f'{self.name()} is installed but not answering (`{" ".join(self.ready_argv())}` failed)'

    # ------------------------------------------------------------- commands
    def pull_argv(self, image: str) -> list:
        return [self.binary(), 'pull', image]

    def run_argv(self, spec: dict) -> list:
        raise NotImplementedError

    def stop_argv(self, name: str) -> list:
        return [self.binary(), 'stop', name]

    def remove_argv(self, name: str) -> list:
        return [self.binary(), 'rm', '-f', name]

    def logs_argv(self, name: str, follow: bool = False) -> list:
        return [self.binary(), 'logs'] + (['-f'] if follow else []) + [name]

    def running_argv(self, name: str) -> list:
        return [self.binary(), 'inspect', '--format', '{{.State.Running}}', name]

    def digest_argv(self, image: str) -> list:
        return [self.binary(), 'image', 'inspect', '--format', '{{index .RepoDigests 0}}', image]

    # ------------------------------------------------------------- actions
    def start_service(self) -> bool:
        for argv in self.start_service_argvs():
            self.runner.run(argv, timeout=PULL_TIMEOUT)                # "already exists / already running" is fine
        return self.ready()

    def pull(self, image: str) -> dict:
        return self.runner.run(self.pull_argv(image), timeout=PULL_TIMEOUT)

    def run(self, spec: dict) -> dict:
        self.runner.run(self.remove_argv(spec['name']), timeout=60)    # a stopped leftover with this name
        return self.runner.run(self.run_argv(spec), timeout=120)

    def stop(self, name: str) -> dict:
        result = self.runner.run(self.stop_argv(name), timeout=60)
        self.runner.run(self.remove_argv(name), timeout=60)
        return result

    def running(self, name: str) -> bool:
        result = self.runner.run(self.running_argv(name), timeout=30)
        return result['code'] == 0 and result['out'].strip().lower() == 'true'

    def digest(self, image: str) -> str:
        result = self.runner.run(self.digest_argv(image), timeout=30)
        return result['out'].strip() if result['code'] == 0 else ''

    def logs(self, name: str, follow: bool = False) -> int:
        return self.runner.run_visible(self.logs_argv(name, follow))

    # ------------------------------------------------------------- helpers
    def env_flags(self, spec: dict) -> list:
        flags = []
        for key, value in sorted((spec.get('env') or {}).items()):
            flags += ['-e', f'{key}={value}']
        return flags

    def publish_flag(self, spec: dict) -> str:
        """Always bound to an address (127.0.0.1 by default): a bare `-p 8080:8080`
        publishes on every interface."""
        return f'{spec["bind"]}:{int(spec["host_port"])}:{CONTAINER_PORT}'
