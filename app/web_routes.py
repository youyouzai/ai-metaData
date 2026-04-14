from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote as urlquote

import pymysql
from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import admin_services, crud_services, query_log as ql, services
from app.db import cursor, transaction

router = APIRouter()
_TPL = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TPL))
templates.env.filters["uriquote"] = lambda s: urlquote(str(s), safe="-_.~")


def _mysql_error_hint(exc: pymysql.MySQLError) -> str:
    code = int(exc.args[0]) if exc.args else 0
    msg = str(exc.args[1]) if len(exc.args) > 1 else str(exc)
    if code == 1049:
        return " 请先创建数据库（例如执行 sql/000_create_database.sql），或检查环境变量 MYSQL_DATABASE。"
    if code == 1045:
        return " 请检查 MYSQL_USER、MYSQL_PASSWORD 是否有权限连接实例。"
    if code in (2003, 2002):
        return " 请确认 MySQL 已启动，并检查 MYSQL_HOST、MYSQL_PORT。"
    if code == 1146:
        return " 请先执行 sql/001_schema.sql / 002_seed.sql（或 sql/003_migrate_add_row_acl.sql）建表。"
    if code == 1054:
        return " 表结构过旧：请执行迁移脚本或重建库。"
    return ""


def _load_users_safe() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    try:
        with cursor() as cur:
            return services.list_users(cur), None
    except pymysql.MySQLError as e:
        return [], f"无法连接数据库（{e.args[0]}）：{e.args[1]}{_mysql_error_hint(e)}"


def _session_username(request: Request) -> Optional[str]:
    raw = request.session.get("username")
    if raw is None:
        return None
    return str(raw)


def _bo_admin_response(request: Request):
    """返回 (user_dict, None) 或 (None, HTTP 响应)。"""
    username = _session_username(request)
    if not username:
        return None, RedirectResponse(url="/web/login", status_code=302)
    with cursor() as cur:
        me = services.get_user_by_username(cur, username)
    if not me or not int(me.get("is_admin") or 0):
        return None, templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "title": "无权限",
                "message": "仅管理员可进行业务对象主数据维护",
                "user": me,
            },
            status_code=403,
        )
    return me, None


@router.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse(url="/web/browse", status_code=302)


@router.get("/web/login", response_class=HTMLResponse)
def login_page(request: Request):
    users, db_error = _load_users_safe()
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "users": users, "error": db_error},
    )


@router.post("/web/login", response_class=HTMLResponse)
async def login_submit(request: Request, username: str = Form(...)):
    try:
        with cursor() as cur:
            user = services.get_user_by_username(cur, username.strip())
    except pymysql.MySQLError as e:
        users, db_error = _load_users_safe()
        msg = db_error or f"数据库不可用（{e.args[0]}）：{e.args[1]}{_mysql_error_hint(e)}"
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "users": users, "error": msg},
            status_code=503,
        )
    if not user:
        users, db_error = _load_users_safe()
        err = db_error or "用户不存在"
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "users": users, "error": err},
            status_code=503 if db_error else 400,
        )
    request.session["username"] = user["username"]
    return RedirectResponse(url="/web/browse", status_code=302)


@router.get("/web/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/web/login", status_code=302)


