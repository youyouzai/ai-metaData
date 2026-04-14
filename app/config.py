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

SESSION_SECRET = _getenv("SESSION_SECRET", "dev-change-me-in-production")

# 业务查询过程与 SQL 日志（mdm.business）。设为 0/false/no 可关闭
_v = (_getenv("MDM_BUSINESS_LOG", "1") or "1").strip().lower()
MDM_BUSINESS_LOG = _v not in ("0", "false", "no", "off")
