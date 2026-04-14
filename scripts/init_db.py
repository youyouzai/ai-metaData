"""
初始化 MySQL 数据库并导入 demo 数据（执行 sql/000、001、002）。

连接参数与 app.config 一致，可用环境变量覆盖：
  MYSQL_HOST MYSQL_PORT MYSQL_USER MYSQL_PASSWORD MYSQL_DATABASE
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pymysql
from pymysql.constants import CLIENT

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _cfg(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v not in (None, "") else default


def _connect(*, database: str | None):
    host = _cfg("MYSQL_HOST", "127.0.0.1")
    port = int(_cfg("MYSQL_PORT", "3306"))
    user = _cfg("MYSQL_USER", "root")
    password = _cfg("MYSQL_PASSWORD", "root")
    kw: dict = dict(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=True,
        client_flag=CLIENT.MULTI_STATEMENTS,
    )
    if database is not None:
        kw["database"] = database
    return pymysql.connect(**kw)


def _run_sql_file(conn, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    cur = conn.cursor()
    cur.execute(sql)
    while cur.nextset():
        pass


def main() -> int:
    db_name = _cfg("MYSQL_DATABASE", "ai_metadata")

    p0 = SQL_DIR / "000_create_database.sql"
    p1 = SQL_DIR / "001_schema.sql"
    p2 = SQL_DIR / "002_seed.sql"
    for p in (p0, p1, p2):
        if not p.is_file():
            print(f"缺少脚本: {p}", file=sys.stderr)
            return 1

    print(f"连接 {_cfg('MYSQL_HOST', '127.0.0.1')}:{_cfg('MYSQL_PORT', '3306')} 用户 {_cfg('MYSQL_USER', 'root')}")
    print(f"执行 {p0.name} …")
    c0 = _connect(database=None)
    try:
        txt = p0.read_text(encoding="utf-8")
        if db_name != "ai_metadata" and "ai_metadata" in txt:
            txt = txt.replace("ai_metadata", db_name)
        cur = c0.cursor()
        cur.execute(txt)
        while cur.nextset():
            pass
    finally:
        c0.close()

    print(f"执行 {p1.name}、{p2.name}（库 {db_name}）…")
    c1 = _connect(database=db_name)
    try:
        _run_sql_file(c1, p1)
        _run_sql_file(c1, p2)
    finally:
        c1.close()

    print("完成：已建库、建表并写入 demo 数据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
