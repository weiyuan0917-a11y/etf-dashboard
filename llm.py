# -*- coding: utf-8 -*-
"""LLM 客户端：DeepSeek 优先（OpenAI 兼容协议），可切换任意 OpenAI 兼容服务。

配置项存于 settings 表：
  - llm_provider        : 'deepseek' | 'openai' | 'custom'
  - llm_api_key         : str
  - llm_base_url        : str（custom 必填，其他可留空走默认）
  - llm_model           : str（默认 deepseek-chat / gpt-4o-mini）
  - llm_enabled         : '1' / '0'（侧栏开关）
"""
from __future__ import annotations

import json
import time
from typing import Generator

from openai import OpenAI

import storage


class _RetryableEmptyResponse(Exception):
    """内部信号：max_tokens 被 reasoning 吃光，调用方可以重试或换模型。"""
    pass

# 各 provider 的默认 base_url / model
_DEFAULTS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "custom": {
        "base_url": "",
        "model": "",
    },
}


def get_config() -> dict:
    """读出当前 LLM 配置（未设置项补默认值）。"""
    p = storage.get_setting("llm_provider", "deepseek")
    cfg = dict(_DEFAULTS.get(p, _DEFAULTS["deepseek"]))
    cfg["provider"] = p
    cfg["api_key"] = storage.get_setting("llm_api_key", "")
    cfg["base_url"] = storage.get_setting("llm_base_url", cfg["base_url"])
    cfg["model"] = storage.get_setting("llm_model", cfg["model"])
    cfg["enabled"] = storage.get_setting("llm_enabled", "0") == "1"
    return cfg


def is_ready() -> bool:
    """是否已配置且启用（用于页面里决定是否展示 AI 功能）。"""
    cfg = get_config()
    return bool(cfg["enabled"] and cfg["api_key"] and cfg["model"])


def save_config(
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    enabled: bool,
) -> None:
    """写入所有 LLM 设置。base_url / model 留空时由 provider 默认值兜底。"""
    storage.set_setting("llm_provider", provider)
    storage.set_setting("llm_api_key", api_key.strip())
    storage.set_setting("llm_base_url", base_url.strip())
    storage.set_setting("llm_model", model.strip())
    storage.set_setting("llm_enabled", "1" if enabled else "0")


def _client() -> OpenAI:
    cfg = get_config()
    if not cfg["api_key"]:
        raise RuntimeError("LLM API key 未配置")
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"] or None)


def chat(
    messages: list[dict],
    *,
    temperature: float = 0.4,
    max_tokens: int = 1500,
    stream: bool = False,
) -> str | Generator[str, None, None]:
    """通用对话接口。messages: [{"role": "system|user|assistant", "content": str}]"""
    cfg = get_config()
    client = _client()
    if stream:
        return _stream(client, cfg["model"], messages, temperature, max_tokens)
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    choice = resp.choices[0]
    content = choice.message.content or ""
    # DeepSeek 一些"带思考"的变体（flash / reasoner）会把推理时间吃满 max_tokens，
    # 真正给用户的内容只剩 0 字、几字、或 finish_reason=length。
    # 处理顺序：
    #   1) content 非空 → 直接用
    #   2) content 空 + reasoning 非空 → 拼成"思考过程"给用户（避免白板）
    #   3) 都空 + finish_reason=length → 极可能是 max_tokens 不够，
    #      自动用 max_tokens×2 重试一次（覆盖 flash 大量 reasoning 场景）
    #   4) 仍失败 → 抛错
    if not content:
        reasoning = getattr(choice.message, "reasoning_content", None) or ""
        if reasoning and choice.finish_reason != "length":
            # 有 reasoning 但被风控过滤 → 拼出来
            return f"（模型未输出正文，以下是它的思考过程）\n\n{reasoning}"
        if reasoning and choice.finish_reason == "length":
            # max_tokens 被 reasoning 吃光 → 重试
            raise _RetryableEmptyResponse(
                f"flash/reasoner 把 max_tokens={max_tokens} 全部花在 reasoning 上。"
                f"实际 reasoning {len(reasoning)} 字，content 0 字。"
            )
        # content/reasoning 都空
        raise RuntimeError(
            f"模型返回空内容（finish_reason={choice.finish_reason}）。"
            f"可能原因：① 触发内容安全风控；② 模型/账号异常；③ 余额/限流。"
        )
    return content


def _stream(client, model, messages, temperature, max_tokens) -> Generator[str, None, None]:
    """流式生成，每 yield 一个文本块。"""
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in stream:
        try:
            delta = chunk.choices[0].delta.content
        except (IndexError, AttributeError):
            delta = None
        if delta:
            yield delta


def ping() -> dict:
    """连通性自检：发一条 'hi' 看模型能不能回。返回 {ok, latency_ms, model, error}。"""
    cfg = get_config()
    t0 = time.time()
    try:
        reply = chat(
            messages=[{"role": "user", "content": "回复一个字符：OK"}],
            temperature=0.0,
            max_tokens=10,
        )
        return {
            "ok": True,
            "latency_ms": int((time.time() - t0) * 1000),
            "model": cfg["model"],
            "reply": (reply or "").strip()[:50],
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "latency_ms": int((time.time() - t0) * 1000),
            "model": cfg["model"],
            "error": str(e)[:200],
        }
