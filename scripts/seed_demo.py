"""把设计稿里的 6 篇示例笔记 + 实体灌入数据库，用于无密钥时演示检索 / 图谱。

运行（在服务器上，带 backend 到 PYTHONPATH）：
  cd /opt/fuxi/backend && PYTHONPATH=. .venv/bin/python ../scripts/seed_demo.py

幂等：按标题先删后插，重复跑不会产生重复笔记。embedding 留空（无 OPENAI key），
故语义检索此时不可用，关键词检索可用。
"""
from __future__ import annotations

import json
import sys
import uuid

from db import pool

# slug -> 笔记
NOTES = [
    {
        "slug": "n1", "source_type": "url",
        "title": "Anthropic 发布 Claude Opus 4.8",
        "source": "anthropic.com", "date": "2026-06-20",
        "tags": ["AI", "LLM", "Anthropic", "发布"],
        "summary": "Anthropic 推出 Claude Opus 4.8，主打更长上下文窗口（1M tokens）与更强的 agentic 编码能力，在 SWE-bench 上较前代提升明显，定价下调约 20%。",
        "keypoints": [
            "上下文窗口扩展到 1M tokens，长文档问答无需分块",
            "agentic coding 在 SWE-bench Verified 上达到 SOTA",
            "输入 token 价格下调 ~20%，长文场景成本显著降低",
            "原生支持工具调用的并行执行",
        ],
        "content": "Anthropic 今日发布了 Claude Opus 4.8。相较 4.5，这一代在三个方向上做了重点投入：上下文长度、agentic 能力与成本。\n\n上下文窗口从 200K 扩展到 1M tokens，意味着多数中等规模的代码库或长 PDF 可以一次性放入，无需做 chunking。这对 RAG 系统是一个值得重新评估的信号——对于单文档问答，长上下文可能比检索更简单可靠。\n\n在 agentic coding 上，Opus 4.8 在 SWE-bench Verified 上取得了当前最好成绩，并且在多步工具调用任务里表现出更稳定的规划能力。\n\n定价方面，输入 token 下调约 20%。结合更长的上下文，长文档处理的单位成本下降幅度更大。",
    },
    {
        "slug": "n2", "source_type": "pdf",
        "title": "RAG 分块策略实战：从固定窗口到语义切分",
        "source": "report.pdf · 24页", "date": "2026-05-14",
        "tags": ["RAG", "检索", "Embedding", "分块"],
        "summary": "系统对比固定长度、滑动窗口、递归字符与语义切分四类分块策略对检索召回的影响。结论：语义切分在长文档上召回最优，但成本最高；多数场景递归切分 + 适度重叠是性价比之选。",
        "keypoints": [
            "固定窗口实现简单但易切断语义单元，召回波动大",
            "滑动窗口的重叠（10–20%）能显著缓解边界丢失",
            "递归字符切分按结构层级回退，是工程上的稳健默认",
            "语义切分召回最优，但需额外 embedding 调用，成本高 3–5×",
            "chunk 大小与 embedding 模型的最优窗口相关，需实测",
        ],
        "content": "分块（chunking）是 RAG 流水线里最被低估的一环。同一份语料，分块策略不同，检索召回可以相差 30% 以上。\n\n固定长度切分是最简单的基线：按 N 个 token 一刀切。问题在于它会粗暴地切断句子甚至词，导致 chunk 语义不完整，向量表示漂移。\n\n滑动窗口在固定切分的基础上引入重叠区，通常 10–20%。重叠让边界处的语义在相邻 chunk 中都有体现，缓解了「答案正好被切断」的情况。\n\n递归字符切分按 段落 → 句子 → 词 的层级逐级回退，尽量在自然边界处切分。它在工程上是一个稳健的默认选择。\n\n语义切分用 embedding 相似度判断句子是否属于同一语义块，召回最优，但每次切分都要额外的 embedding 调用，成本高 3–5 倍。",
    },
    {
        "slug": "n3", "source_type": "url",
        "title": "pgvector 十亿级向量检索调优笔记",
        "source": "jkutner.github.io", "date": "2026-04-30",
        "tags": ["PostgreSQL", "pgvector", "向量检索", "性能"],
        "summary": "pgvector 0.7 的 HNSW 索引在千万级向量上 P99 可控；超过亿级需关注 maintenance_work_mem、并行构建与 ef_search 调参。给出了一组可复用的参数基线。",
        "keypoints": [
            "HNSW 优于 IVFFlat：召回-延迟曲线更好，无需训练",
            "构建索引时调大 maintenance_work_mem 与 max_parallel_maintenance_workers",
            "查询期 ef_search 是召回与延迟的主旋钮",
            "亿级以上考虑分区表 + 每分区独立索引",
        ],
        "content": "pgvector 把向量检索塞进了 PostgreSQL，省去了单独维护一个向量库的运维成本。但要在亿级规模上跑得动，调参不可少。\n\n索引选型上，HNSW 几乎总是优于 IVFFlat：它的召回-延迟曲线更好，而且不需要预先训练聚类中心。代价是构建慢、占内存。\n\n构建 HNSW 索引时，maintenance_work_mem 一定要调大，否则会频繁落盘导致构建时间爆炸。同时打开并行构建。\n\n查询期最重要的旋钮是 ef_search：调大召回上升、延迟上升。这是一个需要按业务 SLA 实测的权衡。",
    },
    {
        "slug": "n4", "source_type": "image",
        "title": "2026 AI Agent 市场地图（截图 OCR）",
        "source": "whiteboard.jpg · OCR", "date": "2026-06-02",
        "tags": ["Agent", "市场", "创业"],
        "summary": "一张市场地图的 OCR 笔记：把 Agent 赛道分为编排框架、垂直 agent、评测/可观测、记忆/存储四层，并标注了代表公司与开源项目。",
        "keypoints": [
            "编排层：LangGraph / CrewAI / AutoGen 仍在快速迭代",
            "垂直 agent（编码、客服、销售）开始出现可付费产品",
            "评测与可观测是 2026 年新增的明显热点",
            "记忆/长期存储被视为 agent 的下一个瓶颈",
        ],
        "content": "这张图把 Agent 生态切成四层。最底下是记忆与存储——向量库、KV、图存储；很多人认为这是 agent 走向长期任务的瓶颈。\n\n往上是编排框架层，LangGraph、CrewAI、AutoGen 等仍在快速迭代，API 还没有收敛。\n\n再往上是垂直 agent，编码助手最成熟，客服与销售 agent 开始出现真正能付费的产品。\n\n最上面新长出来的一层是评测与可观测——agent 行为难以复现，没有评测就无法迭代。",
    },
    {
        "slug": "n5", "source_type": "docx",
        "title": "Elasticsearch 中文分词 ik 插件实践",
        "source": "es-notes.docx", "date": "2026-03-18",
        "tags": ["Elasticsearch", "搜索", "中文分词"],
        "summary": "记录 ik 分词器在中文全文检索里的配置：ik_max_word 建索引、ik_smart 查询，自定义词典处理专有名词，并与 pgvector 语义检索做混合排序。",
        "keypoints": [
            "建索引用 ik_max_word（细粒度），查询用 ik_smart（粗粒度）",
            "专有名词（公司名、技术名）需要进自定义词典",
            "停用词表对中文检索质量影响明显",
            "与语义检索混排时用 RRF 融合两路结果",
        ],
        "content": "Elasticsearch 处理中文，绕不开分词。默认的 standard 分词器会把每个汉字单独切开，检索质量很差。\n\nik 插件提供两种模式：ik_max_word 切得最细，适合建索引；ik_smart 切得粗，适合查询输入。一般建索引用前者、查询用后者。\n\n专有名词是重灾区，比如「pgvector」「知识图谱」，必须进自定义词典，否则会被拆碎。\n\n最终我们用 RRF（Reciprocal Rank Fusion）把 ES 的关键词结果和 pgvector 的语义结果融合，效果优于任一单路。",
    },
    {
        "slug": "n6", "source_type": "url",
        "title": "语义检索 vs 关键词检索：什么时候用哪个",
        "source": "pinecone.io/learn", "date": "2026-05-28",
        "tags": ["检索", "语义搜索", "Embedding"],
        "summary": "关键词检索精确但脆弱，语义检索鲁棒但可能漂移。实践中两者互补：用 RRF 或加权融合做混合检索，往往比单路提升 15–25% 的召回。",
        "keypoints": [
            "关键词检索擅长精确匹配、专有名词、代码片段",
            "语义检索擅长同义、改写、跨语言",
            "两者的失败模式不同，因此适合融合",
            "混合检索（hybrid）通常比单路召回高 15–25%",
        ],
        "content": "关键词检索（BM25 一类）的优点是精确：你搜「pgvector」，它只会返回真的包含这个词的文档。缺点是脆弱，换个说法就召回不到。\n\n语义检索基于 embedding，能理解同义与改写，「向量数据库」也能匹配到「vector store」。但它有时会漂移，返回主题相关却答非所问的内容。\n\n关键在于：两者的失败模式不同。关键词漏掉的，语义常能补上；语义漂移的，关键词能锚定。\n\n所以实践里很少二选一，而是做 hybrid：两路各自检索，再用 RRF 或加权分数融合。混合检索通常比单路高 15–25% 的召回。",
    },
]

