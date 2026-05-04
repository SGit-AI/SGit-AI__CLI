from enum import Enum


class Enum__Workflow_Status(Enum):
    PENDING   = 'pending'
    RUNNING   = 'running'
    SUCCESS   = 'success'
    FAILED    = 'failed'
    ABORTED   = 'aborted'
