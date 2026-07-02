"""连接器统一数据模型与抽象。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RemoteItem:
    external_id: str
    title: str
    url: str
    version: str
    modified_at: str | None = None
    deleted: bool = False
    metadata: dict | None = None


@dataclass
class RemoteDocument:
    item: RemoteItem
    content: str


class ConnectorProvider(ABC):
    full_snapshot = False
    def __init__(self, config: dict, credentials: dict):
        self.config = config
        self.credentials = credentials

    @abstractmethod
    def list_changes(self, cursor: str | None) -> tuple[list[RemoteItem], str | None]:
        pass

    @abstractmethod
    def fetch_content(self, item: RemoteItem) -> RemoteDocument:
        pass
