"""Confluence、飞书、Google Drive、SharePoint 只读连接器。"""
from __future__ import annotations

import html
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx

from services import fetcher
from services.logging import get_logger
from .base import ConnectorProvider, RemoteDocument, RemoteItem

log = get_logger("connector_providers")

# 429 / 5xx 重试：指数退避 1s/2s/4s，最多 3 次。
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_RETRY_BACKOFF = (1.0, 2.0, 4.0)


def _request(method: str, url: str, **kwargs) -> httpx.Response:
    """带重试的 HTTP 请求：仅对 429/5xx 退避重试，其余直接返回/抛。

    超时与 headers 由调用方在 kwargs 里传。瞬时限流不再让整轮同步直接失败。
    """
    kwargs.setdefault("timeout", 30)
    last_exc: Exception | None = None
    for attempt, backoff in enumerate(_RETRY_BACKOFF, 1):
        try:
            resp = httpx.request(method, url, **kwargs)
            if resp.status_code in _RETRY_STATUSES and attempt < len(_RETRY_BACKOFF):
                log.warning("HTTP %s 退避重试 %s 第 %s 次", resp.status_code, url, attempt)
                time.sleep(backoff)
                continue
            return resp
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < len(_RETRY_BACKOFF):
                log.warning("请求异常退避重试 %s 第 %s 次: %s", url, attempt, exc)
                time.sleep(backoff)
                continue
            raise
    # 理论上不会走到（循环内必 return 或 raise），防御性兜底
    if last_exc:
        raise last_exc
    return httpx.request(method, url, **kwargs)


