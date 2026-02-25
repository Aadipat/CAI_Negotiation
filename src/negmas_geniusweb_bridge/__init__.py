"""
NegMAS-GeniusWeb Bridge.

This module provides wrapped GeniusWeb negotiation agents that can be used
with NegMAS mechanisms.

Example:
    >>> from negmas_geniusweb_bridge import BoulwareAgent
    >>> negotiator = BoulwareAgent(ufun=my_ufun)
"""

from typing import Any

from .wrapper import (
    make_geniusweb_negotiator as make_negotiator,
    GeniusWebNegotiator,
    GENIUS_WEB_AVAILABLE,
)

# Check if negmas.registry is available (newer negmas versions)
try:
    from negmas.registry import register_negotiator

    REGISTRY_AVAILABLE = True
except ImportError:
    REGISTRY_AVAILABLE = False

    # Dummy decorator for older negmas versions
    def register_negotiator(
        cls: type | None = None,
        **kwargs: Any,
    ) -> Any:
        """Dummy decorator when registry is not available."""
        if cls is None:
            return lambda c: c
        return cls


# Import agent dictionaries from each module
from .anl2022 import AGENTS as ANL2022_AGENTS, WRAPPED_AGENTS as ANL2022_WRAPPED
from .anl2023 import AGENTS as ANL2023_AGENTS, WRAPPED_AGENTS as ANL2023_WRAPPED
from .basic import AGENTS as BASIC_AGENTS, WRAPPED_AGENTS as BASIC_WRAPPED
from .cse3210 import AGENTS as CSE3210_AGENTS, WRAPPED_AGENTS as CSE3210_WRAPPED
from .anac2020 import AGENTS as ANAC2020_AGENTS, WRAPPED_AGENTS as ANAC2020_WRAPPED
from .anac2021 import AGENTS as ANAC2021_AGENTS, WRAPPED_AGENTS as ANAC2021_WRAPPED

# Import individual wrapped classes for direct use
from .anac2020 import HammingAgent, ShineAgent
from .basic import (
    BoulwareAgent,
    ConcederAgent,
    LinearAgent,
    HardlinerAgent,
    RandomAgent,
    StupidAgent,
    TimeDependentAgent,
)

# Dictionaries for agent management
TRAINING_AGENTS: dict[str, Any] = {}
TESTING_AGENTS: dict[str, Any] = {}
ALL_AGENTS: dict[str, Any] = {}

# Combine all wrapped agents
ALL_AGENTS.update(BASIC_WRAPPED)
ALL_AGENTS.update(ANL2022_WRAPPED)
ALL_AGENTS.update(ANL2023_WRAPPED)
ALL_AGENTS.update(CSE3210_WRAPPED)
ALL_AGENTS.update(ANAC2020_WRAPPED)
ALL_AGENTS.update(ANAC2021_WRAPPED)

TRAINING_AGENTS = ALL_AGENTS.copy()
TESTING_AGENTS = ALL_AGENTS.copy()

# Agents with known issues that fail tests on some domains
# These get "disabled" and "broken" tags during registration
BROKEN_AGENTS: set[str] = {
    # ANL 2022 agents
    "BIUAgent",  # May timeout >60 secs on some domains
    "CompromisingAgent",  # May cause 'Action cannot be None' errors
    "LearningAgent",  # May cause 'Action cannot be None' errors
    "ProcrastinAgent",  # May have issues with first offer accepted
    # ANL 2023 agents
    "AmbitiousAgent",  # ProgressRounds missing getStart method
    # CSE3210 agents
    "Agent22",  # May throw scipy divide by zero errors
    "Agent67",  # Edge case issues on small domains
    "Agent68",  # May have issues handling opening bid
}


def _register_agent(
    agent_cls: type, short_name: str, tags: set[str], **kwargs: Any
) -> None:
    """Register a negotiator with backward compatibility for older negmas versions.

    Attempts to register with `source` parameter first (new API), and falls back
    to registration without `source` if that parameter is not supported.

    Args:
        agent_cls: The negotiator class to register.
        short_name: Short name for the negotiator.
        tags: Set of tags for the negotiator.
        **kwargs: Additional keyword arguments passed to register_negotiator.
    """
    try:
        register_negotiator(
            agent_cls,
            short_name=short_name,
            source="geniusweb-bridge",
            tags=tags,
            **kwargs,
        )
    except TypeError:
        # Fallback for older negmas versions without source parameter
        register_negotiator(
            agent_cls,
            short_name=short_name,
            tags=tags,
            **kwargs,
        )


