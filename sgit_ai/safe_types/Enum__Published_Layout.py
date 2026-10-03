from enum import Enum


class Enum__Published_Layout(Enum):
    """Where a published host serves an object relative to its root.

    API_PATH mirrors the live API (api/vault/read/{vault_id}/{file_id}) so the
    same URL works against SG/API and a static host; FLAT is a plain directory
    server or bare folder ({file_id} at the root). The static transport sniffs
    both on the first read and sticks with whichever answers.
    """
    API_PATH = 'api-path'
    FLAT     = 'flat'
