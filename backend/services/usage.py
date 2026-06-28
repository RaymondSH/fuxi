"""token 用量采集：provider 把每次调用的 usage 记进「当前请求」的累加器。

用 ContextVar 让 provider（services/providers/glm.py）与路由解耦：
  - 路由用 `with usage.collect() as u:` 开一个累加器跑业务；
  - provider 每次调用 API 后 `usage.record_call(resp.usage)` 累加进来；
  - 路由结束把 `u` 交给 services.quota.record_usage 落库。

未开累加器时 record_call 是空操作，所以脚本/迁移直接调 provider 不受影响。
"""
from __future__ import annotations

import contextlib
import contextvars
from dataclasses import dataclass


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, prompt: int = 0, completion: int = 0, total: int = 0) -> None:
        prompt = prompt or 0
        completion = completion or 0
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += total or (prompt + completion)


# 当前累加器（None=没开采集，record_call 静默忽略）
_current: contextvars.ContextVar[Usage | None] = contextvars.ContextVar(
    "fuxi_usage", default=None
)


def record_call(resp_usage) -> None:
    """provider 调用后把 OpenAI 风格的 usage（含 prompt/completion/total_tokens）记进累加器。"""
    acc = _current.get()
    if acc is None or resp_usage is None:
        return
    acc.add(
        getattr(resp_usage, "prompt_tokens", 0),
        getattr(resp_usage, "completion_tokens", 0),
        getattr(resp_usage, "total_tokens", 0),
    )


@contextlib.contextmanager
def collect():
    """开一个新的累加器；with 块内的 provider 调用都会累加到它。"""
    acc = Usage()
    token = _current.set(acc)
    try:
        yield acc
    finally:
        _current.reset(token)
