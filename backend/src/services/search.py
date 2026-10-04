#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : search.py
@Time    : 2026/9/24 15:20
@Author  : MaoJian Y
@Desc    : 搜索源适配器：统一输出 SourceDocument，全部为异步契约。
"""
import asyncio
import os, httpx
import re
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit

from ddgs import DDGS
from ddgs.exceptions import DDGSException

from backend.src.research.schemas import SourceDocument
from backend.src.utils.logger import get_logger


logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# 通用质量闸门
# --------------------------------------------------------------------------- #
# 正文短于该阈值多半是导航页 / 聚合页 / 软文占位，直接丢弃
_MIN_BODY_CHARS = 60

# 常见追踪参数，归一化 URL 时剔除，让跨源重复更易被识别
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "yclid", "ref", "ref_src", "spm", "from", "source",
}


def _norm_url(url: str) -> str:
    """去掉追踪参数、fragment 与末尾斜杠，便于跨源去重。"""
    url = str(url)
    if not url:
        return ""
    try:
        p = urlsplit(url)
    except ValueError:
        return url
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if k.lower() not in _TRACKING_PARAMS]
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, urlencode(q), ""))


def _clean(text: str | None) -> str:
    """收敛空白：避免多段摘要 / 高亮拼出大片换行噪声。"""
    return re.sub(r"\s+", " ", text or "").strip()


def _prepare(docs: list[SourceDocument], source: str, query: str) -> list[SourceDocument]:
    """统一去重 + 质量过滤，并打印前后条数便于调阈值。"""
    kept: list[SourceDocument] = []
    seen: set[str] = set()
    for d in docs:
        raw_url = str(d.url) if d.url else ""
        if not raw_url:
            continue
        key = _norm_url(raw_url)
        if not key or key in seen:
            continue
        if len(_clean(d.content)) < _MIN_BODY_CHARS:
            continue
        seen.add(key)
        kept.append(d)

    if len(kept) != len(docs):
        logger.info(f"{source}: 【{query}】 原始 {len(docs)} 条，质量过滤后 {len(kept)} 条")
    else:
        logger.info(f"{source}: 【{query}】 返回 {len(kept)} 条结果")
    return kept


async def _raise_api_error(resp: httpx.Response) -> None:
    """非 2xx 时抛出带响应体的异常，便于定位 422/403 的具体原因。"""
    if resp.is_error:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")


# --------------------------------------------------------------------------- #
# 各搜索源
# --------------------------------------------------------------------------- #
async def duckduckgo_search(query: str, max_results: int = 5) -> list[SourceDocument]:
    """同步库用 asyncio.to_thread 桥接，避免阻塞事件循环。"""
    def _sync() -> list[SourceDocument]:
        try:
            results = DDGS(timeout=15).text(
                query,
                max_results=max_results,
                backend="auto",          # 轮询可用后端
                safesearch="moderate",   # 减少低质内容混入
            )
        except DDGSException as e:
            # ddgs 对"无结果"和后端故障都抛异常，多源架构下降级为空列表
            logger.warning(f"DuckDuckGo: 【{query}】 请求失败 {e}")
            return []

        docs = [
            SourceDocument(
                url=r["href"],
                title=_clean(r.get("title")) or "无标题",
                content=_clean(r.get("body")),
            )
            for r in results
        ]
        return _prepare(docs, "DuckDuckGo", query)

    return await asyncio.to_thread(_sync)


async def tavily_search(query: str, max_results: int = 5) -> list[SourceDocument]:
    """原生 async HTTP 客户端可直接 await（httpx 已在依赖中）。"""
    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": os.environ["TAVILY_API_KEY"],
                "query": query,
                "max_results": max_results,
                # 质量优先：advanced 深度检索 + 直回 markdown 正文，避免只有 snippet
                "search_depth": "advanced",
                "include_answer": False,
                "include_raw_content": "markdown",
                "topic": "general",
            },
        )
        await _raise_api_error(resp)

        items = resp.json().get("results", []) or []
        # Tavily 每条带相关性 score，先排序再落成文档，最高分排前面
        items.sort(key=lambda x: x.get("score") or 0.0, reverse=True)

        docs = [
            SourceDocument(
                url=item.get("url", ""),
                title=_clean(item.get("title")) or "无标题",
                content=_clean(item.get("raw_content") or item.get("content")),
            )
            for item in items
        ]
        return _prepare(docs, "Tavily", query)


async def parallel_search(query: str, max_results: int = 5) -> list[SourceDocument]:
    """Parallel Search API：面向 Agent 的自然语言搜索，返回 LLM 优化摘要。"""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.parallel.ai/v1/search",
            headers={"x-api-key": os.environ["PARALLEL_API_KEY"]},
            json={
                "objective": query,
                "search_queries": [query],  # 必填：至少 1 条关键词查询
                # 质量优先：advanced ~3s，召回与摘要质量最高（fast/turbo 更快但更浅）
                "mode": "advanced",
                "advanced_settings": {
                    "max_results": max_results,
                    "excerpt_settings": {"max_chars_per_result": 4000},
                },
            },
        )
        await _raise_api_error(resp)

        items = resp.json().get("results", []) or []
        docs = [
            SourceDocument(
                url=item.get("url", ""),
                title=_clean(item.get("title")) or "无标题",
                published_at=item.get("publish_date"),
                content=_clean("\n".join(item.get("excerpts") or [])),
            )
            for item in items
        ]
        return _prepare(docs, "Parallel", query)


async def youcom_search(query: str, max_results: int = 5) -> list[SourceDocument]:
    """you.com Search API：POST /v1/search，返回 results.web/news 结构。"""
    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.post(
            "https://ydc-index.io/v1/search",
            headers={"x-api-key": os.environ["YDC_API_KEY"]},
            json={
                "query": query,
                "count": max_results,
                # 质量优先：让 You.com 抓取原始页面，拿到正文而非只有 snippet
                "livecrawl": "web",
                "safesearch": "moderate",
            },
        )
        await _raise_api_error(resp)

        data = resp.json().get("results") or {}
        entries = list(data.get("web") or []) + list(data.get("news") or [])

        docs = [
            SourceDocument(
                url=item.get("url", ""),
                title=_clean(item.get("title")) or "无标题",
                published_at=item.get("page_age"),
                content=_clean(
                    "\n".join(item.get("snippets") or [])
                    or item.get("description")
                ),
            )
            for item in entries
        ]
        return _prepare(docs, "You.com", query)


async def exa_search(query: str, max_results: int = 5) -> list[SourceDocument]:
    """Exa Search API：语义搜索，支持论文/新闻分类与正文内联回取。"""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": os.environ["EXA_API_KEY"]},
            json={
                "query": query,
                "numResults": max_results,
                # 质量优先：deep-lite 在延迟与召回质量间取平衡（auto 偏浅）
                "type": "deep-lite",
                "contents": {
                    "text": {"maxCharacters": 4000},
                    "highlights": {"query": query, "numSentences": 5},
                },
            },
        )
        await _raise_api_error(resp)

        items = resp.json().get("results", []) or []
        docs = [
            SourceDocument(
                url=item.get("url", ""),
                title=_clean(item.get("title")) or "无标题",
                publisher=item.get("author"),
                published_at=item.get("publishedDate"),
                content=_clean(
                    item.get("text") or "\n".join(item.get("highlights") or [])
                ),
            )
            for item in items
        ]
        return _prepare(docs, "Exa", query)


if __name__ == '__main__':
    import dotenv
    from rich import print
    dotenv.load_dotenv()
    async def _demo() -> None:
        # 单源调用：直接 await 协程即可
        single = await duckduckgo_search("大模型未来3年发展前景")
        print(f"单源返回 {len(single)} 条：")
        for doc in single:
            print(f"  [{doc.source_type}] {doc.title} -> {doc.url}")

        # 多源并发：gather 扇出；return_exceptions 让单源失败不中断
        # results = await asyncio.gather(
        #     duckduckgo_search("大模型 技术进展 2026 综述"),
        #     tavily_search("大模型 技术进展 2026 综述"),
        #     parallel_search("大模型 技术进展 2026 综述"),
        #     youcom_search("大模型 技术进展 2026 综述"),
        #     exa_search("大模型 技术进展 2026 综述"),
        #     return_exceptions=True,
        # )
        # for search_fn, result in zip((duckduckgo_search, tavily_search,parallel_search, youcom_search, exa_search,), results): #
        #     print(f"{search_fn.__name__}")
        #     print(f"{result[-1] if result else 'No result'}")


    asyncio.run(_demo())