def _add_broken_tags(name: str, tags: set[str]) -> set[str]:
    """Add 'disabled' and 'broken' tags if the agent is known to have issues."""
    if name in BROKEN_AGENTS:
        return tags | {"disabled", "broken"}
    return tags


# Register all wrapped agents with negmas.registry if available
def _register_agents() -> None:
    """Register all wrapped agents with negmas.registry."""
    if not REGISTRY_AVAILABLE:
        return

    # Basic agents - reference implementations
    for name, agent_cls in BASIC_WRAPPED.items():
        tags = {"geniusweb", "basic", "reference", "bilateral_only"}
        _register_agent(
            agent_cls,
            short_name=name,
            tags=_add_broken_tags(name, tags),
        )

    # ANAC 2020 agents - AI-translated from Java
    for name, agent_cls in ANAC2020_WRAPPED.items():
        tags = {"geniusweb", "anac2020", "ai-translated", "bilateral_only"}
        _register_agent(
            agent_cls,
            short_name=name,
            anac_year=2020,
            tags=_add_broken_tags(name, tags),
        )

    # ANAC 2021 agents - AI-translated from Java
    for name, agent_cls in ANAC2021_WRAPPED.items():
        tags = {"geniusweb", "anac2021", "ai-translated", "bilateral_only"}
        _register_agent(
            agent_cls,
            short_name=name,
            anac_year=2021,
            tags=_add_broken_tags(name, tags),
        )

    # ANL 2022 agents - Python native
    for name, agent_cls in ANL2022_WRAPPED.items():
        tags = {"geniusweb", "anl2022", "python-native", "bilateral_only"}
        _register_agent(
            agent_cls,
            short_name=name,
            anac_year=2022,
            tags=_add_broken_tags(name, tags),
        )

    # ANL 2023 agents - Python native
    for name, agent_cls in ANL2023_WRAPPED.items():
        tags = {"geniusweb", "anl2023", "python-native", "bilateral_only"}
        _register_agent(
            agent_cls,
            short_name=name,
            anac_year=2023,
            tags=_add_broken_tags(name, tags),
        )

    # CSE3210 agents - Python native (TU Delft course)
    for name, agent_cls in CSE3210_WRAPPED.items():
        tags = {
            "geniusweb",
            "cse3210",
            "python-native",
            "educational",
            "bilateral_only",
        }
        _register_agent(
            agent_cls,
            short_name=name,
            tags=_add_broken_tags(name, tags),
        )


# Perform registration on module import
_register_agents()

__all__ = [
    # Core classes
    "GeniusWebNegotiator",
    "make_negotiator",
    "GENIUS_WEB_AVAILABLE",
    "REGISTRY_AVAILABLE",
    # Agent dictionaries
    "ALL_AGENTS",
    "TRAINING_AGENTS",
    "TESTING_AGENTS",
    "BROKEN_AGENTS",
    # Individual wrapped agents - Basic
    "BoulwareAgent",
    "ConcederAgent",
    "LinearAgent",
    "HardlinerAgent",
    "RandomAgent",
    "StupidAgent",
    "TimeDependentAgent",
    # Individual wrapped agents - ANAC2020 (AI translated)
    "HammingAgent",
    "ShineAgent",
    # Raw agent dictionaries (for advanced users)
    "BASIC_AGENTS",
    "BASIC_WRAPPED",
    "ANL2022_AGENTS",
    "ANL2022_WRAPPED",
    "ANL2023_AGENTS",
    "ANL2023_WRAPPED",
    "CSE3210_AGENTS",
    "CSE3210_WRAPPED",
    "ANAC2020_AGENTS",
    "ANAC2020_WRAPPED",
    "ANAC2021_AGENTS",
    "ANAC2021_WRAPPED",
]