@router.get("/web/browse", response_class=HTMLResponse)
def browse(
    request: Request,
    object_type: Optional[str] = Query(None, alias="type"),
):
    username = _session_username(request)
    if not username:
        return RedirectResponse(url="/web/login", status_code=302)

    sel = object_type.strip().upper() if object_type and object_type.strip() else None
    with cursor() as cur:
        ql.step(
            "web.browse.begin",
            username=username,
            selected_type=sel,
            note="数据列表页：类型卡片 + 可选主键列表 + 权限摘要",
        )
        user = services.get_user_by_username(cur, username, log_sql=True)
        if not user:
            ql.step("web.browse.abort", reason="user_not_found")
            return RedirectResponse(url="/web/login", status_code=302)

        ql.step("web.browse.load_object_types", phase="业务类型列表")
        types = services.list_object_types(cur)

        keys_data: Optional[Dict[str, Any]] = None
        if object_type and object_type.strip():
            ql.step(
                "web.browse.load_visible_keys",
                object_type_code=object_type.strip().upper(),
                phase="行+列权限过滤后的主键列表",
            )
            keys_data = services.list_object_keys_filtered(
                cur,
                username=username,
                object_type_code=object_type.strip().upper(),
                user=user,
            )

        ql.step("web.browse.load_permissions_snapshot", phase="列权限+行白名单摘要")
        perm = services.list_grants_for_user(cur, username, user=user)

        ql.step(
            "web.browse.end",
            types=len(types),
            selected_type=sel,
            keys_count=len(keys_data["business_keys"])
            if keys_data and isinstance(keys_data.get("business_keys"), list)
            else 0,
        )

    return templates.TemplateResponse(
        "browse.html",
        {
            "request": request,
            "user": user,
            "object_types": types,
            "selected_type": sel,
            "keys_data": keys_data,
            "perm": perm,
        },
    )


@router.get("/web/objects-page", response_class=HTMLResponse)
def objects_page(
    request: Request,
    object_type: Optional[str] = Query(None, alias="type"),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
):
    """当前用户可见业务主键的分页列表（行权限过滤）。"""
    username = _session_username(request)
    if not username:
        return RedirectResponse(url="/web/login", status_code=302)
    with cursor() as cur:
        user = services.get_user_by_username(cur, username, log_sql=True)
        if not user:
            return RedirectResponse(url="/web/login", status_code=302)
        types = services.list_object_types(cur)
        if not types:
            return templates.TemplateResponse(
                "objects_page.html",
                {
                    "request": request,
                    "user": user,
                    "types": [],
                    "type_code": None,
                    "data": None,
                    "paged_rows": [],
                    "msg": "暂无业务对象类型",
                },
            )
        codes = {str(t["code"]).strip().upper() for t in types}
        tc = (
            object_type.strip().upper()
            if object_type and object_type.strip()
            else str(types[0]["code"]).strip().upper()
        )
        if tc not in codes:
            tc = str(types[0]["code"]).strip().upper()
        data = services.list_object_keys_filtered_paged(
            cur,
            username=username,
            object_type_code=tc,
            user=user,
            page=page,
            page_size=size,
        )
    if data.get("error") == "user_not_found":
        return RedirectResponse(url="/web/login", status_code=302)
    paged_rows = list(data.get("rows") or [])
    return templates.TemplateResponse(
        "objects_page.html",
        {
            "request": request,
            "user": user,
            "types": types,
            "type_code": tc,
            "data": data,
            "paged_rows": paged_rows,
            "msg": None,
        },
    )


@router.get("/web/logs", response_class=HTMLResponse)
def logs_page(request: Request):
    username = _session_username(request)
    if not username:
        return RedirectResponse(url="/web/login", status_code=302)
    with cursor() as cur:
        user = services.get_user_by_username(cur, username)
    return templates.TemplateResponse(
        "logs.html",
        {"request": request, "user": user},
    )


@router.get("/web/objects/{object_type_code}/{business_key}", response_class=HTMLResponse)
def object_detail(request: Request, object_type_code: str, business_key: str):
    username = _session_username(request)
    if not username:
        return RedirectResponse(url="/web/login", status_code=302)

    with cursor() as cur:
        user = services.get_user_by_username(cur, username)
        data = services.get_object_filtered(
            cur,
            username=username,
            object_type_code=object_type_code.upper(),
            business_key=business_key,
        )

    err = data.get("error")
    if err == "row_access_denied":
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "title": "无行级权限",
                "message": data.get("message") or "不可访问该业务主键",
                "user": user,
            },
            status_code=403,
        )
    if err == "no_visible_attributes":
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "title": "无列级权限",
                "message": data.get("message") or "不可查看任何字段",
                "user": user,
            },
            status_code=403,
        )
    if err == "object_not_found":
        raise HTTPException(status_code=404, detail="对象不存在")

    return templates.TemplateResponse(
        "object_detail.html",
        {"request": request, "user": user, "data": data},
    )


