"""
Basic Reference Agents - Python Native.

Reference implementations of common negotiation strategies.
These agents are Python-native implementations based on the GeniusWeb framework.

Includes time-dependent strategies (Boulware, Conceder, Linear) and simple
testing agents (Random, Hardliner, Stupid).
"""

from typing import Any

from ..wrapper import make_geniusweb_negotiator

# Import raw agents
from .boulware_agent.boulware_agent import BoulwareAgent
from .conceder_agent.conceder_agent import ConcederAgent
from .hardliner_agent.hardliner_agent import HardlinerAgent
from .linear_agent.linear_agent import LinearAgent
from .random_agent.random_agent import RandomAgent
from .stupid_agent.stupid_agent import StupidAgent
from .time_dependent_agent.time_dependent_agent import TimeDependentAgent

# Dictionary of raw GeniusWeb party classes
# All agents are included, with notes about known issues in AGENT_NOTES
AGENTS: dict[str, Any] = {
    "BoulwareAgent": BoulwareAgent,
    "ConcederAgent": ConcederAgent,
    "HardlinerAgent": HardlinerAgent,  # NOTE: useless behaviour (never concedes)
    "LinearAgent": LinearAgent,
    "RandomAgent": RandomAgent,
    "StupidAgent": StupidAgent,  # NOTE: test agent
    "TimeDependentAgent": TimeDependentAgent,
}

# Agent metadata with notes about known issues
AGENT_NOTES: dict[str, str] = {
    "HardlinerAgent": "Never concedes - only useful for testing",
    "StupidAgent": "Test agent with simple random behavior",
    "TimeDependentAgent": "Base class for time-dependent strategies (e parameter controls concession speed)",
}

# Create GW-prefixed wrapped negotiator classes
BoulwareAgent = make_geniusweb_negotiator(BoulwareAgent)
ConcederAgent = make_geniusweb_negotiator(ConcederAgent)
HardlinerAgent = make_geniusweb_negotiator(HardlinerAgent)
LinearAgent = make_geniusweb_negotiator(LinearAgent)
RandomAgent = make_geniusweb_negotiator(RandomAgent)
StupidAgent = make_geniusweb_negotiator(StupidAgent)
TimeDependentAgent = make_geniusweb_negotiator(TimeDependentAgent)

# Dictionary of wrapped negotiator classes
WRAPPED_AGENTS: dict[str, Any] = {
    "BoulwareAgent": BoulwareAgent,
    "ConcederAgent": ConcederAgent,
    "HardlinerAgent": HardlinerAgent,
    "LinearAgent": LinearAgent,
    "RandomAgent": RandomAgent,
    "StupidAgent": StupidAgent,
    "TimeDependentAgent": TimeDependentAgent,
}

__all__ = [
    # Raw agents
    "BoulwareAgent",
    "ConcederAgent",
    "HardlinerAgent",
    "LinearAgent",
    "RandomAgent",
    "StupidAgent",
    "TimeDependentAgent",
    # Wrapped agents
    "BoulwareAgent",
    "ConcederAgent",
    "HardlinerAgent",
    "LinearAgent",
    "RandomAgent",
    "StupidAgent",
    "TimeDependentAgent",
    # Dictionaries
    "AGENTS",
    "WRAPPED_AGENTS",
    "AGENT_NOTES",
]
