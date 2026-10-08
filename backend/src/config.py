#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : config.py
@Time    : 2026/9/23 14:45
@Author  : MaoJian Y
@Desc    : 配置文件
"""
import os
from enum import Enum
from typing import Optional, Any

from pydantic import BaseModel, Field
import dotenv


dotenv.load_dotenv(override=True)


class SearchAPI(Enum):
    PERPLEXITY = "perplexity"
    TAVILY = "tavily"
    DUCKDUCKGO = "duckduckgo"
    SEARXNG = "searxng"
    ADVANCED = "advanced"


class Configuration(BaseModel):
    """为深度研究助手配置选项"""

    max_web_research_loops: int = Field(default=3, title="搜索深度", description="执行迭代搜索次数")
    local_llm: str = Field(default="gemma4:e4b", title="本地大模型", description="本地ollama/LMStudio大模型名称")
    llm_provider: str = Field(default="ollama", title="大模型提供商", description="大模型提供者，支持ollama和lmstudio or custom")
    search_api: SearchAPI = Field(default=SearchAPI.DUCKDUCKGO, title="搜索API", description="搜索API，支持perplexity, tavily, duckduckgo, searxng, advanced")
    fetch_full_page: bool = Field(default=True, title="是否获取完整页面", description="是否获取完整页面内容")
    ollama_base_url: str = Field(default="http://localhost:11434", title="Ollama服务URL", description="Ollama服务基础URL")
    lmstudio_base_url: str = Field(default="http://localhost:1234/v1", title="LMStudio服务URL", description="LMStudio服务基础URL")
    use_tool_calling: bool = Field(
        default=True,
        title="是否使用工具调用",
        description="结构化输出优先使用工具调用；兼容性较差的模型可关闭并使用 JSON Schema。",
    )
    llm_api_key: str = Field(
        ...,
        title="LLM API Key",
        description="Optional API key when using custom OpenAI-compatible services",
    )
    llm_base_url: str = Field(
        ...,
        title="LLM Base URL",
        description="Optional base URL when using custom OpenAI-compatible services",
    )
    llm_model: str = Field(
        ...,
        title="LLM Model",
        description="Optional model identifier for custom OpenAI-compatible services",
    )
    host: str = Field(
        default="0.0.0.0",
        description="Service host"
    )
    port: int = Field(
        default=8000,
        description="Service port"
    )
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"
    )
    @classmethod
    def from_env(cls, overrides: Optional[dict[str, Any]] = None) -> "Configuration":
        """从环境变量中加载配置"""

        raw_values: dict[str, Any] = {}

        for field_name in cls.model_fields.keys():
            env_key = field_name.upper()
            if env_key in os.environ:
                raw_values[field_name] = os.environ[env_key]

        env_aliases = {
            "local_llm": os.getenv("LOCAL_LLM"),
            "llm_provider": os.getenv("LLM_PROVIDER"),
            "llm_api_key": os.getenv("LLM_API_KEY"),
            "llm_model": os.getenv("LLM_MODEL"),
            "llm_base_url": os.getenv("LLM_BASE_URL"),
            "lmstudio_base_url": os.getenv("LMSTUDIO_BASE_URL"),
            "ollama_base_url": os.getenv("OLLAMA_BASE_URL"),
            "max_web_research_loops": os.getenv("MAX_WEB_RESEARCH_LOOPS"),
            "fetch_full_page": os.getenv("FETCH_FULL_PAGE"),
            "use_tool_calling": os.getenv("USE_TOOL_CALLING"),
            "search_api": os.getenv("SEARCH_API"),
            "host": os.getenv("HOST"),
            "port": os.getenv("PORT"),
            "cors_origins": os.getenv("CORS_ORIGINS"),
        }

        for key, value in env_aliases.items():
            if value is not None:
                raw_values.setdefault(key, value)

        if overrides:
            for key, value in overrides.items():
                if value is not None:
                    raw_values[key] = value

        return cls(**raw_values)

    def sanitized_ollama_url(self) -> str:
        """Ensure Ollama base URL includes the /v1 suffix required by OpenAI clients."""

        base = self.ollama_base_url.rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        return base

    def resolved_model(self) -> Optional[str]:
        """Best-effort resolution of the model identifier to use."""

        return self.llm_model or self.local_llm

_config = None
def get_config():
    global _config
    if _config is None:
        _config = Configuration.from_env()
    return _config


if __name__ == '__main__':
    conf = get_config()
    print(conf)
