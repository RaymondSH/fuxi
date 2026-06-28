"""智谱 GLM provider：用智谱开放平台 API 实现 LLM 与 Embedding。

智谱 /api/paas/v4/ 兼容 OpenAI 协议，故复用 openai SDK + base_url，无需新依赖。
  - 对话/视觉/向量共用一个 API Key（settings.ai_api_key）。
  - thinking / reasoning_effort 是智谱专属参数，通过 OpenAI SDK 的 extra_body 透传。
  - 结构化输出用 response_format={"type":"json_object"} + system 嵌 schema 提示，
    再用 IngestResult.model_validate_json() 解析（智谱没有 Anthropic 的 messages.parse）。

文档：https://docs.bigmodel.cn/cn/guide/models/text/glm-5.2
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from openai import AsyncOpenAI, OpenAI

from config import settings
from services import usage
from services.providers.base import (
    INGEST_SYSTEM,
    QA_SYSTEM,
    WIKI_COMPILE_SYSTEM,
    EmbeddingProvider,
    IngestResult,
    LLMProvider,
    WikiCompileResult,
)

# 懒加载：模块导入时不创建客户端，否则空 API key 会让整个后端起不来。
# 真正用到（入库提炼那一步）才构造；缺 key 时在此处抛错，被 worker 记成入库失败。
_client: OpenAI | None = None
_async_client: AsyncOpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.ai_api_key:
            raise RuntimeError("未配置 API_KEY，无法调用智谱 GLM")
        _client = OpenAI(
            api_key=settings.ai_api_key,
            base_url=settings.ai_base_url,
        )
    return _client


def _get_async_client() -> AsyncOpenAI:
    """异步客户端（流式问答用）。与同步客户端分离，各自单例复用。"""
    global _async_client
    if _async_client is None:
        if not settings.ai_api_key:
            raise RuntimeError("未配置 API_KEY，无法调用智谱 GLM")
        _async_client = AsyncOpenAI(
            api_key=settings.ai_api_key,
            base_url=settings.ai_base_url,
        )
    return _async_client


# ---------- LLM ----------

class GLMProvider(LLMProvider):
    """智谱 GLM 对话/视觉 provider。"""

    def analyze(self, content: str, *, title_hint: str = "") -> IngestResult:
        """入库提炼：摘要+要点+标签+实体，结构化 JSON 输出。"""
        user = content if not title_hint else f"标题提示：{title_hint}\n\n正文：\n{content}"
        resp = _get_client().chat.completions.create(
            model=settings.chat_model,
            max_tokens=4096,
            temperature=1.0,
            messages=[
                {"role": "system", "content": INGEST_SYSTEM},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            extra_body={
                "thinking": {"type": "enabled"},
                "reasoning_effort": "max",
            },
        )
        usage.record_call(getattr(resp, "usage", None))
        text = resp.choices[0].message.content or ""
        return IngestResult.model_validate_json(text)

    def answer(self, question: str, context: str, history: list[dict] | None = None) -> str:
        """基于检索到的来源生成带依据的回答。history 为多轮上下文。"""
        messages: list[dict] = [
            {"role": "system", "content": QA_SYSTEM},
        ]
        for turn in history or []:
            role = "assistant" if turn.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": turn.get("text", "")})
        messages.append(
            {"role": "user", "content": f"以下是知识库检索到的来源：\n\n{context}\n\n问题：{question}"}
        )
        resp = _get_client().chat.completions.create(
            model=settings.chat_model,
            max_tokens=2048,
            temperature=1.0,
            messages=messages,
            extra_body={"thinking": {"type": "enabled"}},
        )
        usage.record_call(getattr(resp, "usage", None))
        return resp.choices[0].message.content or ""

    async def answer_stream(
        self, question: str, context: str, history: list[dict] | None = None
    ) -> AsyncIterator[str]:
        """流式问答：用 stream=True 逐块 yield 生成内容，前端逐字渲染。

        消息拼装与非流式 answer 完全一致，区别只在 stream=True 与逐块取出 delta。
        """
        messages: list[dict] = [{"role": "system", "content": QA_SYSTEM}]
        for turn in history or []:
            role = "assistant" if turn.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": turn.get("text", "")})
        messages.append(
            {"role": "user", "content": f"以下是知识库检索到的来源：\n\n{context}\n\n问题：{question}"}
        )
        stream = await _get_async_client().chat.completions.create(
            model=settings.chat_model,
            max_tokens=2048,
            temperature=1.0,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},  # 末尾 chunk 带 usage，用于配额计费
            extra_body={"thinking": {"type": "enabled"}},
        )
        async for chunk in stream:
            # 含 usage 的统计 chunk（通常是最后一个）choices 为空
            if getattr(chunk, "usage", None):
                usage.record_call(chunk.usage)
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta

    def describe_image(self, image_b64: str, media_type: str) -> str:
        """让视觉模型描述一张图片，输出可入库的文字内容。"""
        data_url = f"data:{media_type};base64,{image_b64}"
        resp = _get_client().chat.completions.create(
            model=settings.vision_model,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {
                            "type": "text",
                            "text": "详细描述这张图片的内容；如果包含文字、图表或数据，"
                            "请把它们转写出来。输出纯文本。",
                        },
                    ],
                }
            ],
        )
        usage.record_call(getattr(resp, "usage", None))
        return resp.choices[0].message.content or ""

    def compile_wiki(self, sources: list[dict], topic: str) -> WikiCompileResult:
        """主题页编译：把多篇笔记综合成结构化 sections + 冲突标记，JSON 输出。"""
        # 每篇来源截前 1200 字，控制上下文长度
        blocks = []
        for i, s in enumerate(sources, 1):
            excerpt = (s.get("content") or s.get("summary") or "")[:1200]
            blocks.append(f"[来源{i}] note_id={s['id']}\n标题：{s.get('title','')}\n摘要：{s.get('summary','')}\n正文节选：{excerpt}")
        user = f"主题：{topic}\n\n来源：\n\n" + "\n\n".join(blocks)
        resp = _get_client().chat.completions.create(
            model=settings.chat_model,
            max_tokens=4096,
            temperature=1.0,
            messages=[
                {"role": "system", "content": WIKI_COMPILE_SYSTEM},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            extra_body={
                "thinking": {"type": "enabled"},
                "reasoning_effort": "max",
            },
        )
        usage.record_call(getattr(resp, "usage", None))
        text = resp.choices[0].message.content or ""
        return WikiCompileResult.model_validate_json(text)


# ---------- Embedding ----------

class GLMEmbedder(EmbeddingProvider):
    """智谱 embedding-3 向量化。维度可自定义，固定用 settings.embed_dim 对齐 SQL。"""

    def embed(self, text: str) -> list[float]:
        """把一段文本转成定长向量。空文本返回零向量，避免入库报错。"""
        text = (text or "").strip()
        if not text:
            return [0.0] * settings.embed_dim
        # Embedding 模型有输入长度上限，超长就截断（入库向量用摘要+正文前段足够）
        resp = _get_client().embeddings.create(
            model=settings.embed_model,
            input=text[:8000],
            dimensions=settings.embed_dim,
        )
        usage.record_call(getattr(resp, "usage", None))
        return resp.data[0].embedding
