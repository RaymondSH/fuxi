"""外发模型前的轻量 PII 掩码与引用校验。"""
from __future__ import annotations

import re

_PATTERNS = (
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<![\w.])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.])"),
    re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
)


def mask_pii(text: str) -> tuple[str, bool]:
    masked, changed = text, False
    for pattern in _PATTERNS:
        masked, count = pattern.subn("[PII已隐藏]", masked)
        changed = changed or count > 0
    return masked, changed


def verify_citations(answer: str, source_count: int) -> dict:
    cited = [int(n) for n in re.findall(r"\[(\d+)\]", answer)]
    invalid = sorted({n for n in cited if n < 1 or n > source_count})
    if source_count == 0:
        return {"status": "warning", "invalid_citations": invalid, "message": "没有可用来源"}
    if invalid:
        return {"status": "warning", "invalid_citations": invalid, "message": "回答包含无效引用"}
    if not cited:
        return {"status": "warning", "invalid_citations": [], "message": "回答未标注来源"}
    return {"status": "supported", "invalid_citations": [], "message": "引用编号有效"}