@router.get("/web/admin", response_class=HTMLResponse)
def admin_page(request: Request, target: Optional[str] = None):
    username = _session_username(request)
    if not username:
        return RedirectResponse(url="/web/login", status_code=302)
    with cursor() as cur:
        me = services.get_user_by_username(cur, username)
    if not me or not int(me.get("is_admin") or 0):
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "title": "无权限",
                "message": "仅管理员可访问权限管理页，请使用 admin 登录",
                "user": me,
            },
            status_code=403,
        )
    with cursor() as cur:
        users = admin_services.list_users_for_admin(cur)
        attrs = admin_services.list_all_attributes_grouped(cur)
        bos = admin_services.list_all_business_objects_grouped(cur)

    target_username = target
    if not target_username and users:
        for u in users:
            if not int(u.get("is_admin") or 0):
                target_username = str(u["username"])
                break
        if not target_username:
            target_username = str(users[0]["username"])

    col_sel: Set[int] = set()
    row_sel: Set[int] = set()
    target_user: Optional[Dict[str, Any]] = None
    if target_username:
        with cursor() as cur:
            target_user = services.get_user_by_username(cur, target_username)
            if target_user:
                col_sel = admin_services.column_grant_set_for_user(
                    cur, int(target_user["id"])
                )
                row_sel = admin_services.row_grant_set_for_user(
                    cur, int(target_user["id"])
                )

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "users": users,
            "attrs_grouped": attrs,
            "objects_grouped": bos,
            "target_username": target_username,
            "target_user": target_user,
            "col_sel": col_sel,
            "row_sel": row_sel,
            "msg": request.session.pop("admin_msg", None),
        },
    )


@router.post("/web/admin/columns")
async def admin_save_columns(request: Request):
    username = _session_username(request)
    if not username:
        return RedirectResponse(url="/web/login", status_code=302)
    with cursor() as cur:
        me = services.get_user_by_username(cur, username)
    if not me or not int(me.get("is_admin") or 0):
        raise HTTPException(status_code=403, detail="需要管理员账号")
    form = await request.form()
    target_username = str(form.get("target_username") or "").strip()
    if not target_username:
        request.session["admin_msg"] = "请选择目标用户"
        return RedirectResponse(url="/web/admin", status_code=302)

    granted: Set[int] = set()
    for k in form.keys():
        if not isinstance(k, str) or not k.startswith("attr_"):
            continue
        try:
            granted.add(int(k.replace("attr_", "", 1)))
        except ValueError:
            continue

    with cursor() as cur:
        target = services.get_user_by_username(cur, target_username)
        if not target:
            request.session["admin_msg"] = "目标用户不存在"
            return RedirectResponse(url="/web/admin", status_code=302)

    with transaction() as cur:
        admin_services.sync_column_grants(
            cur, target_user_id=int(target["id"]), granted_attribute_ids=granted
        )

    request.session["admin_msg"] = "列权限已保存"
    return RedirectResponse(url=f"/web/admin?target={target_username}", status_code=302)


@router.post("/web/admin/rows")
async def admin_save_rows(request: Request):
    username = _session_username(request)
    if not username:
        return RedirectResponse(url="/web/login", status_code=302)
    with cursor() as cur:
        me = services.get_user_by_username(cur, username)
    if not me or not int(me.get("is_admin") or 0):
        raise HTTPException(status_code=403, detail="需要管理员账号")
    form = await request.form()
    target_username = str(form.get("target_username") or "").strip()
    if not target_username:
        request.session["admin_msg"] = "请选择目标用户"
        return RedirectResponse(url="/web/admin", status_code=302)

    granted: Set[int] = set()
    for k in form.keys():
        if not isinstance(k, str) or not k.startswith("row_"):
            continue
        try:
            granted.add(int(k.replace("row_", "", 1)))
        except ValueError:
            continue

    with cursor() as cur:
        target = services.get_user_by_username(cur, target_username)
        if not target:
            request.session["admin_msg"] = "目标用户不存在"
            return RedirectResponse(url="/web/admin", status_code=302)

    with transaction() as cur:
        admin_services.sync_row_grants(
            cur, target_user_id=int(target["id"]), granted_object_ids=granted
        )

    request.session["admin_msg"] = "行权限已保存（某类型下若为空则不对该类型限制行）"
    return RedirectResponse(url=f"/web/admin?target={target_username}", status_code=302)


