from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from app.config import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER


def connect():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
    )


@contextmanager
def cursor():
    conn = connect()
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()


@contextmanager
def transaction():
    conn = connect()
    conn.autocommit(False)
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
