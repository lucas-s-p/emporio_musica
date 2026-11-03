from emporio.config import Settings
from emporio.llm.base import (
    LLMClient,
    LLMConfigError,
    LLMError,
    LLMResponse,
    LLMUnavailableError,
    ToolCall,
    tool_message,
)
from emporio.llm.openrouter import OpenRouterClient


def build_llm(settings: Settings) -> LLMClient:
    """The configured provider. Today only OpenRouter; add a branch here for another one."""
    return OpenRouterClient(settings.openrouter_api_key, settings.model_chain)


__all__ = [
    "LLMClient",
    "LLMConfigError",
    "LLMError",
    "LLMResponse",
    "LLMUnavailableError",
    "OpenRouterClient",
    "ToolCall",
    "build_llm",
    "tool_message",
]
