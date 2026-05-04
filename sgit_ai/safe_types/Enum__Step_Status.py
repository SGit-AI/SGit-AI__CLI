from enum import Enum


class Enum__Step_Status(Enum):
    PENDING   = 'pending'
    RUNNING   = 'running'
    COMPLETED = 'completed'
    FAILED    = 'failed'
    SKIPPED   = 'skipped'
