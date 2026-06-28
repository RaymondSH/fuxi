"""原始文件落盘：抽象对象存储 + LocalStore / R2Store 两个实现 + 工厂。

摄取时把源文件（pdf/docx/xlsx/图片 等）原样存下来，写回 notes.raw_path。
策略与 providers 层一致：换后端（local↔R2↔S3）只改配置，不改调用方。

- STORAGE_BACKEND=local：落服务器本地目录（默认，零依赖）
- STORAGE_BACKEND=r2   ：用 Cloudflare R2（S3 兼容，依赖 boto3；凭据未填时自动回退 local）
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod

from config import settings


class ObjectStore(ABC):
    """对象存储抽象：put 写、get 读、public_url 取对外地址、exists 判断。"""

    @abstractmethod
    def put(self, key: str, data: bytes) -> str:
        """存入 data 到 key，返回写回 notes.raw_path 的 path 标识。"""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """读出 key 对应的原始字节。"""

    @abstractmethod
    def public_url(self, key: str) -> str:
        """对外可访问的 URL（local 时返回本地路径；R2 时返回公网/预签名 URL）。"""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """key 是否已存在。"""


class LocalStore(ObjectStore):
    """落本地文件系统：根目录 / {note_id} / {filename}。"""

    def __init__(self, root: str) -> None:
        self._root = root

    def _path(self, key: str) -> str:
        return os.path.join(self._root, key)

    def put(self, key: str, data: bytes) -> str:
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        # raw_path 存相对 key，读时再拼根目录，便于整体迁移
        return key

    def get(self, key: str) -> bytes:
        with open(self._path(key), "rb") as f:
            return f.read()

    def public_url(self, key: str) -> str:
        # 本地落盘无对外 URL，返回服务器路径供排查
        return self._path(key)

    def exists(self, key: str) -> bool:
        return os.path.exists(self._path(key))


class R2Store(ObjectStore):
    """Cloudflare R2 / S3 兼容存储。凭据未填时不应被构造（工厂会回退 local）。"""

    def __init__(self) -> None:
        import boto3  # 延迟导入：local 模式无需 boto3

        self._s3 = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            region_name="auto",
        )
        self._bucket = settings.r2_bucket
        self._public_base = settings.r2_public_base_url

    def put(self, key: str, data: bytes) -> str:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    def get(self, key: str) -> bytes:
        return self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def public_url(self, key: str) -> str:
        if self._public_base:
            return f"{self._public_base.rstrip('/')}/{key}"
        # 未配公网 base 时返回 key，调用方按需自行预签名
        return key

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False


_store: ObjectStore | None = None


def get_store() -> ObjectStore:
    """返回当前存储后端单例。

    - backend=r2 且凭据齐全 → R2Store
    - 否则 → LocalStore（含 backend 配错 / 凭据缺失的静默回退）
    """
    global _store
    if _store is not None:
        return _store

    if (
        settings.storage_backend == "r2"
        and settings.r2_endpoint
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
    ):
        _store = R2Store()
    else:
        _store = LocalStore(settings.storage_local_root)
    return _store


__all__ = ["ObjectStore", "LocalStore", "R2Store", "get_store"]
