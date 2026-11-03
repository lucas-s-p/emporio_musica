from pathlib import Path

from emporio.agent.agent import Agent, AgentReply, ToolTrace
from emporio.agent.prompt import build_system_prompt
from emporio.data import Store
from emporio.knowledge import PolicyIndex
from emporio.llm import LLMClient
from emporio.services.clock import Clock
from emporio.tools import build_registry


def build_agent(
    llm: LLMClient,
    store: Store,
    clock: Clock,
    policies: PolicyIndex,
    prompts_dir: Path,
) -> Agent:
    """A fresh conversation: own tool registry (so own verified identity) and own history."""
    return Agent(
        llm,
        build_registry(store, clock, policies=policies),
        build_system_prompt(clock, prompts_dir),
    )


__all__ = ["Agent", "AgentReply", "ToolTrace", "build_agent", "build_system_prompt"]
