"""Per-conversation dependencies shared by all tools."""

from dataclasses import dataclass

from emporio.data import Store
from emporio.services.clock import Clock
from emporio.services.identity import CustomerVerifier


@dataclass(frozen=True)
class ToolContext:
    store: Store
    clock: Clock
    verifier: CustomerVerifier  # holds who is verified in THIS conversation
