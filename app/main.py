import asyncio
import json

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.middleware.sessions import SessionMiddleware

from app.config import SESSION_SECRET
from app.db import cursor
from app import log_buffer, services
from app.logging_setup import setup_logging
from app.web_routes import router as web_router

setup_logging()

app = FastAPI(title="AI Metadata MDM", version="0.2.0")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")
app.include_router(web_router)


@app.get("/api/logs")
def api_logs_snapshot(n: int = Query(300, ge=1, le=4000)):
    """最近 n 条业务日志（内存缓冲），用于页面首屏加载。"""
    return {"items": log_buffer.tail_last(n)}


@app.get("/api/logs/stream")
async def api_logs_stream(request: Request):
    """Server-Sent Events：实时推送 mdm.business 日志（需已登录会话）。"""

    async def event_gen():
        last_id = 0
        while True:
            if await request.is_disconnected():
                break
            if not request.session.get("username"):
                yield 'data: {"err":"login"}\n\n'
                break
            batch = log_buffer.tail_since(last_id, limit=150)
            if not batch:
                yield ": ping\n\n"
            else:
                for item in batch:
                    last_id = item["id"]
                    yield "data: " + json.dumps(item, ensure_ascii=False) + "\n\n"
            await asyncio.sleep(0.35)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/users")
def users():
    with cursor() as cur:
        return {"users": services.list_users(cur)}


@app.get("/object-types")
def object_types():
    with cursor() as cur:
        return {"object_types": services.list_object_types(cur)}


@app.get("/permissions")
def permissions(username: str = Query(..., description="mdm_users.username")):
    with cursor() as cur:
        data = services.list_grants_for_user(cur, username)
    if data.get("error") == "user_not_found":
        raise HTTPException(status_code=404, detail=data)
    return data


@app.get("/objects/{object_type_code}")
def list_objects(
    object_type_code: str,
    username: str = Query(..., description="mdm_users.username"),
):
    with cursor() as cur:
        data = services.list_object_keys_filtered(
            cur,
            username=username,
            object_type_code=object_type_code.upper(),
        )
    if data.get("error") == "user_not_found":
        raise HTTPException(status_code=404, detail=data)
    return data


@app.get("/objects/{object_type_code}/{business_key}")
def get_object(
    object_type_code: str,
    business_key: str,
    username: str = Query(..., description="mdm_users.username"),
):
    with cursor() as cur:
        data = services.get_object_filtered(
            cur,
            username=username,
            object_type_code=object_type_code.upper(),
            business_key=business_key,
        )
    err = data.get("error")
    if err == "user_not_found":
        raise HTTPException(status_code=404, detail=data)
    if err == "object_not_found":
        raise HTTPException(status_code=404, detail=data)
    if err == "row_access_denied":
        raise HTTPException(status_code=403, detail=data)
    if err == "no_visible_attributes":
        raise HTTPException(status_code=403, detail=data)
    return data
