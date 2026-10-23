#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : context_budget.py
@Time    : 2026/9/26 13:17
@Author  : MaoJian Y
@Desc    : 模型上下文预算工具。

设计原则：原始全文只保存在应用层状态（ResearchRun）中，禁止直接进入提示词；
所有进入模型的数据都必须经过紧凑视图截断与预算装箱，防止单次调用超出模型上下文窗口。
"""
from typing import TypeVar, Iterable
from collections.abc import Callable, Sequence
from backend.src.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# ---- 紧凑视图截断长度（字符）----
DIGEST_CLAIM_CHARS = 200
DIGEST_EXCERPT_CHARS = 400
DIGEST_STATEMENT_CHARS = 300
DIGEST_CAVEAT_CHARS = 120
DIGEST_LIMITATION_CHARS = 120
DIGEST_MAX_CAVEATS = 5
DIGEST_MAX_LIMITATIONS = 4

# ---- 各 Agent 单次调用的输入 token 预算（模型上限 1048576，取保守值）----
CRITIC_INPUT_BUDGET_TOKENS = 150_000
WRITER_INPUT_BUDGET_TOKENS = 150_000
PLANNER_SUPPLEMENT_INPUT_BUDGET_TOKENS = 80_000
FOLLOW_UP_INPUT_BUDGET_TOKENS = 40_000
FOLLOW_UP_MAX_COMPLETE_TURNS = 20

# ---- 综合与分章写作预算 ----
SYNTHESIZER_INPUT_BUDGET_TOKENS = 40_000
WRITER_SECTION_INPUT_BUDGET_TOKENS = 60_000

_DENSE_TOKEN_RANGES = (
    ("\u0900", "\u097f"),  # Devanagari
    ("\u0e00", "\u0e7f"),  # Thai
    ("\u3040", "\u30ff"),  # Japanese kana
    ("\u3400", "\u9fff"),  # Han
    ("\uac00", "\ud7af"),  # Hangul
)


def estimate_tokens(text: str) -> int:
    """Conservative multilingual token estimate without a model-specific tokenizer."""
    if not text:
        return 0
    dense = sum(
        1 for ch in text
        if any(lo <= ch <= hi for lo, hi in _DENSE_TOKEN_RANGES)
    )
    return dense + (len(text) - dense + 3) // 4


def truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    text = text or ""
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "…"


def log_payload_size(agent: str, payload: str) -> None:
    """记录进入模型的载荷规模，便于观测上下文增长趋势。"""
    logger.info("%s 输入载荷：%d 字符 ≈ %d tokens", agent, len(payload), estimate_tokens(payload))


def round_robin_by_task(items: Sequence[T], key: Callable[[T], str]) -> list[T]:
    """按 task 分组轮流取样；预算裁剪时保证每个任务仍有代表性条目。"""
    buckets: dict[str, list[T]] = {}
    for item in items:
        buckets.setdefault(key(item), []).append(item)
    ordered: list[T] = []
    while any(buckets.values()):
        for task_id in list(buckets):
            if buckets[task_id]:
                ordered.append(buckets[task_id].pop(0))
    return ordered


def take_within_budget(items: Sequence[T], budget_tokens: int, render: Callable[[T], str]) -> list[T]:
    """贪心装箱：依序保留 token 估算仍在预算内的项，超出的丢弃并记录可观测日志。"""
    selected: list[T] = []
    used = 0
    for item in items:
        cost = estimate_tokens(render(item)) + 1
        if used + cost <= budget_tokens:
            selected.append(item)
            used += cost
    if len(selected) < len(items):
        logger.warning("上下文预算裁剪：保留 %d/%d 项（预算 %d tokens）", len(selected), len(items), budget_tokens)
    return selected
