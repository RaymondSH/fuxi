"""Provider 抽象层：定义 LLM / Embedding 的统一接口与共享数据模型。

策略模式的骨架：业务层只依赖这里的抽象接口，具体实现（智谱 GLM 等）在子模块，
由 __init__.py 的工厂按配置选择。换 provider 时只改实现类 + 配置，不改业务代码。

共享契约（与 provider 无关的部分都放这里）：
  - IngestResult / Entity       入库提炼的结构化产物
  - INGEST_SYSTEM / QA_SYSTEM   两个 system 提示词，各 provider 复用
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Literal

from pydantic import BaseModel, Field

# 实体类型枚举：company 公司 / person 人名 / concept 概念 / product 产品 / event 事件 / place 地点
EntityType = Literal["company", "person", "concept", "product", "event", "place"]


class Entity(BaseModel):
    name: str
    type: EntityType
    aliases: list[str] = Field(default_factory=list)


class IngestResult(BaseModel):
    """入库提炼产物：LLM 对一篇正文做摘要+要点+标签+实体后的结构化结果。"""

    title: str = Field(description="文章标题，若正文未给出则据内容拟一个")
    summary: str
    key_points: list[str]
    tags: list[str]
    entities: list[Entity] = Field(default_factory=list)


class WikiParagraph(BaseModel):
    """主题页正文一段：正文 + 引用的来源 note id 列表（角标用）。"""
    text: str
    cites: list[str] = Field(default_factory=list, description="来源 note id 字符串列表")


class WikiSection(BaseModel):
    """主题页一个章节：标题 + 若干段落。"""
    heading: str
    paragraphs: list[WikiParagraph]


class WikiConflictSide(BaseModel):
    """观点矛盾的一方：来源 note id + 该来源的主张。"""
    note_id: str
    claim: str


class WikiConflict(BaseModel):
    """编译时标出的对立判断（多篇来源对同一话题给出冲突结论）。"""
    topic: str
    sides: list[WikiConflictSide] = Field(default_factory=list)


class WikiCompileResult(BaseModel):
    """主题页编译产物：结构化 sections + 冲突 + 概览摘要。"""
    sections: list[WikiSection]
    conflict: WikiConflict | None = None
    summary: str = Field(default="", description="一句话概括本主题页")


class QaGenItem(BaseModel):
    """文档→Q&A 生成的一条产物：一个问题 + 一个回答。"""
    question: str = Field(description="基于该笔记内容拟出的自问")
    answer: str = Field(description="依据笔记内容的自答，2-4 句")


class QaGenResult(BaseModel):
    """文档→Q&A 生成产物：多条问答对。回灌检索后写入 generated_qa。"""
    items: list[QaGenItem] = Field(default_factory=list)


class ConflictAssessment(BaseModel):
    conflict: bool = False
    topic: str = ""
    explanation: str = ""


class QueryPlan(BaseModel):
    queries: list[str] = Field(default_factory=list)


# IngestResult 的 JSON schema 文本，嵌进 system 提示让模型按结构输出
_INGEST_SCHEMA_HINT = """按以下 JSON 结构输出，字段含义：
{
  "title": "文章标题，正文未给出则据内容拟一个",
  "summary": "2-3 句摘要，说清核心内容和作者判断",
  "key_points": ["3-5 条要点，不够就少写，别硬凑"],
  "tags": ["3-5 个标签，从内容里自然提炼，中英文均可"],
  "entities": [
    {"name": "实体名", "type": "company|person|concept|product|event|place", "aliases": ["同一实体的其它叫法"]}
  ]
}"""

# 入库提炼用的 system 提示，对齐 my-wiki 的 CLAUDE.md 规则
INGEST_SYSTEM = f"""你是一个个人知识库的入库助手。给你一篇文章正文，你要：
1. 写 2-3 句摘要，说清楚核心内容和作者判断；
2. 提炼 3-5 条要点，不够就少写，别硬凑；
3. 打 3-5 个标签，从内容里自然提炼，中英文均可；
4. 抽取文中出现的关键实体（公司、人名、概念、产品、事件、地点），
   给出类型；同一实体的不同叫法放进 aliases。
只描述文章里真实出现的内容，不要编造。