# 实体（name, type）
ENTITIES = [
    ("RAG", "concept"), ("Embedding", "concept"), ("Agent", "concept"),
    ("Claude", "product"), ("pgvector", "product"), ("PostgreSQL", "product"),
    ("Elasticsearch", "product"), ("Anthropic", "company"), ("OpenAI", "company"),
]

# 实体 -> 提及它的笔记 slug
ENTITY_NOTES = {
    "RAG": ["n2", "n6", "n4", "n1"], "Embedding": ["n2", "n6"], "Agent": ["n4"],
    "Claude": ["n1"], "pgvector": ["n3"], "PostgreSQL": ["n3"],
    "Elasticsearch": ["n5"], "Anthropic": ["n1"], "OpenAI": ["n4"],
}

# Wiki 主题页（cites / note 用 slug，灌库时映射成真实 note uuid）
WIKI = {
    "slug": "rag",
    "title": "检索增强生成（RAG）",
    "date": "2026-06-20",
    "source_slugs": ["n2", "n6", "n3", "n5", "n1"],
    "sections": [
        {"heading": "什么是 RAG", "paragraphs": [
            {"text": "检索增强生成把外部知识库的检索结果作为上下文喂给大模型，让回答有据可依、可溯源，而不依赖模型参数里的记忆。", "cites": ["n6"]},
        ]},
        {"heading": "分块与索引", "paragraphs": [
            {"text": "入库阶段需要把长文档切分成 chunk 再做向量化。分块策略直接影响召回——递归字符切分是稳健的默认，语义切分召回最优但成本高 3–5 倍。", "cites": ["n2"]},
            {"text": "向量索引层面，pgvector 的 HNSW 在召回-延迟曲线上优于 IVFFlat，亿级规模需重点调 ef_search 与 maintenance_work_mem。", "cites": ["n3"]},
        ]},
        {"heading": "检索：关键词 vs 语义 vs 混合", "paragraphs": [
            {"text": "关键词检索精确但脆弱，语义检索鲁棒但可能漂移。两者失败模式互补，因此实践中用 RRF 融合做 hybrid 检索，中文场景还需 ik 分词配合。", "cites": ["n6", "n5"]},
        ]},
    ],
    "conflict": {
        "topic": "长上下文是否会取代 RAG？",
        "sides": [
            {"note": "n1", "claim": "Claude Opus 4.8 的 1M 上下文窗口让「单文档问答无需 chunking」，对 RAG 是值得重新评估的信号。"},
            {"note": "n6", "claim": "对大规模、动态更新的语料，检索仍不可替代——长上下文解决不了「从百万文档里找到对的那几段」。"},
        ],
    },
}


