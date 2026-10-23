"""Language normalization, inference, and output quality tests."""

from __future__ import annotations

import unittest

from backend.src.research.language import (
    InvalidLanguageTag, canonicalize_language, detect_language, language_matches,
    language_profile, resolve_report_language,
)


class LanguageContractTests(unittest.TestCase):
    def test_canonicalizes_tags_and_common_names(self):
        self.assertEqual(canonicalize_language("EN_us"), "en-US")
        self.assertEqual(canonicalize_language("zh"), "zh-CN")
        self.assertEqual(canonicalize_language("English"), "en")
        self.assertEqual(canonicalize_language("阿拉伯文"), "ar")

    def test_rejects_malformed_tags(self):
        for value in ("not a language!", "en--US", "@@"):
            with self.subTest(value=value):
                with self.assertRaises(InvalidLanguageTag):
                    canonicalize_language(value)

    def test_profiles_identify_direction_and_quality(self):
        self.assertEqual(language_profile("ar").direction, "rtl")
        self.assertEqual(language_profile("en").quality, "verified")
        self.assertEqual(language_profile("sw").quality, "best_effort")

    def test_infers_request_language_and_falls_back(self):
        self.assertEqual(resolve_report_language("研究新能源汽车政策"), ("zh-CN", "detected"))
        self.assertEqual(resolve_report_language("Investigate renewable energy policy"), ("en", "detected"))
        self.assertEqual(resolve_report_language("12345"), ("zh-CN", "fallback"))
        self.assertEqual(
            resolve_report_language("研究主题", "Japanese"),
            ("ja", "explicit"),
        )

    def test_detects_major_scripts(self):
        self.assertEqual(detect_language("これは日本語のレポートです"), "ja")
        self.assertEqual(detect_language("هذا تقرير بحثي باللغة العربية"), "ar")
        self.assertEqual(detect_language("这是一个中文研究报告"), "zh-CN")

    def test_output_language_gate_catches_mismatches(self):
        self.assertTrue(language_matches("This is an English research report.", "en"))
        self.assertTrue(language_matches("Este es un informe de investigación.", "es"))
        self.assertFalse(language_matches("This is an English research report.", "ja"))
        self.assertTrue(language_matches("123", "ja"))
        self.assertTrue(language_matches("Best effort language content", "sw"))
        self.assertTrue(language_matches(
            "The report evaluates the policy. 原文写道：政策已于今年生效。",
            "en",
        ))


if __name__ == "__main__":
    unittest.main()
