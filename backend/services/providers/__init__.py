"""Provider 工厂：按配置返回 LLM / Embedding provider 实例（单例）。

策略模式的扩展点：未来加新 provider（如 Anthropic），在这两个工厂里加分支即可，
业务层（services/llm.py、services/embedder.py）无需改动。
"""
from __future__ import annotations

from services.providers.base import EmbeddingProvider, LLMProvider
from services.providers.glm import GLMEmbedder, GLMProvider

# 懒加载单例：首次用到才构造，缺 key 时在 provider 内部抛错（被业务层 catch 降级）
_llm: LLMProvider | None = None
_embedder: EmbeddingProvider | None = None


def get_llm() -> LLMProvider:
    """返回当前 LLM provider 单例。"""
    global _llm
    if _llm is None:
        _llm = GLMProvider()
    return _llm


def get_embedder() -> EmbeddingProvider:
    """返回当前 Embedding provider 单例。"""
    global _embedder
    if _embedder is None:
        _embedder = GLMEmbedder()
    return _embedder


__all__ = [
    "EmbeddingProvider",
    "LLMProvider",
    "get_embedder",
    "get_llm",
]
