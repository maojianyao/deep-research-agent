"""Smoke tests for deterministic context budget helpers."""

from __future__ import annotations

import unittest

from backend.src.research.context_budget import (
    estimate_tokens, round_robin_by_task, take_within_budget, truncate_text,
)


class ContextBudgetTests(unittest.TestCase):
    def test_estimate_tokens_empty(self):
        self.assertEqual(estimate_tokens(""), 0)

    def test_estimate_tokens_ascii_and_cjk(self):
        # Four ASCII characters are roughly one token; each CJK character is one token.
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("中文"), 2)
        self.assertEqual(estimate_tokens("abcd中文"), 3)

    def test_truncate_text(self):
        self.assertEqual(truncate_text("abcdef", 10), "abcdef")
        self.assertEqual(truncate_text("abcdef", 3), "abc…")
        self.assertEqual(truncate_text("abc   ", 5), "abc…")
        self.assertEqual(truncate_text("abcdef", 0), "")
        self.assertEqual(truncate_text(None, 3), "")

    def test_round_robin_by_task_interleaves_groups(self):
        items = ["a1", "a2", "b1", "a3", "b2"]
        result = round_robin_by_task(items, key=lambda item: item[0])
        self.assertEqual(result, ["a1", "b1", "a2", "b2", "a3"])

    def test_take_within_budget_keeps_items_in_order(self):
        items = ["aaaa", "bb", "cccc"]
        selected = take_within_budget(items, 5, render=lambda item: item)
        # Costs are 2, 2, and 2; the third exceeds a budget of 5.
        self.assertEqual(selected, ["aaaa", "bb"])

    def test_take_within_budget_accepts_all_when_generous(self):
        items = ["aaaa", "bb", "cccc"]
        selected = take_within_budget(items, 100, render=lambda item: item)
        self.assertEqual(selected, items)


if __name__ == "__main__":
    unittest.main()