# --- 业务对象主数据 CRUD（管理员） ---


@router.get("/web/bo", response_class=HTMLResponse)
def bo_list(
    request: Request,
    object_type: Optional[str] = Query(None, alias="type"),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
):
    me, resp = _bo_admin_response(request)
    if resp is not None:
        return resp
    with cursor() as cur:
        types = crud_services.list_types_minimal(cur)
        if not types:
            return templates.TemplateResponse(
                "bo_list.html",
                {
                    "request": request,
                    "user": me,
                    "types": [],
                    "type_code": None,
                    "data": None,
                    "bo_rows": [],
                    "msg": request.session.pop("bo_msg", None),
                },
            )
        codes = {str(t["code"]).strip().upper() for t in types}
        tc = (
            object_type.strip().upper()
            if object_type and object_type.strip()
            else str(types[0]["code"]).strip().upper()
        )
        if tc not in codes:
            tc = str(types[0]["code"]).strip().upper()
        data = crud_services.list_business_objects_paged(
            cur, type_code=tc, page=page, page_size=size
        )
    bo_rows = list(data.get("rows") or [])
    return templates.TemplateResponse(
        "bo_list.html",
        {
            "request": request,
            "user": me,
            "types": types,
            "type_code": tc,
            "data": data,
            "bo_rows": bo_rows,
            "msg": request.session.pop("bo_msg", None),
        },
    )


@router.get("/web/bo/new", response_class=HTMLResponse)
def bo_new_form(
    request: Request,
    object_type: Optional[str] = Query(None, alias="type"),
):
    me, resp = _bo_admin_response(request)
    if resp is not None:
        return resp
    with cursor() as cur:
        types = crud_services.list_types_minimal(cur)
        if not types:
            return RedirectResponse(url="/web/bo", status_code=302)
        codes = {str(t["code"]).strip().upper() for t in types}
        tc = (
            object_type.strip().upper()
            if object_type and object_type.strip()
            else str(types[0]["code"]).strip().upper()
        )
        if tc not in codes:
            tc = str(types[0]["code"]).strip().upper()
        payload = crud_services.get_new_form_payload(cur, tc)
    if not payload:
        request.session["bo_msg"] = "类型无效"
        return RedirectResponse(url="/web/bo", status_code=302)
    return templates.TemplateResponse(
        "bo_form.html",
        {
            "request": request,
            "user": me,
            "mode": "new",
            "types": types,
            "payload": payload,
            "error": None,
        },
    )


@router.post("/web/bo/new")
async def bo_new_submit(request: Request):
    me, resp = _bo_admin_response(request)
    if resp is not None:
        return resp
    form = await request.form()
    tc = str(form.get("object_type") or "").strip().upper()
    bid = str(form.get("business_key") or "").strip()
    if not bid:
        request.session["bo_msg"] = "请填写业务主键"
        return RedirectResponse(url=f"/web/bo/new?type={urlquote(tc)}", status_code=302)
    if len(bid) > 128:
        request.session["bo_msg"] = "业务主键过长（≤128）"
        return RedirectResponse(url=f"/web/bo/new?type={urlquote(tc)}", status_code=302)
    with cursor() as cur:
        t = crud_services.resolve_type(cur, tc)
        if not t:
            request.session["bo_msg"] = "类型无效"
            return RedirectResponse(url="/web/bo/new", status_code=302)
        valid = crud_services.valid_attr_ids_for_type(cur, int(t["id"]))
    vals = crud_services.parse_attr_values_from_form(form, valid_ids=valid)
    with transaction() as cur:
        r = crud_services.create_business_object(
            cur, type_code=tc, business_key=bid, values_by_attr_id=vals
        )
    if not r.get("ok"):
        err = r.get("error")
        if err == "duplicate_key":
            request.session["bo_msg"] = "业务主键已存在（同类型下唯一）"
        elif err == "empty_key":
            request.session["bo_msg"] = "业务主键不能为空"
        else:
            request.session["bo_msg"] = "创建失败"
        return RedirectResponse(url=f"/web/bo/new?type={urlquote(tc)}", status_code=302)
    request.session["bo_msg"] = f"已创建：{tc} / {r.get('business_key')}"
    return RedirectResponse(
        url=f"/web/bo?type={urlquote(tc)}&page=1", status_code=302
    )


