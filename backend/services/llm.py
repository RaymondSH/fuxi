"""LLM 调用门面：入库提炼 / 问答 / 图片描述。

对外保持 analyze / answer / describe_image 三个函数（调用方零改动），内部委托
services/providers 工厂返回的 LLMProvider。换 provider（智谱 GLM / Anthropic ...）
只改 providers 配置，不改这里。

数据模型 IngestResult / Entity 从 providers.base re-export，保持
`from services.llm import IngestResult` 可用。
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from services import providers
from services.providers.base import (
    Entity,
    EntityType,
    IngestResult,
    WikiCompileResult,
)


def analyze(content: str, *, title_hint: str = "") -> IngestResult:
    """对一篇正文做摘要+要点+标签+实体提取，返回结构化结果。"""
    return providers.get_llm().analyze(content, title_hint=title_hint)


def answer(question: str, context: str, history: list[dict] | None = None) -> str:
    """基于检索到的来源（context）生成带依据的回答。history 为多轮上下文。"""
    return providers.get_llm().answer(question, context, history)


async def answer_stream(
    question: str, context: str, history: list[dict] | None = None
) -> AsyncIterator[str]:
    """流式问答：逐块 yield 生成内容，供 SSE 推给前端逐字渲染。"""
    async for chunk in providers.get_llm().answer_stream(question, context, history):
        yield chunk


def describe_image(image_b64: str, media_type: str) -> str:
    """让模型描述一张图片，输出可入库的文字内容。"""
    return providers.get_llm().describe_image(image_b64, media_type)


def compile_wiki(sources: list[dict], topic: str) -> WikiCompileResult:
    """主题页编译：把多篇笔记综合成结构化 sections + 冲突标记。"""
    return providers.get_llm().compile_wiki(sources, topic)


__all__ = [
    "Entity",
    "EntityType",
    "IngestResult",
    "WikiCompileResult",
    "analyze",
    "answer",
    "answer_stream",
    "compile_wiki",
    "describe_image",
]