def _get_with_retry(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    """带重试的 Client.get：供 Confluence 这类需要 base_url+auth 的 Client 复用。"""
    kwargs.setdefault("timeout", 30)
    last_exc: Exception | None = None
    for attempt, backoff in enumerate(_RETRY_BACKOFF, 1):
        try:
            resp = client.get(url, **kwargs)
            if resp.status_code in _RETRY_STATUSES and attempt < len(_RETRY_BACKOFF):
                log.warning("HTTP %s 退避重试 %s 第 %s 次", resp.status_code, url, attempt)
                time.sleep(backoff)
                continue
            return resp
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < len(_RETRY_BACKOFF):
                log.warning("请求异常退避重试 %s 第 %s 次: %s", url, attempt, exc)
                time.sleep(backoff)
                continue
            raise
    if last_exc:
        raise last_exc
    return client.get(url, **kwargs)


def _plain(value: str) -> str:
    # raw string 里应为 \d（数字），不是 \\d（字面反斜杠 d）——修复标题闭合标签丢失
    value = re.sub(r"<(br|/p|/div|/li|/h\d)>", "\n", value, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


class ConfluenceProvider(ConnectorProvider):
    full_snapshot = True
    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.config["base_url"].rstrip("/"),
            auth=(self.credentials["email"], self.credentials["api_token"]),
            timeout=30,
        )

    def list_changes(self, cursor):
        params = {"limit": 100, "body-format": "storage", "status": "current"}
        if self.config.get("confluence_space_id"):
            params["space-id"] = self.config["confluence_space_id"]
        items = []
        with self._client() as c:
            next_url = "/wiki/api/v2/pages"
            while next_url:
                r = _get_with_retry(c, next_url, params=params if next_url.endswith("/pages") else None)
                r.raise_for_status(); data = r.json()
                items.extend(RemoteItem(
                    external_id=str(p["id"]), title=p["title"],
                    url=urljoin(self.config["base_url"], p.get("_links", {}).get("webui", "")),
                    version=str((p.get("version") or {}).get("number", "")),
                    modified_at=(p.get("version") or {}).get("createdAt"),
                    metadata={"body": p.get("body", {})},
                ) for p in data.get("results", []))
                next_url = data.get("_links", {}).get("next")
        return items, None

    def fetch_content(self, item):
        body = (item.metadata or {}).get("body", {}).get("storage", {}).get("value")
        if body is None:
            with self._client() as c:
                r = _get_with_retry(c, f"/wiki/api/v2/pages/{item.external_id}", params={"body-format": "storage"})
                r.raise_for_status(); body = r.json().get("body", {}).get("storage", {}).get("value", "")
        return RemoteDocument(item, _plain(body))


class FeishuProvider(ConnectorProvider):
    full_snapshot = True
    def _token(self) -> str:
        r = _request("POST", "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                     json={"app_id": self.credentials["app_id"], "app_secret": self.credentials["app_secret"]},
                     timeout=20)
        r.raise_for_status(); data = r.json()
        if data.get("code", 0) != 0: raise RuntimeError(data.get("msg", "飞书认证失败"))
        return data["tenant_access_token"]

    def list_changes(self, cursor):
        token = self._token()
        folders, items = [self.config.get("folder_token", "")], []
        while folders:
            folder, page = folders.pop(), None
            while True:
                params = {"folder_token": folder, "page_size": 200}
                if page: params["page_token"] = page
                r = _request("GET", "https://open.feishu.cn/open-apis/drive/v1/files", params=params,
                             headers={"Authorization": f"Bearer {token}"})
                r.raise_for_status(); data = r.json().get("data", {})
                for x in data.get("files", []):
                    if x.get("type") == "folder":
                        folders.append(x["token"])
                    elif x.get("type") == "docx":
                        modified = str(x.get("modified_time", ""))
                        modified_iso = datetime.fromtimestamp(int(modified), timezone.utc).isoformat() if modified else None
                        items.append(RemoteItem(
                            external_id=x["token"], title=x["name"], url=x.get("url", ""),
                            version=modified, modified_at=modified_iso, metadata={"type": "docx"},
                        ))
                if not data.get("has_more"): break
                page = data.get("next_page_token")
        return items, None

    def fetch_content(self, item):
        token = self._token()
        r = _request(
            "GET",
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{item.external_id}/raw_content",
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status(); data = r.json()
        return RemoteDocument(item, data.get("data", {}).get("content", ""))


class GoogleDriveProvider(ConnectorProvider):
    def _token(self) -> str:
        r = _request("POST", "https://oauth2.googleapis.com/token", data={
            "client_id": self.credentials["client_id"], "client_secret": self.credentials["client_secret"],
            "refresh_token": self.credentials["refresh_token"], "grant_type": "refresh_token",
        }, timeout=20)
        r.raise_for_status(); return r.json()["access_token"]

    def list_changes(self, cursor):
        token = self._token(); headers = {"Authorization": f"Bearer {token}"}
        if cursor:
            r = _request("GET", "https://www.googleapis.com/drive/v3/changes", headers=headers,
                         params={"pageToken": cursor, "fields": "nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,mimeType,modifiedTime,webViewLink,version))"})
            r.raise_for_status(); data = r.json()
            items = []
            for ch in data.get("changes", []):
                f = ch.get("file") or {}
                items.append(RemoteItem(
                    external_id=ch["fileId"], title=f.get("name", ch["fileId"]),
                    url=f.get("webViewLink", ""), version=str(f.get("version", "")),
                    modified_at=f.get("modifiedTime"), deleted=bool(ch.get("removed")),
                    metadata={"mimeType": f.get("mimeType")},
                ))
            return items, data.get("nextPageToken") or data.get("newStartPageToken") or cursor
        items, page_token = [], None
        while True:
            params = {
                "pageSize": 1000,
                "q": "trashed=false",
                "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink,version)",
            }
            if page_token:
                params["pageToken"] = page_token
            r = _request(
                "GET", "https://www.googleapis.com/drive/v3/files",
                headers=headers, params=params,
            )
            r.raise_for_status()
            data = r.json()
            items.extend(
                RemoteItem(
                    str(f["id"]), f["name"], f.get("webViewLink", ""),
                    str(f.get("version", "")), f.get("modifiedTime"),
                    metadata={"mimeType": f.get("mimeType")},
                )
                for f in data.get("files", [])
                if f.get("mimeType") != "application/vnd.google-apps.folder"
            )
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        t = _request("GET", "https://www.googleapis.com/drive/v3/changes/startPageToken",
                     headers=headers, timeout=20); t.raise_for_status()
        return items, t.json()["startPageToken"]

    def fetch_content(self, item):
        token = self._token(); headers = {"Authorization": f"Bearer {token}"}
        mime = (item.metadata or {}).get("mimeType", "")
        if mime.startswith("application/vnd.google-apps"):
            r = _request("GET", f"https://www.googleapis.com/drive/v3/files/{item.external_id}/export",
                         params={"mimeType": "text/plain"}, headers=headers)
            r.raise_for_status(); content = r.text
        else:
            r = _request("GET", f"https://www.googleapis.com/drive/v3/files/{item.external_id}",
                         params={"alt": "media"}, headers=headers)
            r.raise_for_status()
            content = fetcher.fetch(data=r.content, filename=item.title).content
        return RemoteDocument(item, content)


class SharePointProvider(ConnectorProvider):
    def _token(self) -> str:
        tenant = self.credentials["tenant_id"]
        r = _request("POST", f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", data={
            "client_id": self.credentials["client_id"], "client_secret": self.credentials["client_secret"],
            "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials",
        }, timeout=20)
        r.raise_for_status(); return r.json()["access_token"]

    def list_changes(self, cursor):
        token, drive = self._token(), self.config["drive_id"]
        url = cursor or f"https://graph.microsoft.com/v1.0/drives/{drive}/root/delta"
        r = _request("GET", url, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status(); data = r.json()
        items = [RemoteItem(
            external_id=x["id"], title=x.get("name", x["id"]),
            url=x.get("webUrl", ""), version=x.get("eTag", ""),
            modified_at=x.get("lastModifiedDateTime"), deleted="deleted" in x,
            metadata={"folder": "folder" in x},
        ) for x in data.get("value", []) if "folder" not in x]
        return items, data.get("@odata.nextLink") or data.get("@odata.deltaLink") or cursor

    def fetch_content(self, item):
        token, drive = self._token(), self.config["drive_id"]
        r = _request("GET", f"https://graph.microsoft.com/v1.0/drives/{drive}/items/{item.external_id}/content",
                     headers={"Authorization": f"Bearer {token}"}, follow_redirects=True, timeout=60)
        r.raise_for_status()
        return RemoteDocument(item, fetcher.fetch(data=r.content, filename=item.title).content)
