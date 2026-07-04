"""M4 企业连接器管理 API。"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from db import pool
from services import audit, connector_crypto, spaces
from services.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/connectors", tags=["connectors"])
_REQUIRED = {
    "confluence": (("base_url",), ("email", "api_token")),
    "feishu": (("folder_token",), ("app_id", "app_secret")),
    "google_drive": ((), ("client_id", "client_secret", "refresh_token")),
    "sharepoint": (("drive_id",), ("tenant_id", "client_id", "client_secret")),
}


class ConnectorCreate(BaseModel):
    space_id: uuid.UUID
    provider: str
    name: str
    config: dict = Field(default_factory=dict)
    credentials: dict


class ConnectorPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    config: dict | None = None
    credentials: dict | None = None
    status: str | None = None


@router.get("")
def list_connectors(space_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> dict:
    spaces.assert_space_role(user, space_id, "viewer")
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id,provider,name,config,status,error_msg,last_synced_at FROM connector_accounts "
            "WHERE space_id=%s ORDER BY created_at DESC", (space_id,)
        ).fetchall()
    return {"items": [{"id": r[0], "provider": r[1], "name": r[2], "config": r[3],
                       "status": r[4], "error_msg": r[5],
                       "last_synced_at": r[6].isoformat() if r[6] else None} for r in rows]}


@router.post("", status_code=201)
def create_connector(req: ConnectorCreate, request: Request,
                     user: CurrentUser = Depends(get_current_user)) -> dict:
    spaces.assert_space_role(user, req.space_id, "space_admin")
    if req.provider not in ("confluence", "feishu", "google_drive", "sharepoint"):
        raise HTTPException(status_code=422, detail="非法连接器类型")
    config_keys, credential_keys = _REQUIRED[req.provider]
    missing = [k for k in config_keys if not req.config.get(k)]
    missing += [k for k in credential_keys if not req.credentials.get(k)]
    if missing:
        raise HTTPException(status_code=422, detail=f"缺少连接器字段：{', '.join(missing)}")
    connector_id = uuid.uuid4()
    try:
        encrypted = connector_crypto.encrypt(req.credentials)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO connector_accounts(id,space_id,provider,name,config,credentials,created_by) "
            "VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s)",
            (connector_id, req.space_id, req.provider, req.name,
             json.dumps(req.config, ensure_ascii=False), encrypted, user.id),
        )
    audit.log("connector_create", request=request, user_id=user.id,
              target_type="connector", target_id=connector_id,
              detail={"provider": req.provider, "space_id": str(req.space_id)})
    return {"id": connector_id, "status": "active"}


@router.patch("/{connector_id}")
def update_connector(
    connector_id: uuid.UUID, req: ConnectorPatch, request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT space_id,provider FROM connector_accounts WHERE id=%s",
            (connector_id,),
        ).fetchone()
    if row is None: raise HTTPException(status_code=404, detail="连接器不存在")
    spaces.assert_space_role(user, row[0], "space_admin")
    values = req.model_dump(exclude_unset=True)
    for key in ("name", "config", "credentials", "status"):
        if key in values and values[key] is None:
            raise HTTPException(status_code=422, detail=f"{key} 不能为 null")
    if "status" in values and values["status"] not in ("active", "disabled"):
        raise HTTPException(status_code=422, detail="非法状态")
    config_keys, credential_keys = _REQUIRED[row[1]]
    if "config" in values:
        missing = [key for key in config_keys if not values["config"].get(key)]
        if missing:
            raise HTTPException(status_code=422, detail=f"缺少连接器字段：{', '.join(missing)}")
    if "credentials" in values:
        missing = [key for key in credential_keys if not values["credentials"].get(key)]
        if missing:
            raise HTTPException(status_code=422, detail=f"缺少连接器字段：{', '.join(missing)}")
    sets, params = [], []
    for key in ("name", "status"):
        if key in values:
            sets.append(f"{key}=%s"); params.append(values[key])
    if "config" in values:
        sets.extend(["config=%s::jsonb", "sync_cursor=NULL"]); params.append(json.dumps(values["config"]))
    if "credentials" in values:
        sets.extend(["credentials=%s", "sync_cursor=NULL"])
        try:
            params.append(connector_crypto.encrypt(values["credentials"]))
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not sets: return {"id": connector_id}
    with pool.connection() as conn:
        conn.execute(f"UPDATE connector_accounts SET {','.join(sets)},updated_at=NOW() WHERE id=%s",
                     [*params, connector_id])
    audit.log("connector_update", request=request, user_id=user.id,
              target_type="connector", target_id=connector_id)
    return {"id": connector_id}


@router.delete("/{connector_id}", status_code=204)
def delete_connector(
    connector_id: uuid.UUID, request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    with pool.connection() as conn:
        row = conn.execute("SELECT space_id FROM connector_accounts WHERE id=%s", (connector_id,)).fetchone()
    if row is None: raise HTTPException(status_code=404, detail="连接器不存在")
    spaces.assert_space_role(user, row[0], "space_admin")
    with pool.connection() as conn:
        conn.execute("DELETE FROM connector_accounts WHERE id=%s", (connector_id,))
    audit.log("connector_delete", request=request, user_id=user.id,
              target_type="connector", target_id=connector_id)


@router.post("/{connector_id}/sync", status_code=202)
def sync_connector(connector_id: uuid.UUID, request: Request,
                   user: CurrentUser = Depends(get_current_user)) -> dict:
    with pool.connection() as conn:
        row = conn.execute("SELECT space_id,name FROM connector_accounts WHERE id=%s", (connector_id,)).fetchone()
    if row is None: raise HTTPException(status_code=404, detail="连接器不存在")
    spaces.assert_space_role(user, row[0], "space_admin")
    job_id = uuid.uuid4()
    with pool.connection() as conn:
        conn.execute("UPDATE connector_accounts SET status='active',error_msg=NULL WHERE id=%s",
                     (connector_id,))
        conn.execute(
            "INSERT INTO jobs(id,job_type,payload,status,stage,title) VALUES("
            "%s,'connector_sync',jsonb_build_object('connector_id',%s::text),'queued','queued',%s)",
            (job_id, connector_id, f"同步 {row[1]}"),
        )
    audit.log("connector_sync", request=request, user_id=user.id,
              target_type="connector", target_id=connector_id)
    return {"job_id": job_id, "status": "pending"}


@router.get("/{connector_id}/items")
def list_items(connector_id: uuid.UUID, user: CurrentUser = Depends(get_current_user)) -> dict:
    with pool.connection() as conn:
        row = conn.execute("SELECT space_id FROM connector_accounts WHERE id=%s", (connector_id,)).fetchone()
        if row is None: raise HTTPException(status_code=404, detail="连接器不存在")
        spaces.assert_space_role(user, row[0], "viewer")
        items = conn.execute(
            "SELECT external_id,note_id,remote_version,status,error_msg,synced_at FROM connector_items "
            "WHERE connector_id=%s ORDER BY synced_at DESC NULLS LAST", (connector_id,)
        ).fetchall()
    return {"items": [{"external_id": r[0], "note_id": r[1], "version": r[2],
                       "status": r[3], "error_msg": r[4],
                       "synced_at": r[5].isoformat() if r[5] else None} for r in items]}
