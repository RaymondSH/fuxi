"""全局配置：从环境变量 / .env 读取。

AI 服务统一一套配置：智谱 /api/paas/v4/ 兼容 OpenAI 协议，聊天/视觉/向量共用一个 Key。
换兼容 OpenAI 协议的 provider（智谱/DeepSeek/月之暗面/OpenAI）只改 API_KEY +
AI_BASE_URL + 模型名；接不兼容协议的 provider 再按需新增配置项（见 services/providers/）。
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # 应用版本（单一来源：main.py 的 FastAPI version 与前端系统状态都读这里）
    app_version: str = "0.4.0"

    # 数据库
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/fuxi"
    )

    # ── AI 服务统一配置 ──
    # 智谱一个 Key 通吃聊天 / 视觉 / 向量；换 provider 改下面几项即可。
    ai_api_key: str = os.getenv("API_KEY", "")
    ai_base_url: str = os.getenv("AI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    chat_model: str = os.getenv("CHAT_MODEL", "glm-5.2")          # 对话/提炼/问答
    vision_model: str = os.getenv("VISION_MODEL", "glm-4.6v")     # 图片入库视觉理解
    # 向量维度必须和 sql/02_notes.sql 的 vector(1536) 一致；换维度要同时改 SQL
    embed_model: str = os.getenv("EMBED_MODEL", "embedding-3")
    embed_dim: int = int(os.getenv("EMBED_DIM", "1536"))

    # ── 文档分块 ──
    # 长文档按 chunk_size 切块（含 overlap 重叠，避免切断语义）；过短的块并入相邻块。
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "120"))
    chunk_min_size: int = int(os.getenv("CHUNK_MIN_SIZE", "80"))

    # 抓取微信公众号用 Jina Reader 前缀
    jina_reader_prefix: str = os.getenv("JINA_READER_PREFIX", "https://r.jina.ai/")

    # ── 原始文件存储（摄取时的源文件落盘）──
    # storage_backend=local 落服务器本地目录（默认，零依赖）；
    # =r2 用 Cloudflare R2（S3 兼容，填好 R2_* 凭据即生效）。换后端只改这里。
    storage_backend: str = os.getenv("STORAGE_BACKEND", "local")
    storage_local_root: str = os.getenv("STORAGE_LOCAL_ROOT", "/opt/fuxi/raw")
    # R2 / S3 兼容凭据（未开通时留空，自动回退 local）
    r2_endpoint: str = os.getenv("R2_ENDPOINT", "")        # 如 https://<acct>.r2.cloudflarestorage.com
    r2_access_key_id: str = os.getenv("R2_ACCESS_KEY_ID", "")
    r2_secret_access_key: str = os.getenv("R2_SECRET_ACCESS_KEY", "")
    r2_bucket: str = os.getenv("R2_BUCKET", "fuxi")
    r2_public_base_url: str = os.getenv("R2_PUBLIC_BASE_URL", "")  # 对外可读的 base，留空则返回 key

    # ── Elasticsearch 关键词检索（ik 中文分词）──
    # 留空则关键词路回退 Postgres ILIKE；填 http://127.0.0.1:9200 走 ES。
    es_url: str = os.getenv("ES_URL", "")
    es_timeout: float = float(os.getenv("ES_TIMEOUT", "5.0"))  # 检索/索引超时（秒）

    # ── 鉴权 / 配额（见 docs/auth-design.md）──
    # JWT_SECRET 必填（随机长串）；未配置时登录/鉴权直接报错，不放行。
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_expire_hours: int = int(os.getenv("JWT_EXPIRE_HOURS", "168"))  # 默认 7 天
    # 普通用户每日 token 上限（用户未单独设额度时用此默认）；admin 不限。
    default_daily_token_limit: int = int(os.getenv("DEFAULT_DAILY_TOKEN_LIMIT", "100000"))
    # 配额按此时区算「自然日」边界，次日 0 点重置。
    usage_tz: str = os.getenv("USAGE_TZ", "Asia/Shanghai")


settings = Settings()