def main() -> None:
    titles = [n["title"] for n in NOTES]
    with pool.connection() as conn:
        # 幂等：先删同名旧笔记（级联删 note_entities）
        conn.execute("DELETE FROM notes WHERE title = ANY(%s)", (titles,))

        slug_to_id: dict[str, uuid.UUID] = {}
        for n in NOTES:
            nid = uuid.uuid4()
            slug_to_id[n["slug"]] = nid
            conn.execute(
                """
                INSERT INTO notes (id, title, source, source_type, published_date,
                                   summary, key_points, content, tags, ingest_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'done')
                """,
                (nid, n["title"], n["source"], n["source_type"], n["date"],
                 n["summary"], n["keypoints"], n["content"], n["tags"]),
            )

        name_to_id: dict[str, uuid.UUID] = {}
        for name, etype in ENTITIES:
            conn.execute(
                "INSERT INTO entities (name, type) VALUES (%s, %s) ON CONFLICT (name, type) DO NOTHING",
                (name, etype),
            )
            row = conn.execute(
                "SELECT id FROM entities WHERE name = %s AND type = %s", (name, etype)
            ).fetchone()
            name_to_id[name] = row[0]

        for name, slugs in ENTITY_NOTES.items():
            for slug in slugs:
                conn.execute(
                    """
                    INSERT INTO note_entities (note_id, entity_id, mention_count)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (note_id, entity_id) DO NOTHING
                    """,
                    (slug_to_id[slug], name_to_id[name]),
                )

        # ── Wiki 主题页：slug 引用映射成真实 note uuid ──
        def nid(slug: str) -> str:
            return str(slug_to_id[slug])

        sections = [
            {"heading": s["heading"],
             "paragraphs": [{"text": p["text"], "cites": [nid(c) for c in p["cites"]]}
                            for p in s["paragraphs"]]}
            for s in WIKI["sections"]
        ]
        conflict = {
            "topic": WIKI["conflict"]["topic"],
            "sides": [{"note_id": nid(side["note"]), "claim": side["claim"]}
                      for side in WIKI["conflict"]["sides"]],
        }
        source_ids = [slug_to_id[s] for s in WIKI["source_slugs"]]

        conn.execute("DELETE FROM wiki_pages WHERE slug = %s", (WIKI["slug"],))
        conn.execute(
            """
            INSERT INTO wiki_pages (slug, title, content, sections, conflict,
                                    source_note_ids, compiled_at)
            VALUES (%s, %s, '', %s::jsonb, %s::jsonb, %s, %s)
            """,
            (WIKI["slug"], WIKI["title"], json.dumps(sections, ensure_ascii=False),
             json.dumps(conflict, ensure_ascii=False), source_ids, WIKI["date"]),
        )

    print(f"✅ 灌入 {len(NOTES)} 篇笔记、{len(ENTITIES)} 个实体、"
          f"{sum(len(v) for v in ENTITY_NOTES.values())} 条笔记-实体关联、1 个 Wiki 主题页")


if __name__ == "__main__":
    sys.exit(main())
