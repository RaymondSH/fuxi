"""M4 企业连接器 provider 工厂。"""
from .base import ConnectorProvider, RemoteDocument, RemoteItem
from .providers import ConfluenceProvider, FeishuProvider, GoogleDriveProvider, SharePointProvider

_PROVIDERS = {
    "confluence": ConfluenceProvider,
    "feishu": FeishuProvider,
    "google_drive": GoogleDriveProvider,
    "sharepoint": SharePointProvider,
}


def create(provider: str, config: dict, credentials: dict) -> ConnectorProvider:
    cls = _PROVIDERS.get(provider)
    if cls is None:
        raise ValueError(f"不支持的连接器: {provider}")
    return cls(config, credentials)


__all__ = ["ConnectorProvider", "RemoteDocument", "RemoteItem", "create"]

