from typing import Any, Dict, List, Optional

import pymysql

from app import query_log as ql


def _attach_is_admin_fallback(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for r in rows:
        if "is_admin" not in r or r.get("is_admin") is None:
            r["is_admin"] = 1 if str(r.get("username") or "") == "admin" else 0
    return rows


def list_users(cur) -> List[Dict[str, Any]]:
    try:
        cur.execute(
            "SELECT id, username, display_name, is_admin FROM mdm_users ORDER BY id ASC"
        )
        return list(cur.fetchall())
    except pymysql.err.OperationalError as e:
        if e.args and e.args[0] == 1054:
            cur.execute(
                "SELECT id, username, display_name FROM mdm_users ORDER BY id ASC"
            )
            return _attach_is_admin_fallback(list(cur.fetchall()))
        raise


def list_object_types(cur) -> List[Dict[str, Any]]:
    ql.step("list_object_types.begin", note="业务对象类型列表（浏览卡片/API）")
    ql.sql_exec(
        cur,
        "SELECT id, code, name, description FROM business_object_types ORDER BY id ASC",
        None,
        step="list_object_types.query",
    )
    rows = list(cur.fetchall())
    for r in rows:
        c = r.get("code")
        r["code"] = str(c).strip().upper() if c is not None else ""
    ql.result_summary("list_object_types.result", rows=len(rows))
    ql.step("list_object_types.end", count=len(rows))
    return rows


def get_user_by_username(
    cur, username: str, *, log_sql: bool = False
) -> Optional[Dict[str, Any]]:
    def _run(sql: str, params: tuple) -> None:
        if log_sql:
            ql.sql_exec(cur, sql, params, step="get_user_by_username")
        else:
            cur.execute(sql, params)

    try:
        _run(
            "SELECT id, username, display_name, is_admin FROM mdm_users WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
    except pymysql.err.OperationalError as e:
        if not e.args or e.args[0] != 1054:
            raise
        _run(
            "SELECT id, username, display_name FROM mdm_users WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
    if not row:
        return None
    if "is_admin" not in row or row.get("is_admin") is None:
        row["is_admin"] = 1 if str(row.get("username") or "") == "admin" else 0
    return row


def can_read_object_row(
    cur,
    *,
    user_id: int,
    object_type_id: int,
    object_id: int,
    trace: str = "row_acl",
) -> bool:
    ql.sql_exec(
        cur,
        """
        SELECT EXISTS(
          SELECT 1
          FROM user_object_row_grants g
          JOIN business_objects bo2 ON bo2.id = g.object_id
          WHERE g.user_id = %s
            AND bo2.object_type_id = %s
        ) AS active
        """,
        (user_id, object_type_id),
        step=f"{trace}.whitelist_active_for_type",
    )
    row = cur.fetchone()
    active = bool(row and row.get("active"))
    ql.step(f"{trace}.whitelist_active_for_type.result", active=active)
    if not active:
        ql.step(f"{trace}.skip_row_grant_check", reason="no_whitelist_on_type")
        return True
    ql.sql_exec(
        cur,
        """
        SELECT 1
        FROM user_object_row_grants g
        WHERE g.user_id = %s
          AND g.object_id = %s
          AND g.can_read = 1
        LIMIT 1
        """,
        (user_id, object_id),
        step=f"{trace}.row_grant_exists",
    )
    ok = cur.fetchone() is not None
    ql.step(f"{trace}.row_grant_exists.result", allowed=ok)
    return ok


def list_object_keys_filtered(
    cur,
    *,
    username: str,
    object_type_code: str,
    user: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ql.step(
        "list_object_keys_filtered.begin",
        username=username,
        object_type_code=object_type_code,
        reused_user=user is not None,
    )
    if user is None:
        user = get_user_by_username(cur, username, log_sql=True)
    else:
        ql.step(
            "list_object_keys_filtered.reuse_user",
            user_id=int(user["id"]),
            note="与 web.browse 共用会话用户，跳过一次 SELECT",
        )
    if not user:
        ql.step("list_object_keys_filtered.end", error="user_not_found")
        return {"error": "user_not_found", "username": username}

    ql.step(
        "list_object_keys_filtered.resolve_user_ok",
        user_id=int(user["id"]),
        display_name=user.get("display_name"),
    )
    ql.sql_exec(
        cur,
        """
        SELECT bo.business_key
        FROM business_objects bo
        JOIN business_object_types t ON t.id = bo.object_type_id AND t.code = %s
        WHERE (
          NOT EXISTS (
            SELECT 1
            FROM user_object_row_grants g
            JOIN business_objects bo2 ON bo2.id = g.object_id
            WHERE g.user_id = %s
              AND bo2.object_type_id = t.id
          )
          OR EXISTS (
            SELECT 1
            FROM user_object_row_grants gx
            WHERE gx.user_id = %s
              AND gx.object_id = bo.id
              AND gx.can_read = 1
          )
        )
        ORDER BY bo.business_key ASC
        """,
        (object_type_code.strip().upper(), user["id"], user["id"]),
        step="list_object_keys_filtered.visible_business_keys",
    )
    keys = [r["business_key"] for r in cur.fetchall()]
    ql.result_summary("list_object_keys_filtered.keys", rows=len(keys), sample_keys=keys)
    ql.step("list_object_keys_filtered.end", count=len(keys))
    return {
        "user": {"username": user["username"], "display_name": user["display_name"]},
        "object_type_code": object_type_code.strip().upper(),
        "business_keys": keys,
    }


def list_object_keys_filtered_paged(
    cur,
    *,
    username: str,
    object_type_code: str,
    user: Optional[Dict[str, Any]] = None,
    page: int = 1,
    page_size: int = 10,
) -> Dict[str, Any]:
    """按行权限过滤后的业务主键分页列表（与 list_object_keys_filtered 同一过滤条件）。"""
    ql.step(
        "list_object_keys_filtered_paged.begin",
        username=username,
        object_type_code=object_type_code,
        page=page,
        page_size=page_size,
        reused_user=user is not None,
    )
    type_code_sql = (object_type_code or "").strip().upper()
    cur.execute(
        """
        SELECT id, code, name
        FROM business_object_types
        WHERE code = %s
        LIMIT 1
        """,
        (type_code_sql,),
    )
    type_row = cur.fetchone()
    if not type_row:
        ql.step("list_object_keys_filtered_paged.end", error="invalid_type")
        return {"error": "invalid_type", "object_type_code": object_type_code}

    if user is None:
        user = get_user_by_username(cur, username, log_sql=True)
    else:
        ql.step(
            "list_object_keys_filtered_paged.reuse_user",
            user_id=int(user["id"]),
        )
    if not user:
        ql.step("list_object_keys_filtered_paged.end", error="user_not_found")
        return {"error": "user_not_found", "username": username}

    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size
    params_row = (type_code_sql, user["id"], user["id"])

    ql.sql_exec(
        cur,
        """
        SELECT COUNT(*) AS c
        FROM business_objects bo
        JOIN business_object_types t ON t.id = bo.object_type_id AND t.code = %s
        WHERE (
          NOT EXISTS (
            SELECT 1
            FROM user_object_row_grants g
            JOIN business_objects bo2 ON bo2.id = g.object_id
            WHERE g.user_id = %s
              AND bo2.object_type_id = t.id
          )
          OR EXISTS (
            SELECT 1
            FROM user_object_row_grants gx
            WHERE gx.user_id = %s
              AND gx.object_id = bo.id
              AND gx.can_read = 1
          )
        )
        """,
        params_row,
        step="list_object_keys_filtered_paged.count",
    )
    total = int(cur.fetchone()["c"])
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1

    type_id = int(type_row["id"])
    uid = int(user["id"])
    ql.sql_exec(
        cur,
        """
        SELECT a.code, a.name
        FROM attributes a
        INNER JOIN user_attribute_grants g
          ON g.attribute_id = a.id AND g.user_id = %s AND g.can_read = 1
        WHERE a.object_type_id = %s
        ORDER BY a.sort_order ASC, a.id ASC
        """,
        (uid, type_id),
        step="list_object_keys_filtered_paged.list_columns",
    )
    col_rows = list(cur.fetchall())
    list_columns = [
        {"code": str(r["code"]), "name": str(r["name"])} for r in col_rows
    ]
    col_codes = [c["code"] for c in list_columns]

    ql.sql_exec(
        cur,
        """
        SELECT bo.id, bo.business_key
        FROM business_objects bo
        JOIN business_object_types t ON t.id = bo.object_type_id AND t.code = %s
        WHERE (
          NOT EXISTS (
            SELECT 1
            FROM user_object_row_grants g
            JOIN business_objects bo2 ON bo2.id = g.object_id
            WHERE g.user_id = %s
              AND bo2.object_type_id = t.id
          )
          OR EXISTS (
            SELECT 1
            FROM user_object_row_grants gx
            WHERE gx.user_id = %s
              AND gx.object_id = bo.id
              AND gx.can_read = 1
          )
        )
        ORDER BY bo.business_key ASC
        LIMIT %s OFFSET %s
        """,
        (*params_row, page_size, offset),
        step="list_object_keys_filtered_paged.page_query",
    )
    page_objs = list(cur.fetchall())
    keys = [r["business_key"] for r in page_objs]

    cell_by_key: Dict[str, Dict[str, str]] = {}
    if keys and col_codes:
        placeholders = ",".join(["%s"] * len(keys))
        ql.sql_exec(
            cur,
            f"""
            SELECT bo.business_key, a.code, av.value_text
            FROM business_objects bo
            JOIN attribute_values av ON av.object_id = bo.id
            JOIN attributes a ON a.id = av.attribute_id
            JOIN user_attribute_grants g
              ON g.attribute_id = a.id AND g.user_id = %s AND g.can_read = 1
            WHERE bo.object_type_id = %s AND bo.business_key IN ({placeholders})
            """,
            (uid, type_id, *keys),
            step="list_object_keys_filtered_paged.page_attribute_values",
        )
        for r in cur.fetchall():
            bk = str(r["business_key"])
            code = str(r["code"])
            if bk not in cell_by_key:
                cell_by_key[bk] = {}
            v = r.get("value_text")
            cell_by_key[bk][code] = "" if v is None else str(v)

    rows_out: List[Dict[str, Any]] = []
    for r in page_objs:
        bk = str(r["business_key"])
        m = cell_by_key.get(bk, {})
        rows_out.append(
            {
                "business_key": bk,
                "cells": [m.get(c) or "" for c in col_codes],
            }
        )

    ql.step(
        "list_object_keys_filtered_paged.end",
        total=total,
        page=page,
        returned=len(rows_out),
        columns=len(list_columns),
    )
    return {
        "ok": True,
        "user": {"username": user["username"], "display_name": user["display_name"]},
        "type": {
            "id": type_id,
            "code": str(type_row["code"] or "").strip().upper(),
            "name": type_row["name"],
        },
        "object_type_code": type_code_sql,
        "list_columns": list_columns,
        "rows": rows_out,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def get_object_filtered(
    cur, *, username: str, object_type_code: str, business_key: str
) -> Dict[str, Any]:
    ql.step(
        "get_object_filtered.begin",
        username=username,
        object_type_code=object_type_code,
        business_key=business_key,
    )
    user = get_user_by_username(cur, username, log_sql=True)
    if not user:
        ql.step("get_object_filtered.end", error="user_not_found")
        return {"error": "user_not_found", "username": username}

    ql.step("get_object_filtered.resolve_user_ok", user_id=int(user["id"]))
    ql.sql_exec(
        cur,
        """
        SELECT bo.id AS object_id, bo.object_type_id, bo.business_key
        FROM business_objects bo
        JOIN business_object_types t ON t.id = bo.object_type_id AND t.code = %s
        WHERE bo.business_key = %s
        LIMIT 1
        """,
        (object_type_code, business_key),
        step="get_object_filtered.resolve_business_object",
    )
    obj = cur.fetchone()
    if not obj:
        ql.step("get_object_filtered.end", error="object_not_found")
        return {"error": "object_not_found", "business_key": business_key}

    ql.step(
        "get_object_filtered.row_acl_check",
        object_id=int(obj["object_id"]),
        object_type_id=int(obj["object_type_id"]),
    )
    if not can_read_object_row(
        cur,
        user_id=int(user["id"]),
        object_type_id=int(obj["object_type_id"]),
        object_id=int(obj["object_id"]),
        trace="get_object_filtered.row_acl",
    ):
        ql.step("get_object_filtered.end", error="row_access_denied")
        return {
            "error": "row_access_denied",
            "message": "当前用户对该业务对象无行级访问权限",
            "business_key": business_key,
        }

    ql.step("get_object_filtered.column_acl_query", note="JOIN user_attribute_grants")
    ql.sql_exec(
        cur,
        """
        SELECT
          t.code AS object_type_code,
          t.name AS object_type_name,
          bo.business_key,
          a.code AS attribute_code,
          a.name AS attribute_name,
          a.data_type,
          av.value_text
        FROM business_objects bo
        JOIN business_object_types t ON t.id = bo.object_type_id AND t.code = %s
        JOIN attribute_values av ON av.object_id = bo.id
        JOIN attributes a ON a.id = av.attribute_id
        JOIN user_attribute_grants g
          ON g.attribute_id = a.id
         AND g.user_id = %s
         AND g.can_read = 1
        WHERE bo.business_key = %s
        ORDER BY a.sort_order ASC, a.id ASC
        """,
        (object_type_code, user["id"], business_key),
        step="get_object_filtered.visible_attribute_values",
    )
    rows: List[Dict[str, Any]] = list(cur.fetchall())
    if not rows:
        ql.step("get_object_filtered.end", error="no_visible_attributes", attribute_rows=0)
        return {
            "error": "no_visible_attributes",
            "message": "对象存在但当前用户对该类型无任何可读属性授权",
            "user": {"username": user["username"], "display_name": user["display_name"]},
            "object_type_code": object_type_code,
            "business_key": business_key,
            "attributes": {},
        }

    attrs: Dict[str, Any] = {}
    for r in rows:
        attrs[r["attribute_code"]] = {
            "label": r["attribute_name"],
            "data_type": r["data_type"],
            "value": r["value_text"],
        }

    sample = rows[0]
    ql.result_summary(
        "get_object_filtered.attributes",
        rows=len(rows),
        sample_keys=list(attrs.keys()),
    )
    ql.step("get_object_filtered.end", ok=True, attribute_count=len(attrs))
    return {
        "user": {"username": user["username"], "display_name": user["display_name"]},
        "object_type": {
            "code": sample["object_type_code"],
            "name": sample["object_type_name"],
        },
        "business_key": sample["business_key"],
        "attributes": attrs,
    }


def list_grants_for_user(
    cur, username: str, *, user: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    ql.step(
        "list_grants_for_user.begin",
        username=username,
        reused_user=user is not None,
    )
    if user is None:
        user = get_user_by_username(cur, username, log_sql=True)
    else:
        ql.step(
            "list_grants_for_user.reuse_user",
            user_id=int(user["id"]),
            note="与 web.browse 共用会话用户，跳过一次 SELECT",
        )
    if not user:
        ql.step("list_grants_for_user.end", error="user_not_found")
        return {"error": "user_not_found", "username": username}

    ql.step("list_grants_for_user.resolve_user_ok", user_id=int(user["id"]))
    ql.sql_exec(
        cur,
        """
        SELECT
          t.code AS object_type_code,
          a.code AS attribute_code,
          a.name AS attribute_name,
          g.can_read
        FROM user_attribute_grants g
        JOIN attributes a ON a.id = g.attribute_id
        JOIN business_object_types t ON t.id = a.object_type_id
        WHERE g.user_id = %s
        ORDER BY t.code ASC, a.sort_order ASC, a.id ASC
        """,
        (user["id"],),
        step="list_grants_for_user.column_grants",
    )
    rows = list(cur.fetchall())
    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_type.setdefault(r["object_type_code"], []).append(
            {
                "code": r["attribute_code"],
                "name": r["attribute_name"],
                "can_read": bool(r["can_read"]),
            }
        )

    ql.sql_exec(
        cur,
        """
        SELECT t.code AS object_type_code, bo.business_key
        FROM user_object_row_grants g
        JOIN business_objects bo ON bo.id = g.object_id
        JOIN business_object_types t ON t.id = bo.object_type_id
        WHERE g.user_id = %s
          AND g.can_read = 1
        ORDER BY t.code ASC, bo.business_key ASC
        """,
        (user["id"],),
        step="list_grants_for_user.row_grants",
    )
    row_entries = list(cur.fetchall())
    row_by_type: Dict[str, List[str]] = {}
    for r in row_entries:
        row_by_type.setdefault(r["object_type_code"], []).append(r["business_key"])

    ql.sql_exec(
        cur,
        """
        SELECT EXISTS(
          SELECT 1
          FROM user_object_row_grants g
          JOIN business_objects bo ON bo.id = g.object_id
          JOIN business_object_types t ON t.id = bo.object_type_id
          WHERE g.user_id = %s
        ) AS any_row_grant
        """,
        (user["id"],),
        step="list_grants_for_user.row_acl_flag",
    )
    flag = cur.fetchone() or {}
    any_row = bool(flag.get("any_row_grant"))
    ql.step(
        "list_grants_for_user.end",
        ok=True,
        column_grant_rows=len(rows),
        row_grant_rows=len(row_entries),
        has_row_whitelist_entries=any_row,
    )

    return {
        "user": {"username": user["username"], "display_name": user["display_name"]},
        "readable_attributes_by_type": by_type,
        "row_acl": {
            "has_row_whitelist_entries": any_row,
            "whitelist_by_type": row_by_type,
            "note": "若用户在某对象类型下配置了任意行授权，则该类型仅可访问列出的主键行；未配置行授权的类型不限制行",
        },
    }
