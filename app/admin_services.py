from typing import Any, Dict, List, Optional, Set


def list_users_for_admin(cur) -> List[Dict[str, Any]]:
    from app import services

    rows = services.list_users(cur)
    rows.sort(key=lambda r: (not int(r.get("is_admin") or 0), int(r["id"])))
    return rows


def list_all_attributes_grouped(cur) -> List[Dict[str, Any]]:
    cur.execute(
        """
        SELECT
          t.code AS object_type_code,
          t.name AS object_type_name,
          a.id AS attribute_id,
          a.code AS attribute_code,
          a.name AS attribute_name
        FROM attributes a
        JOIN business_object_types t ON t.id = a.object_type_id
        ORDER BY t.code ASC, a.sort_order ASC, a.id ASC
        """
    )
    rows = list(cur.fetchall())
    grouped: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    for r in rows:
        key = r["object_type_code"]
        if current is None or current["code"] != key:
            current = {
                "code": key,
                "name": r["object_type_name"],
                "attributes": [],
            }
            grouped.append(current)
        current["attributes"].append(
            {
                "id": r["attribute_id"],
                "code": r["attribute_code"],
                "name": r["attribute_name"],
            }
        )
    return grouped


def list_all_business_objects_grouped(cur) -> List[Dict[str, Any]]:
    cur.execute(
        """
        SELECT
          t.code AS object_type_code,
          t.name AS object_type_name,
          bo.id AS object_id,
          bo.business_key
        FROM business_objects bo
        JOIN business_object_types t ON t.id = bo.object_type_id
        ORDER BY t.code ASC, bo.business_key ASC
        """
    )
    rows = list(cur.fetchall())
    grouped: List[Dict[str, Any]] = []
    current_bo: Optional[Dict[str, Any]] = None
    for r in rows:
        key = r["object_type_code"]
        if current_bo is None or current_bo["code"] != key:
            current_bo = {
                "code": key,
                "name": r["object_type_name"],
                "objects": [],
            }
            grouped.append(current_bo)
        current_bo["objects"].append(
            {"id": r["object_id"], "business_key": r["business_key"]}
        )
    return grouped


def column_grant_set_for_user(cur, user_id: int) -> Set[int]:
    cur.execute(
        "SELECT attribute_id FROM user_attribute_grants WHERE user_id = %s AND can_read = 1",
        (user_id,),
    )
    return {int(r["attribute_id"]) for r in cur.fetchall()}


def row_grant_set_for_user(cur, user_id: int) -> Set[int]:
    cur.execute(
        "SELECT object_id FROM user_object_row_grants WHERE user_id = %s AND can_read = 1",
        (user_id,),
    )
    return {int(r["object_id"]) for r in cur.fetchall()}


def sync_column_grants(cur, *, target_user_id: int, granted_attribute_ids: Set[int]) -> None:
    cur.execute(
        "SELECT id FROM attributes",
    )
    all_ids = {int(r["id"]) for r in cur.fetchall()}
    granted = {i for i in granted_attribute_ids if i in all_ids}

    cur.execute(
        "DELETE FROM user_attribute_grants WHERE user_id = %s",
        (target_user_id,),
    )
    if not granted:
        return
    rows = [(target_user_id, aid, 1) for aid in sorted(granted)]
    cur.executemany(
        "INSERT INTO user_attribute_grants (user_id, attribute_id, can_read) VALUES (%s, %s, %s)",
        rows,
    )


def sync_row_grants(cur, *, target_user_id: int, granted_object_ids: Set[int]) -> None:
    cur.execute("SELECT id FROM business_objects")
    all_ids = {int(r["id"]) for r in cur.fetchall()}
    granted = {i for i in granted_object_ids if i in all_ids}

    cur.execute(
        "DELETE FROM user_object_row_grants WHERE user_id = %s",
        (target_user_id,),
    )
    if not granted:
        return
    rows = [(target_user_id, oid, 1) for oid in sorted(granted)]
    cur.executemany(
        "INSERT INTO user_object_row_grants (user_id, object_id, can_read) VALUES (%s, %s, %s)",
        rows,
    )
