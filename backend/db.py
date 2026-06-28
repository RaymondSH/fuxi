"""数据库连接池。Worker 用同步连接，简单可靠。"""
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector

from config import settings


def _configure(conn):
    # 每条连接都注册 vector 类型，才能读取/写入 embedding 列。
    # 注意：embedder 返回纯 list[float]，pgvector 官方 dumper 不覆盖 list，
    # 所以查询/入库处对 embedding 参数用 `%s::vector` 显式转型，避免被当成数组。
    register_vector(conn)


pool = ConnectionPool(
    settings.database_url,
    min_size=1,
    max_size=10,
    configure=_configure,
    open=True,
)
