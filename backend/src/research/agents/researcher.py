"""Researcher Agent：检索原始资料并提取候选证据。"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Awaitable
from functools import partial
from urllib.parse import urlsplit

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.chat_models import BaseChatModel

from backend.src.research.agents.base import Search, _ainvoke, repair_tool_messages
from backend.src.research.context_budget import truncate_text
from backend.src.research.prompts import dynamic_prompt, RoleContext
from backend.src.research.schemas import (
    CandidateEvidence, CandidateEvidenceBatchDraft, ResearchTask, RoleAgent, SourceDocument,
)
from backend.src.utils.documents import document_keys
from backend.src.utils.logger import get_logger


logger = get_logger(__name__)


class ResearcherAgent:
    """检索原始资料并提取候选证据，不对其可信度作最终裁定。"""
    _QUERY_BATCH_SIZE = 2  # 单次结构化调用承载的查询数：输入规模 = 批内查询 × 命中文档数
    _MAX_DOC_CHARS = 2000  # 单文档进入提示词的最大字符数（中文 1 字 ≈ 1 token，2000 字窗口足够证据摘录）
    _MAX_DOCS_PER_CALL = 12  # 单次结构化调用的文档数上限：文档数 × 文档窗口共同决定输入规模
    _MAX_DOCS_PER_DOMAIN = 2  # 单域名入选上限，防止单一站点垄断提示词
    _MIN_CONTENT_CHARS = 50  # 正文最短字符数，过滤无实质内容的占位文档
    _MAX_EXCERPT_CHARS = 600  # 候选证据摘录窗口；原始文档全文仍由应用层持有
    _MAX_CANDIDATES_PER_URL = 2  # 单 URL 候选上限，防止单一来源刷屏
    _MAX_CANDIDATES = 12  # 单批返回候选上限
    _ROLE = RoleContext(user_role=RoleAgent.RESEARCHER)

    def __init__(self, model: BaseChatModel, searches: list[Search], max_concurrent_searches: int = 4):
        self.agent = create_agent(model,
                                  tools=[],
                                  middleware=[dynamic_prompt, repair_tool_messages],
                                  response_format=ToolStrategy(CandidateEvidenceBatchDraft),
                                  )
        self.searches = searches
        self._semaphore = asyncio.Semaphore(max_concurrent_searches)
        self._seen_documents: set[str] = set()

    async def _bounded(self, factory: Callable[[], Awaitable]):
        """用信号量限制对外部服务（搜索源/LLM）的并发数"""
        async with self._semaphore:
            return await factory()

    async def _search_all(self, query: str) -> list[list[SourceDocument]]:
        """单个查询在全部搜索源上扇出；保留来源边界供交错采样，单源失败降级为空结果"""
        results = await asyncio.gather(
            *[self._bounded(partial(search, query)) for search in self.searches],
            return_exceptions=True,
        )
        return [[doc for doc in result if self._is_new_document(doc)]
                for result in results if isinstance(result, list)]

    def _is_new_document(self, doc: SourceDocument) -> bool:
        """Deduplicate documents across queries, tasks, and supplement rounds."""
        keys = {key for key in document_keys(str(doc.url), doc.title) if key}
        if keys & self._seen_documents:
            return False
        self._seen_documents.update(keys)
        return True

    async def _extract(self, task: ResearchTask, queries: list[str]) -> list[CandidateEvidence]:
        """对一批查询执行检索与结构化提取，单次调用的输入输出规模可控。"""
        per_query = await asyncio.gather(*(self._search_all(query) for query in queries))
        documents: dict[str, SourceDocument] = {}
        for source_lists in per_query:
            for docs in source_lists:
                for doc in docs:
                    documents.setdefault(str(doc.url), doc)
        if not documents:
            return []
        prompt_documents = self._select_documents(per_query, task)
        domains = {urlsplit(str(item.url)).netloc for item in prompt_documents}
        logger.info("文档筛选：%d 篇去重候选 → 入选 %d 篇，覆盖 %d 个域名",
                    len(documents), len(prompt_documents), len(domains))
        try:
            batch = await self._bounded(partial(_ainvoke, self.agent, self._ROLE, json.dumps({
                "task": task.model_dump(),
                "documents": [
                    {**item.model_dump(mode="json"), "content": truncate_text(item.content, self._MAX_DOC_CHARS)}
                    for item in prompt_documents
                ],
            }, ensure_ascii=False)))
        except RuntimeError as e:
            # 上游内容风控（Content Exists Risk）等不可重试错误：该批降级为空结果，不拖垮任务
            logger.error("提取批次被上游拒绝，降级为空结果：%s", e)
            return []
        candidates, unknown_urls = batch.to_candidates(documents)
        for candidate in candidates:
            candidate.task_id = task.id
        if unknown_urls:
            logger.warning("Researcher 回报了 %d 个未知来源 URL，已丢弃：%r", len(unknown_urls), unknown_urls[:3])
        return self._limit_candidates(candidates)

    @staticmethod
    def _keywords(task: ResearchTask) -> set[str]:
        """从任务问题与查询词提取检索词元：英文单词 + 中文 2-gram，用于轻量相关性打分。"""
        text = " ".join([task.question, *task.queries])
        tokens = {word.lower() for word in re.findall(r"[A-Za-z][A-Za-z0-9+#.]{1,}", text)}
        tokens.update(text[i:i + 2] for i in range(len(text) - 1)
                      if "\u4e00" <= text[i] <= "\u9fff" and "\u4e00" <= text[i + 1] <= "\u9fff")
        return tokens

    _SOURCE_TYPE_WEIGHTS: dict[str, int] = {
        "government": 6,
        "primary": 5,
        "academic": 5,
        "peer_reviewed": 5,
        "news_major": 4,
        "corporate": 3,
        "international_org": 5,
    }

    @classmethod
    def _relevance(cls, doc: SourceDocument, tokens: set[str], required_types: list[str] | None = None) -> int:
        """轻量相关性：标题命中权重 3，正文命中权重 1，叠加通用一手/权威来源权重加成。"""
        if not tokens:
            return 0
        title, content = doc.title.lower(), doc.content.lower()
        score = 3 * sum(1 for token in tokens if token in title) + sum(1 for token in tokens if token in content)
        st = getattr(doc, "source_type", "unknown") or "unknown"
        score += cls._SOURCE_TYPE_WEIGHTS.get(st, 0)
        if required_types and st in required_types:
            score += 4
        return score

    @classmethod
    def _select_documents(cls, per_query: list[list[list[SourceDocument]]],
                          task: ResearchTask) -> list[SourceDocument]:
        """文档筛选：(查询, 来源) 组内按相关性排序、组间二维轮转采样，
        叠加 URL 去重、单域名限流、近似标题去重与无效正文过滤，
        避免入选文档集中自同一查询、同一搜索源或同一域名。"""
        tokens = cls._keywords(task)
        cells = [sorted(docs, key=lambda item: -cls._relevance(item, tokens, task.required_source_types))
                 for source_lists in per_query for docs in source_lists]
        selected: list[SourceDocument] = []
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        domain_count: dict[str, int] = {}
        while len(selected) < cls._MAX_DOCS_PER_CALL and any(cells):
            for cell in cells:
                if len(selected) >= cls._MAX_DOCS_PER_CALL:
                    break
                # 内层循环弹出并丢弃被约束排除的文档，直到该单元格选中一篇或耗尽
                while cell and len(selected) < cls._MAX_DOCS_PER_CALL:
                    doc = cell.pop(0)
                    url = document_keys(str(doc.url), doc.title)[0]
                    if url in seen_urls or len(doc.content.strip()) < cls._MIN_CONTENT_CHARS:
                        continue
                    norm_title = "".join(ch for ch in doc.title.lower() if ch.isalnum())
                    if norm_title and norm_title in seen_titles:
                        continue
                    domain = urlsplit(url).netloc.removeprefix("www.").lower() or url
                    if domain_count.get(domain, 0) >= cls._MAX_DOCS_PER_DOMAIN:
                        continue
                    seen_urls.add(url)
                    if norm_title:
                        seen_titles.add(norm_title)
                    domain_count[domain] = domain_count.get(domain, 0) + 1
                    selected.append(doc)
                    break
        return selected

    @classmethod
    def _limit_candidates(cls, candidates: list[CandidateEvidence]) -> list[CandidateEvidence]:
        """按 URL 限流并截断摘录；全文仍保留在应用层，防止候选规模失控。"""
        per_url: dict[str, int] = {}
        limited: list[CandidateEvidence] = []
        for item in candidates:
            url = document_keys(str(item.source.url), item.source.title)[0]
            if per_url.get(url, 0) >= cls._MAX_CANDIDATES_PER_URL:
                continue
            per_url[url] = per_url.get(url, 0) + 1
            item.excerpt = truncate_text(item.excerpt, cls._MAX_EXCERPT_CHARS)
            limited.append(item)
            if len(limited) >= cls._MAX_CANDIDATES:
                break
        return limited

    async def run(self, task: ResearchTask) -> list[CandidateEvidence]:
        """覆盖全部查询：查询分批后各自检索与提取（批间并发），最后按（来源, 主张）去重合并。"""
        queries = task.queries or [task.question]
        batches = [queries[i:i + self._QUERY_BATCH_SIZE] for i in range(0, len(queries), self._QUERY_BATCH_SIZE)]
        results = await asyncio.gather(*(self._extract(task, batch) for batch in batches), return_exceptions=True)
        candidates, seen = [], set()
        for items in results:
            if isinstance(items, BaseException):
                logger.error("任务 %s 提取批次异常，已跳过：%s", task.id, items)
                continue
            for item in items:
                # TODO: 去重逻辑待完善
                url = document_keys(str(item.source.url), item.source.title)[0]
                claim = " ".join(item.claim.lower().split())
                key = (url, claim)
                if key not in seen:
                    seen.add(key)
                    candidates.append(item)
        return candidates
