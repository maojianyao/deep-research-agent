#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File    : llm.py
@Time    : 2026/9/24 09:55
@Author  : MaoJian Y
@Desc    : 文件功能描述
"""

import os
from typing import Literal, Any

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from backend.src.config import get_config

_llm_instance = None


class CompatibleChatOpenAI(ChatOpenAI):
    """在构造阶段固定 with_structured_output 的默认 method。

    部分兼容服务（Qwen/GLM 网关等）不支持 response_format=json_schema，
    在模型构造时绑定 method，调用方代码无需感知差异。
    """

    structured_output_method: Literal["function_calling", "json_mode", "json_schema"] = "function_calling"

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:
        kwargs.setdefault("method", self.structured_output_method)
        return super().with_structured_output(schema, **kwargs)

def get_llm() -> CompatibleChatOpenAI:
    """获取LLM实例"""
    global _llm_instance

    if not _llm_instance:
        conf = get_config()
        _llm_instance = CompatibleChatOpenAI(
            api_key=conf.llm_api_key or os.getenv("OPENAI_API_KEY"),
            base_url=conf.llm_base_url or os.getenv("OPENAI_BASE_URL"),
            model=conf.llm_model or os.getenv("OPENAI_MODEL") or "gpt-5.6",
            extra_body={"thinking": {"type": "disabled"}},  # 需关闭思考模式，不然结构化输出会报错,若报错清尝试 extra_body={"enable_thinking": False}
            structured_output_method="function_calling" if conf.use_tool_calling else "json_schema",
            max_tokens=384000,
        )
        return _llm_instance

    return _llm_instance


def reset_llm():
    """重置LLM实例（用于测试或重新配置）"""
    global _llm_instance
    _llm_instance = None
