"""连接器凭据加解密；Fernet 主密钥只来自环境变量。"""
from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken

from config import settings


def _fernet() -> Fernet:
    if not settings.connector_secret_key:
        raise RuntimeError("未配置 CONNECTOR_SECRET_KEY")
    return Fernet(settings.connector_secret_key.encode())


def encrypt(credentials: dict) -> bytes:
    return _fernet().encrypt(json.dumps(credentials, ensure_ascii=False).encode())


def decrypt(value: bytes) -> dict:
    try:
        return json.loads(_fernet().decrypt(bytes(value)).decode())
    except InvalidToken as exc:
        raise RuntimeError("连接器凭据无法解密") from exc

