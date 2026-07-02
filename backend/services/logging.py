"""结构化日志：统一 JSON 格式输出到 stdout，供 systemd/journald 收集与检索。

设计要点：
- 全应用统一一个 logger 名 "fuxi"，子模块用 fuxi.<name> 自动继承根配置。
- JSON 格式（level/ts/logger/msg + 可选字段）；本地开发可用 LOG_FORMAT=text 切纯文本便于阅读。
- uvicorn / uvicorn.access 也挂同一 handler，避免 access log 走默认 stderr 原始格式。
- 幂等：多次调用 setup_logging() 不重复加 handler。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

_STD_FORMAT = "%(asctime)s %(levelname)-7s %(name)s %(message)s"
_LOGGER_NAME = "fuxi"
_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    """单行 JSON 日志 formatter：每条 record 输出一个 JSON 对象。"""

    _RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime", "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        payload: dict[str, object] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # 业务方用 logger.info("...", extra={"event": "login", "user_id": uid}) 透传字段
        for key, val in record.__dict__.items():
            if key in self._RESERVED or key in payload:
                continue
            payload[key] = val
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", fmt: str = "json") -> None:
    """配置 fuxi 根 logger + uvicorn logger。幂等。

    level: LOG_LEVEL 环境变量（DEBUG/INFO/WARNING/ERROR）。
    fmt:   json（生产，默认）或 text（本地开发便于阅读）。
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger(_LOGGER_NAME)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(_STD_FORMAT) if fmt == "text" else _JsonFormatter()
    )
    root.addHandler(handler)
    root.propagate = False  # 不冒泡到 Python root，避免 uvicorn 默认 handler 重复输出

    # uvicorn 的日志也走同一 handler，保持统一格式（含 access log）
    uvicorn_log = logging.getLogger("uvicorn")
    uvicorn_log.handlers = [handler]
    uvicorn_log.propagate = False
    access_log = logging.getLogger("uvicorn.access")
    access_log.handlers = [handler]
    access_log.propagate = False

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """取 fuxi.<name> 子 logger，继承根配置。"""
    if name.startswith(_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
