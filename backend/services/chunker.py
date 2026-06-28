"""文档分块：把长正文切成 chunk，供逐块向量化 + chunk 级语义检索。

用 RecursiveCharacterTextSplitter（按 \\n\\n / \\n / 句号 / 空格 优先级递归切分），
尽量在自然边界断块；过短的块并入相邻块，避免零碎块浪费 embedding 调用。
"""
from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings

# 中文友好分隔符：优先在段落、换行、句末标点处断开
_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", ". ", "! ", "? ", "; ", " ", ""]


def _splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=_SEPARATORS,
        keep_separator=True,
        length_function=len,
    )


def split(content: str) -> list[str]:
    """把正文切成 chunk 列表。空文本返回 []；过短则返回单块或空。

    切完后合并过短块：累计长度未达 chunk_min_size 的相邻块拼到一起，
    避免出现只有一句话的零碎块。
    """
    text = (content or "").strip()
    if not text:
        return []

    chunks = _splitter().split_text(text)
    return _merge_tiny(chunks)


def _merge_tiny(chunks: list[str]) -> list[str]:
    """把过短的块并入相邻块。"""
    min_size = settings.chunk_min_size
    if not chunks or min_size <= 0:
        return chunks

    merged: list[str] = []
    for chunk in chunks:
        c = chunk.strip()
        if not c:
            continue
        if merged and len(c) < min_size:
            # 当前块过短 → 拼到上一块尾部
            merged[-1] = merged[-1] + "\n" + c
        elif merged and len(merged[-1]) < min_size:
            # 上一块过短 → 当前块接到上一块后面
            merged[-1] = merged[-1] + "\n" + c
        else:
            merged.append(c)

    # 末尾若剩一个过短块，并入倒数第二块
    if len(merged) >= 2 and len(merged[-1]) < min_size:
        merged[-2] = merged[-2] + "\n" + merged[-1]
        merged.pop()
    return merged


__all__ = ["split"]