{_INGEST_SCHEMA_HINT}"""

# 问答用的 system 提示
QA_SYSTEM = """你是知识库问答助手。只依据用户提供的「来源」回答问题：
- 回答要点明依据，可在句末用 [n] 形式标注来源序号；
- 来源不足以回答时，如实说明，不要编造；
- 用简洁中文，必要处可用 Markdown 加粗 / 列表。"""

# 角色化输出风格：在默认 QA_SYSTEM 之上叠加风格约束，由 build_qa_system(style) 拼接。
# 保持默认的事实约束（只依据来源、不编造），只改表达风格。
QaStyle = Literal["default", "executive", "technical", "eli5"]

_QA_STYLE_HINTS: dict[str, str] = {
    "executive": (
        "\n\n【输出风格：高管简报】面向决策者，先给一句话结论，再给 2-3 条要点；"
        "省略技术细节与实现过程；用商业语言，强调影响与取舍。"
    ),
    "technical": (
        "\n\n【输出风格：技术说明】面向工程师，给出原理、机制与关键参数；"
        "可使用专业术语，必要时分步骤说明；结论可后置。"
    ),
    "eli5": (
        "\n\n【输出风格：通俗讲解】面向非专业读者，用日常类比解释，"
        "避免术语；句子要短，能不用的专有名词就不用。"
    ),
}


def build_qa_system(style: QaStyle = "default") -> str:
    """按输出风格拼问答 system 提示：默认事实约束 + 风格叠加。"""
    return QA_SYSTEM + _QA_STYLE_HINTS.get(style, "")

# 主题页编译用的 system 提示
_WIKI_SCHEMA_HINT = """按以下 JSON 结构输出：
{
  "summary": "一句话概括本主题页",
  "sections": [
    {
      "heading": "章节标题",
      "paragraphs": [
        {"text": "该段正文，综合多篇来源写成", "cites": ["来源note_id", "..."]}
      ]
    }
  ],
  "conflict": {"topic": "冲突话题", "sides": [{"note_id": "来源id", "claim": "该来源的主张"}]}
}
若各来源无明显冲突，conflict 设为 null。"""

WIKI_COMPILE_SYSTEM = f"""你是知识库的主题页编辑。给你多篇笔记（含 id/标题/摘要/正文节选），
请你把它们综合成一篇结构化主题页：

1. 按 3-6 个章节组织正文，每章一个 heading；
2. 每章下若干段落，每段正文综合多篇来源写成，并在 cites 里列出该段引用到的来源 note id；
3. 梳理出各来源之间的对立判断（如对同一问题给出冲突结论），填进 conflict；
   若无冲突则 conflict 为 null；
4. 概览摘要一句话；
5. 只综合来源里的真实内容，不要编造来源中未出现的信息。

{_WIKI_SCHEMA_HINT}"""


# 文档→Q&A 生成用的 system 提示
_QA_GEN_SCHEMA_HINT = """按以下 JSON 结构输出：
{
  "items": [
    {"question": "针对该笔记内容的自问", "answer": "依据笔记内容的自答，2-4 句"}
  ]
}"""

QA_GEN_SYSTEM = f"""你是知识库的问答标注员。给你一篇笔记的正文，请你站在「未来读者可能想问」的角度，
生成 3-5 个高质量的问答对，用于沉淀进检索库、在被问到同义问题时直接回灌复用：

1. 问题要具体、能从该笔记内容里找到明确答案（避免泛泛而谈）；
2. 回答严格依据笔记内容，2-4 句，不要编造笔记里没有的信息；
3. 覆盖该笔记的主要要点，角度互补，不要重复；
4. 用简洁中文。

{_QA_GEN_SCHEMA_HINT}"""


class LLMProvider(ABC):
    """LLM 提供者抽象：入库提炼 / 问答 / 图片描述三类调用。

    子类实现具体 provider（如智谱 GLM）。门面层 services/llm.py 委托此处。
    """

    @abstractmethod
    def analyze(self, content: str, *, title_hint: str = "") -> IngestResult:
        """对一篇正文做摘要+要点+标签+实体提取，返回结构化结果。"""

    @abstractmethod
    def answer(self, question: str, context: str, history: list[dict] | None = None,
               *, style: QaStyle = "default") -> str:
        """基于检索到的来源（context）生成带依据的回答。history 为多轮上下文。

        style 控制输出风格（default/executive/technical/eli5）。
        """

    def answer_stream(
        self, question: str, context: str, history: list[dict] | None = None,
        *, style: QaStyle = "default",
    ) -> AsyncIterator[str]:
        """流式问答：逐块 yield 生成内容（token 级）。默认抛 NotImplementedError，
        子类按需实现；未实现的 provider 调用方回退到非流式 answer。"""
        raise NotImplementedError("当前 provider 未实现流式回答")
        # 让类型检查认为这是 async generator（raise 之上的 yield 永不执行）
        yield ""  # pragma: no cover

    @abstractmethod
    def describe_image(self, image_b64: str, media_type: str) -> str:
        """让模型描述一张图片，输出可入库的文字内容。"""

    def compile_wiki(self, sources: list[dict], topic: str) -> WikiCompileResult:
        """主题页编译：把多篇笔记综合成结构化 sections + 冲突标记。

        sources 形如 [{"id","title","summary","content"}, ...]，已按相关度排好序。
        默认抛 NotImplementedError，子类按需实现。
        """
        raise NotImplementedError("当前 provider 未实现主题页编译")

    def generate_qa(self, content: str, *, title_hint: str = "") -> QaGenResult:
        """文档→Q&A 生成：基于一篇笔记正文拟若干问答对，回灌进检索库。

        默认抛 NotImplementedError，子类按需实现。
        """
        raise NotImplementedError("当前 provider 未实现 Q&A 生成")

    def detect_conflict(self, left: str, right: str) -> ConflictAssessment:
        """判断两段知识是否对同一事实给出冲突结论。"""
        raise NotImplementedError("当前 provider 未实现冲突检测")

    def plan_queries(self, question: str) -> QueryPlan:
        """把复杂问题拆成有限个可检索子问题。"""
        raise NotImplementedError("当前 provider 未实现问题拆解")


class EmbeddingProvider(ABC):
    """Embedding 提供者抽象：把文本转成定长向量。"""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """把一段文本转成定长向量。维度须与 SQL 的 vector(N) 一致。"""
