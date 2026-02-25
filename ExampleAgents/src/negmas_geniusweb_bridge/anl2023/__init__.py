"""
ANL 2023 Agents.

Agents from the Automated Negotiating Agents League 2023 competition.
"""

from typing import Any

from ..wrapper import make_geniusweb_negotiator

# Import raw agents - core agents that don't need heavy dependencies
from .agent_fo3.AgentFO3 import AgentFO3
from .ambitious_agent.AmbitiousAgent import AmbitiousAgent
from .ant_alliance.antAlliance_agent import AntAllianceAgent
from .ant_heart.antHeart_agent import AntHeartAgent
from .colman_anacondot_agent2.colman_anacondot_agent2 import ColmanAnacondotAgent2
from .exploit_agent.exploit_agent import ExploitAgent
from .got_agent.got_agent import GotAgent
from .hybrid_agent2023.HybridAgent2023 import HybridAgent2023

# KB_time_diff_Agent renamed to KBTimeDiffAgent for Pythonic naming
from .kb_time_diff_agent.kb_time_diff_agent import KB_time_diff_Agent as KBTimeDiffAgent
from .micro_2023.micro_2023 import MiCRO2023
from .popular_agent.popular_agent import PopularAgent
from .smart_agent.smart_agent import SmartAgent
from .spaghetti_agent.spaghetti_agent import Agent37 as SpaghettiAgent
from .triple_e_agent.TripleE_agent import TripleE as TripleEAgent

# MSCAgent requires gym, torch, stable-baselines3 - make it optional
try:
    from .msc_agent.MSC_agent import MSCAgent

    MSC_AGENT_AVAILABLE = True
except ImportError:
    MSCAgent = None  # type: ignore[misc, assignment]
    MSC_AGENT_AVAILABLE = False

# Dictionary of raw GeniusWeb party classes
AGENTS: dict[str, Any] = {
    "AgentFO3": AgentFO3,
    "AmbitiousAgent": AmbitiousAgent,
    "AntAllianceAgent": AntAllianceAgent,
    "AntHeartAgent": AntHeartAgent,
    "ColmanAnacondotAgent2": ColmanAnacondotAgent2,
    "ExploitAgent": ExploitAgent,
    "GotAgent": GotAgent,
    "HybridAgent2023": HybridAgent2023,
    "KBTimeDiffAgent": KBTimeDiffAgent,
    "MiCRO2023": MiCRO2023,
    "PopularAgent": PopularAgent,
    "SmartAgent": SmartAgent,
    "SpaghettiAgent": SpaghettiAgent,
    "TripleEAgent": TripleEAgent,
}

# Add MSCAgent if available
if MSC_AGENT_AVAILABLE:
    AGENTS["MSCAgent"] = MSCAgent

# Create GW-prefixed wrapped negotiator classes
AgentFO3 = make_geniusweb_negotiator(AgentFO3)
AmbitiousAgent = make_geniusweb_negotiator(AmbitiousAgent)
AntAllianceAgent = make_geniusweb_negotiator(AntAllianceAgent)
AntHeartAgent = make_geniusweb_negotiator(AntHeartAgent)
ColmanAnacondotAgent2 = make_geniusweb_negotiator(ColmanAnacondotAgent2)
ExploitAgent = make_geniusweb_negotiator(ExploitAgent)
GotAgent = make_geniusweb_negotiator(GotAgent)
HybridAgent2023 = make_geniusweb_negotiator(HybridAgent2023)
KBTimeDiffAgent = make_geniusweb_negotiator(KBTimeDiffAgent)
MiCRO2023 = make_geniusweb_negotiator(MiCRO2023)
PopularAgent = make_geniusweb_negotiator(PopularAgent)
SmartAgent = make_geniusweb_negotiator(SmartAgent)
SpaghettiAgent = make_geniusweb_negotiator(SpaghettiAgent)
TripleEAgent = make_geniusweb_negotiator(TripleEAgent)

# Dictionary of wrapped negotiator classes
WRAPPED_AGENTS: dict[str, Any] = {
    "AgentFO3": AgentFO3,
    "AmbitiousAgent": AmbitiousAgent,
    "AntAllianceAgent": AntAllianceAgent,
    "AntHeartAgent": AntHeartAgent,
    "ColmanAnacondotAgent2": ColmanAnacondotAgent2,
    "ExploitAgent": ExploitAgent,
    "GotAgent": GotAgent,
    "HybridAgent2023": HybridAgent2023,
    "KBTimeDiffAgent": KBTimeDiffAgent,
    "MiCRO2023": MiCRO2023,
    "PopularAgent": PopularAgent,
    "SmartAgent": SmartAgent,
    "SpaghettiAgent": SpaghettiAgent,
    "TripleEAgent": TripleEAgent,
}

# Add MSCAgent if available
if MSC_AGENT_AVAILABLE:
    MSCAgent = make_geniusweb_negotiator(MSCAgent)
    WRAPPED_AGENTS["MSCAgent"] = MSCAgent
else:
    MSCAgent = None  # type: ignore[misc, assignment]

__all__ = [
    # Availability flags
    "MSC_AGENT_AVAILABLE",
    # Raw agents
    "AgentFO3",
    "AmbitiousAgent",
    "AntAllianceAgent",
    "AntHeartAgent",
    "ColmanAnacondotAgent2",
    "ExploitAgent",
    "GotAgent",
    "HybridAgent2023",
    "KBTimeDiffAgent",
    "MiCRO2023",
    "MSCAgent",
    "PopularAgent",
    "SmartAgent",
    "SpaghettiAgent",
    "TripleEAgent",
    # Wrapped agents
    "AgentFO3",
    "AmbitiousAgent",
    "AntAllianceAgent",
    "AntHeartAgent",
    "ColmanAnacondotAgent2",
    "ExploitAgent",
    "GotAgent",
    "HybridAgent2023",
    "KBTimeDiffAgent",
    "MiCRO2023",
    "MSCAgent",
    "PopularAgent",
    "SmartAgent",
    "SpaghettiAgent",
    "TripleEAgent",
    # Dictionaries
    "AGENTS",
    "WRAPPED_AGENTS",
]
