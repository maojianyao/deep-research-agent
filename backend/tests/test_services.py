"""Smoke tests for search adapters, LLM service, configuration, and logging."""

from __future__ import annotations

import logging
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

from backend.src.config import Configuration, SearchAPI, get_config
from backend.src.services import llm as llm_module
from backend.src.services.search import _clean, _norm_url, _prepare, _raise_api_error
from backend.src.utils.logger import DailyFileHandler, LogManager
from backend.src.utils.logger import get_logger as get_cached_logger
from backend.tests.factories import make_source, make_task


class SearchUtilityTests(unittest.TestCase):
    def test_norm_url_removes_tracking_fragment_and_trailing_slash(self):
        original = "HTTPS://Example.COM/path/?utm_source=x&q=1&fragment=ignored#section"
        normalized = _norm_url(original)
        self.assertEqual(normalized, "https://example.com/path?q=1&fragment=ignored")

    def test_norm_url_handles_empty_value(self):
        self.assertEqual(_norm_url(""), "")

    def test_clean_collapses_whitespace(self):
        self.assertEqual(_clean("  a\n\nb\tc  "), "a b c")
        self.assertEqual(_clean(None), "")

    def test_prepare_filters_short_and_duplicate_documents(self):
        good = make_source(url="https://example.com/a", content="x" * 80)
        duplicate = make_source(url="https://example.com/a/", content="x" * 80)
        short = make_source(url="https://example.com/short", content="short")

        result = _prepare([good, duplicate, short], "test-source", "query")

        self.assertEqual(result, [good])


class SearchHttpErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_raise_api_error_passes_success_response(self):
        response = httpx.Response(200, text="ok")
        await _raise_api_error(response)

    async def test_raise_api_error_includes_response_body(self):
        response = httpx.Response(500, text="upstream failure")
        with self.assertRaises(RuntimeError) as raised:
            await _raise_api_error(response)

        self.assertIn("HTTP 500", str(raised.exception))
        self.assertIn("upstream failure", str(raised.exception))


class LLMServiceTests(unittest.TestCase):
    def test_with_structured_output_defaults_to_function_calling(self):
        model = llm_module.CompatibleChatOpenAI(api_key="test-key", model="test-model")
        schema = SimpleNamespace()

        with patch.object(llm_module.ChatOpenAI, "with_structured_output",
                          MagicMock(return_value="bound-runnable")) as parent_method:
            result = model.with_structured_output(schema, foo="bar")

        self.assertEqual(result, "bound-runnable")
        parent_method.assert_called_once_with(schema, foo="bar", method="function_calling")

    def test_get_llm_caches_instance_until_reset(self):
        original_instance = llm_module._llm_instance
        config = SimpleNamespace(
            llm_api_key="key", llm_base_url="https://example.com/v1",
            llm_model="model", use_tool_calling=True,
        )
        first = MagicMock()

        try:
            llm_module.reset_llm()
            with patch.object(llm_module, "get_config", MagicMock(return_value=config)), \
                    patch.object(llm_module, "CompatibleChatOpenAI", MagicMock(return_value=first)):
                self.assertIs(llm_module.get_llm(), first)
                self.assertIs(llm_module.get_llm(), first)

            llm_module.reset_llm()
            self.assertIsNone(llm_module._llm_instance)
        finally:
            llm_module._llm_instance = original_instance


class ConfigurationTests(unittest.TestCase):
    def make_config(self):
        env = {
            "LLM_API_KEY": "test-key",
            "LLM_BASE_URL": "https://api.example.com/v1",
            "LLM_MODEL": "test-model",
            "SEARCH_API": "tavily",
            "MAX_WEB_RESEARCH_LOOPS": "5",
            "FETCH_FULL_PAGE": "false",
            "USE_TOOL_CALLING": "false",
        }
        with patch.dict(os.environ, env, clear=True):
            return Configuration.from_env()

    def test_from_env_loads_and_coerces_values(self):
        config = self.make_config()
        self.assertEqual(config.llm_api_key, "test-key")
        self.assertEqual(config.llm_base_url, "https://api.example.com/v1")
        self.assertEqual(config.llm_model, "test-model")
        self.assertEqual(config.search_api, SearchAPI.TAVILY)
        self.assertEqual(config.max_web_research_loops, 5)
        self.assertFalse(config.fetch_full_page)
        self.assertFalse(config.use_tool_calling)

    def test_tool_calling_defaults_to_enabled(self):
        env = {
            "LLM_API_KEY": "test-key",
            "LLM_BASE_URL": "https://api.example.com/v1",
            "LLM_MODEL": "test-model",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertTrue(Configuration.from_env().use_tool_calling)

    def test_sanitized_ollama_url_appends_v1(self):
        config = self.make_config()
        config.ollama_base_url = "http://localhost:11434"
        self.assertEqual(config.sanitized_ollama_url(), "http://localhost:11434/v1")

    def test_resolved_model_prefers_llm_model(self):
        config = self.make_config()
        self.assertEqual(config.resolved_model(), "test-model")

        config.llm_model = ""
        self.assertEqual(config.resolved_model(), config.local_llm)

    def test_get_config_caches_constructed_configuration(self):
        import backend.src.config as config_module

        sentinel = object()
        original = config_module._config
        try:
            config_module._config = None
            with patch.object(Configuration, "from_env", MagicMock(return_value=sentinel)) as from_env:
                self.assertIs(get_config(), sentinel)
                self.assertIs(get_config(), sentinel)
                from_env.assert_called_once_with()
        finally:
            config_module._config = original


class LoggerTests(unittest.TestCase):
    def make_record(self, message: str) -> logging.LogRecord:
        return logging.LogRecord(
            name="smoke-test", level=logging.INFO, pathname=__file__,
            lineno=1, msg=message, args=None, exc_info=None,
        )

    def test_daily_file_handler_writes_formatted_record(self):
        with tempfile.TemporaryDirectory() as directory:
            handler = DailyFileHandler(directory)
            handler.setFormatter(logging.Formatter("%(message)s"))
            handler.emit(self.make_record("hello logger"))
            handler.close()

            files = list(Path(directory).glob("*.log"))
            self.assertEqual(len(files), 1)
            self.assertIn("hello logger", files[0].read_text(encoding="utf-8"))

    def test_daily_file_handler_cleans_expired_files(self):
        with tempfile.TemporaryDirectory() as directory:
            expired = Path(directory) / "2020-01-01.log"
            expired.write_text("expired", encoding="utf-8")
            handler = DailyFileHandler(directory, retention_days=2)
            handler.close()

            self.assertFalse(expired.exists())
            self.assertTrue(any(Path(directory).glob("*.log")))

    def test_log_manager_caches_logger_by_name(self):
        with tempfile.TemporaryDirectory() as directory:
            name = f"smoke-{os.getpid()}-{id(self)}"
            logger = LogManager.get_logger(name, log_dir=directory)
            same_logger = LogManager.get_logger(name, log_dir=directory)

            self.assertIs(logger, same_logger)
            self.assertFalse(logger.propagate)

    def test_module_get_logger_uses_single_cached_instance(self):
        import backend.src.utils.logger as logger_module

        original = logger_module._logger
        sentinel = object()
        try:
            logger_module._logger = None
            with patch.object(logger_module.LogManager, "get_logger",
                              MagicMock(return_value=sentinel)):
                self.assertIs(get_cached_logger("test"), sentinel)
                self.assertIs(get_cached_logger("test"), sentinel)
        finally:
            logger_module._logger = original


if __name__ == "__main__":
    unittest.main()
