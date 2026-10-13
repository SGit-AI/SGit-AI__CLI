from osbot_utils.type_safe.Type_Safe                           import Type_Safe
from osbot_utils.type_safe.primitives.core.Safe_UInt           import Safe_UInt
from sgit_ai.safe_types.Safe_Str__Bind_Address                 import Safe_Str__Bind_Address
from sgit_ai.safe_types.Safe_Str__Container_Name               import Safe_Str__Container_Name
from sgit_ai.safe_types.Safe_Str__Container_Runtime            import Safe_Str__Container_Runtime
from sgit_ai.safe_types.Safe_Str__Host_Path                    import Safe_Str__Host_Path
from sgit_ai.safe_types.Safe_Str__Image_Ref                    import Safe_Str__Image_Ref
from sgit_ai.safe_types.Safe_UInt__Port                        import Safe_UInt__Port


class Schema__Serve__State(Type_Safe):
    """What `sgit serve` started, kept beside its data folder so stop, status, logs and
    update find it again (`<clone>/.sg_vault/serve/serve.json`)."""
    runtime        : Safe_Str__Container_Runtime = None   # docker, podman, container, nerdctl, finch, uv
    container_name : Safe_Str__Container_Name    = None
    image          : Safe_Str__Image_Ref         = None   # what was asked for (…:latest)
    image_digest   : Safe_Str__Image_Ref         = None   # what actually ran (repo@sha256:…)
    bind           : Safe_Str__Bind_Address      = None
    host_port      : Safe_UInt__Port
    data_dir       : Safe_Str__Host_Path         = None
    pid            : Safe_UInt                             # the uv engine's process (0 for containers)
    started_at     : Safe_UInt                             # ms since epoch
