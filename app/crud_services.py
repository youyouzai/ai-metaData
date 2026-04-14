"""管理员侧：业务对象实例 CRUD + 分页（不经过行列权限过滤）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pymysql


def resolve_type(cur, code: str) -> Optional[Dict[str, Any]]:
    cur.execute(
        """
        SELECT id, code, name, description
        FROM business_object_types
        WHERE code = %s
        LIMIT 1
        """,
        (code.strip().upper(),),
    )
    return cur.fetchone()


def list_types_minimal(cur) -> List[Dict[str, Any]]:
    cur.execute(
        "SELECT code, name FROM business_object_types ORDER BY code ASC"
    )
    rows = list(cur.fetchall())
    for r in rows:
        c = r.get("code")
        r["code"] = str(c).strip().upper() if c is not None else ""
    return rows


def list_attributes_for_type(cur, object_type_id: int) -> List[Dict[str, Any]]:
    cur.execute(
        """
        SELECT id, code, name, data_type, sort_order
        FROM attributes
        WHERE object_type_id = %s
        ORDER BY sort_order ASC, id ASC
        """,
        (object_type_id,),
    )
    return list(cur.fetchall())


def list_business_objects_paged(
    cur,
    *,
    type_code: str,
    page: int = 1,
    page_size: int = 10,
) -> Dict[str, Any]:
    t = resolve_type(cur, type_code)
    if not t:
        return {
            "ok": False,
            "error": "invalid_type",
            "rows": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "type": None,
        }
    tid = int(t["id"])
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    offset = (page - 1) * page_size

    cur.execute(
        "SELECT COUNT(*) AS c FROM business_objects WHERE object_type_id = %s",
        (tid,),
    )
    total = int(cur.fetchone()["c"])

    cur.execute(
        """
        SELECT id, business_key
        FROM business_objects
        WHERE object_type_id = %s
        ORDER BY id DESC
        LIMIT %s OFFSET %s
        """,
        (tid, page_size, offset),
    )
    items = list(cur.fetchall())
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1

    return {
        "ok": True,
        "type": t,
        "rows": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def get_new_form_payload(cur, type_code: str) -> Optional[Dict[str, Any]]:
    t = resolve_type(cur, type_code)
    if not t:
        return None
    tid = int(t["id"])
    attrs = list_attributes_for_type(cur, tid)
    fields: List[Dict[str, Any]] = []
    for a in attrs:
        d = dict(a)
        d["value_text"] = ""
        fields.append(d)
    return {"type": t, "fields": fields}


def get_object_for_edit(
    cur, *, type_code: str, business_key: str
) -> Optional[Dict[str, Any]]:
    t = resolve_type(cur, type_code)
    if not t:
        return None
    tid = int(t["id"])
    cur.execute(
        """
        SELECT bo.id, bo.business_key
        FROM business_objects bo
        WHERE bo.object_type_id = %s AND bo.business_key = %s
        LIMIT 1
        """,
        (tid, business_key.strip()),
    )
    bo = cur.fetchone()
    if not bo:
        return None
    oid = int(bo["id"])
    cur.execute(
        """
        SELECT a.id, a.code, a.name, a.data_type, a.sort_order, av.value_text
        FROM attributes a
        LEFT JOIN attribute_values av
          ON av.attribute_id = a.id AND av.object_id = %s
        WHERE a.object_type_id = %s
        ORDER BY a.sort_order ASC, a.id ASC
        """,
        (oid, tid),
    )
    fields = list(cur.fetchall())
    return {"type": t, "object": bo, "fields": fields}


def valid_attr_ids_for_type(cur, object_type_id: int) -> Dict[int, None]:
    cur.execute("SELECT id FROM attributes WHERE object_type_id = %s", (object_type_id,))
    return {int(r["id"]): None for r in cur.fetchall()}


def create_business_object(
    cur,
    *,
    type_code: str,
    business_key: str,
    values_by_attr_id: Dict[int, str],
) -> Dict[str, Any]:
    t = resolve_type(cur, type_code)
    if not t:
        return {"ok": False, "error": "invalid_type"}
    tid = int(t["id"])
    bid = business_key.strip()
    if not bid:
        return {"ok": False, "error": "empty_key"}
    valid = valid_attr_ids_for_type(cur, tid)
    try:
        cur.execute(
            """
            INSERT INTO business_objects (object_type_id, business_key)
            VALUES (%s, %s)
            """,
            (tid, bid),
        )
        oid = int(cur.lastrowid)
        for aid in valid:
            val = values_by_attr_id.get(aid, "")
            if val is None:
                val = ""
            cur.execute(
                """
                INSERT INTO attribute_values (object_id, attribute_id, value_text)
                VALUES (%s, %s, %s)
                """,
                (oid, aid, str(val)),
            )
    except pymysql.err.IntegrityError:
        return {"ok": False, "error": "duplicate_key"}
    return {"ok": True, "object_id": oid, "business_key": bid}


def update_business_object(
    cur,
    *,
    type_code: str,
    old_business_key: str,
    new_business_key: str,
    values_by_attr_id: Dict[int, str],
) -> Dict[str, Any]:
    t = resolve_type(cur, type_code)
    if not t:
        return {"ok": False, "error": "invalid_type"}
    tid = int(t["id"])
    old_k = old_business_key.strip()
    new_k = new_business_key.strip()
    if not new_k:
        return {"ok": False, "error": "empty_key"}

    cur.execute(
        """
        SELECT id FROM business_objects
        WHERE object_type_id = %s AND business_key = %s
        LIMIT 1
        """,
        (tid, old_k),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "not_found"}
    oid = int(row["id"])
    valid = valid_attr_ids_for_type(cur, tid)

    try:
        cur.execute(
            """
            UPDATE business_objects
            SET business_key = %s
            WHERE id = %s
            """,
            (new_k, oid),
        )
        for aid in valid:
            val = values_by_attr_id.get(aid, "")
            if val is None:
                val = ""
            cur.execute(
                """
                REPLACE INTO attribute_values (object_id, attribute_id, value_text)
                VALUES (%s, %s, %s)
                """,
                (oid, aid, str(val)),
            )
    except pymysql.err.IntegrityError:
        return {"ok": False, "error": "duplicate_key"}
    return {"ok": True, "object_id": oid, "business_key": new_k}


def delete_business_object(
    cur, *, type_code: str, business_key: str
) -> Dict[str, Any]:
    t = resolve_type(cur, type_code)
    if not t:
        return {"ok": False, "error": "invalid_type"}
    tid = int(t["id"])
    cur.execute(
        """
        DELETE bo FROM business_objects bo
        WHERE bo.object_type_id = %s AND bo.business_key = %s
        """,
        (tid, business_key.strip()),
    )
    if cur.rowcount == 0:
        return {"ok": False, "error": "not_found"}
    return {"ok": True}


def parse_attr_values_from_form(form: Any, *, valid_ids: Dict[int, None]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for k in form.keys():
        if not isinstance(k, str) or not k.startswith("aval_"):
            continue
        try:
            aid = int(k.replace("aval_", "", 1))
        except ValueError:
            continue
        if aid not in valid_ids:
            continue
        raw = form.get(k)
        out[aid] = "" if raw is None else str(raw)
    return out
