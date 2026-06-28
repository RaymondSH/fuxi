"""语义向量化门面。

对外保持 embed(text) 签名不变（调用方零改动），内部委托 services/providers 工厂
返回的 EmbeddingProvider。

当前默认用智谱 embedding-3（维度可自定义，固定 settings.embed_dim 对齐 SQL 的
vector(1536)）。要换 OpenAI / Voyage / 本地模型时，只改 provider 实现与配置，
不改这里；并同步改 config.embed_dim 和 SQL 向量维度。
"""
from __future__ import annotations

from services import providers


def embed(text: str) -> list[float]:
    """把一段文本转成定长向量。空文本返回零向量，避免入库报错。"""
    return providers.get_embedder().embed(text)
