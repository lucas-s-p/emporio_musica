"""Builds the tool registry of one conversation."""

from emporio.data import Store
from emporio.services.clock import Clock
from emporio.services.identity import CustomerVerifier
from emporio.tools.base import ToolRegistry
from emporio.tools.checkout import checkout_tools
from emporio.tools.context import ToolContext
from emporio.tools.orders import order_tools
from emporio.tools.products import product_tools
from emporio.tools.storeinfo import storeinfo_tools


def build_registry(
    store: Store, clock: Clock, verifier: CustomerVerifier | None = None
) -> ToolRegistry:
    """One registry per conversation: the verifier inside it keeps that conversation's identity."""
    ctx = ToolContext(store=store, clock=clock, verifier=verifier or CustomerVerifier(store))
    return ToolRegistry(
        [
            *product_tools(ctx),
            *checkout_tools(ctx),
            *storeinfo_tools(ctx),
            *order_tools(ctx),
        ]
    )
