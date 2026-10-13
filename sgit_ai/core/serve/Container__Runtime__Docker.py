"""Container__Runtime__Docker — every runtime with a docker-compatible CLI: docker, podman,
nerdctl, finch. They share `run -d --name -p -v -e --user`, `inspect`, `logs`, `stop`, `pull`.

Differences handled here:
  * the image runs as uid 10001, so the host data folder is only writable when the
    container runs as the host user: `--user <uid>:<gid>` (verified 2026-10-12);
  * podman is rootless: `--userns=keep-id` maps the host user into the container, and on
    Linux `:Z` relabels the data folder for SELinux;
  * podman on macOS/Windows and finch run a VM that must be started first.
"""
from   sgit_ai.safe_types.Safe_Str__Container_Runtime  import Safe_Str__Container_Runtime
from   sgit_ai.core.serve.Container__Runtime            import Container__Runtime

DOCKER_COMPATIBLE = ('docker', 'podman', 'nerdctl', 'finch')


class Container__Runtime__Docker(Container__Runtime):
    cli : Safe_Str__Container_Runtime = 'docker'

    def name(self) -> str:
        return str(self.cli)

    def describe(self) -> str:
        return {'docker' : 'Docker (Engine or Desktop)',
                'podman' : 'Podman',
                'nerdctl': 'nerdctl (containerd)',
                'finch'  : 'Finch'}.get(self.name(), self.name())

    def start_service_argvs(self) -> list:
        if self.name() == 'podman' and not self.host.is_linux():
            return [['podman', 'machine', 'init'], ['podman', 'machine', 'start']]
        if self.name() == 'finch':
            return [['finch', 'vm', 'init'], ['finch', 'vm', 'start']]
        return []

    def not_ready_hint(self) -> str:
        if self.name() == 'docker':
            return ('Docker is installed but its daemon is not running: start Docker Desktop, or '
                    '`sudo systemctl start docker` on Linux')
        if self.name() == 'podman' and not self.host.is_linux():
            return 'Podman is installed but its machine is not running: `podman machine start`'
        return super().not_ready_hint()

    def run_argv(self, spec: dict) -> list:
        volume = f'{spec["data_dir"]}:/data'
        argv   = [self.binary(), 'run', '-d', '--rm', '--name', spec['name'], '-p', self.publish_flag(spec)]
        if self.name() == 'podman':
            argv.append('--userns=keep-id')
            if self.host.is_linux():
                volume += ':Z'
        if spec.get('user'):
            argv += ['--user', spec['user']]
        argv += ['-v', volume] + self.env_flags(spec) + [spec['image']]
        return argv
