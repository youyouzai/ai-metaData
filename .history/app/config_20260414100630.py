import os
from typing import Optional


def _getenv(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    if v is not None and v != "":
        return v
    return default


MYSQL_HOST = _getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(_getenv("MYSQL_PORT", "3306"))
MYSQL_USER = _getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = _getenv("MYSQL_PASSWORD", "root")
MYSQL_DATABASE = _getenv("MYSQL_DATABASE", "ai_metadata")