@router.get("/web/bo/edit", response_class=HTMLResponse)
def bo_edit_form(
    request: Request,
    object_type: str = Query(..., alias="type"),
    business_key: str = Query(..., alias="key"),
):
    me, resp = _bo_admin_response(request)
    if resp is not None:
        return resp
    tc = object_type.strip().upper()
    bk = business_key.strip()
    with cursor() as cur:
        types = crud_services.list_types_minimal(cur)
        payload = crud_services.get_object_for_edit(cur, type_code=tc, business_key=bk)
    if not payload:
        request.session["bo_msg"] = "记录不存在"
        return RedirectResponse(url=f"/web/bo?type={urlquote(tc)}", status_code=302)
    return templates.TemplateResponse(
        "bo_form.html",
        {
            "request": request,
            "user": me,
            "mode": "edit",
            "types": types,
            "payload": payload,
            "error": None,
        },
    )


@router.post("/web/bo/edit")
async def bo_edit_submit(request: Request):
    me, resp = _bo_admin_response(request)
    if resp is not None:
        return resp
    form = await request.form()
    tc = str(form.get("object_type") or "").strip().upper()
    old_k = str(form.get("original_key") or "").strip()
    new_k = str(form.get("business_key") or "").strip()
    if len(new_k) > 128:
        request.session["bo_msg"] = "业务主键过长（≤128）"
        return RedirectResponse(
            url=f"/web/bo/edit?type={urlquote(tc)}&key={urlquote(old_k)}",
            status_code=302,
        )
    with cursor() as cur:
        t = crud_services.resolve_type(cur, tc)
        if not t:
            request.session["bo_msg"] = "类型无效"
            return RedirectResponse(url="/web/bo", status_code=302)
        valid = crud_services.valid_attr_ids_for_type(cur, int(t["id"]))
    vals = crud_services.parse_attr_values_from_form(form, valid_ids=valid)
    with transaction() as cur:
        r = crud_services.update_business_object(
            cur,
            type_code=tc,
            old_business_key=old_k,
            new_business_key=new_k,
            values_by_attr_id=vals,
        )
    if not r.get("ok"):
        err = r.get("error")
        if err == "duplicate_key":
            request.session["bo_msg"] = "业务主键冲突（同类型下唯一）"
        elif err == "not_found":
            request.session["bo_msg"] = "记录不存在"
        elif err == "empty_key":
            request.session["bo_msg"] = "业务主键不能为空"
        else:
            request.session["bo_msg"] = "保存失败"
        return RedirectResponse(
            url=f"/web/bo/edit?type={urlquote(tc)}&key={urlquote(old_k)}",
            status_code=302,
        )
    nk = str(r.get("business_key") or new_k)
    request.session["bo_msg"] = "已保存"
    return RedirectResponse(
        url=f"/web/bo/edit?type={urlquote(tc)}&key={urlquote(nk)}", status_code=302
    )


@router.post("/web/bo/delete")
async def bo_delete_submit(request: Request):
    me, resp = _bo_admin_response(request)
    if resp is not None:
        return resp
    form = await request.form()
    tc = str(form.get("object_type") or "").strip().upper()
    bk = str(form.get("business_key") or "").strip()
    with transaction() as cur:
        r = crud_services.delete_business_object(cur, type_code=tc, business_key=bk)
    if not r.get("ok"):
        request.session["bo_msg"] = "删除失败或记录不存在"
    else:
        request.session["bo_msg"] = f"已删除 {tc} / {bk}"
    return RedirectResponse(url=f"/web/bo?type={urlquote(tc)}", status_code=302)
