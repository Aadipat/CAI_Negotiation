"""
ANL 2022 Agents - Python Native.

Agents from the Automated Negotiation League 2022 competition.
These agents were originally written in Python by their authors.

Note: Some agents have known issues and are marked accordingly.
"""

from typing import Any

from ..wrapper import make_geniusweb_negotiator

# Import raw agents - all agents that can be imported
from .agent007.agent007 import Agent007
from .agent4410.agent_4410 import Agent4410
from .agentfish.agentfish import AgentFish
from .agent_fo2.AgentFO2 import AgentFO2
from .biu_agent.BIU_agent import BIU_agent as BIUAgent
from .charging_boul.charging_boul import ChargingBoul
from .compromising_agent.compromising_agent import CompromisingAgent
from .dreamteam109_agent.dreamteam109_agent import DreamTeam109Agent
from .gea_agent.gea_agent import GEAAgent
from .learning_agent.learning_agent import LearningAgent
from .lucky_agent_2022.LuckyAgent2022 import LuckyAgent2022
from .micro_agent.micro_agent.micro_agent import MiCROAgent
from .procrastin_agent.procrastin_agent import ProcrastinAgent
from .rg_agent.rg_agent import RGAgent
from .smart_agent.smart_agent import SmartAgent
from .super_agent.super_agent import SuperAgent
from .thirdagent.third_agent import ThirdAgent
from .tjaronchery10_agent.tjaronchery10_agent import Tjaronchery10Agent

# PinarAgent requires lightgbm - make it optional
try:
    from .pinar_agent.Pinar_Agent import Pinar_Agent as PinarAgent

    PINAR_AGENT_AVAILABLE = True
except ImportError:
    PinarAgent = None  # type: ignore[misc, assignment]
    PINAR_AGENT_AVAILABLE = False

# Dictionary of raw GeniusWeb party classes
# All agents are included, with notes about known issues
AGENTS: dict[str, Any] = {
    "Agent007": Agent007,
    "Agent4410": Agent4410,
    "AgentFish": AgentFish,
    "AgentFO2": AgentFO2,
    "BIUAgent": BIUAgent,  # NOTE: may timeout >60 secs on some domains
    "ChargingBoul": ChargingBoul,
    "CompromisingAgent": CompromisingAgent,  # NOTE: may cause Action cannot be None errors
    "DreamTeam109Agent": DreamTeam109Agent,
    "GEAAgent": GEAAgent,  # NOTE: slow, a turn takes ~1.5sec
    "LearningAgent": LearningAgent,  # NOTE: may cause Action cannot be None errors
    "LuckyAgent2022": LuckyAgent2022,
    "MiCROAgent": MiCROAgent,
    "ProcrastinAgent": ProcrastinAgent,  # NOTE: may have issues with first offer accepted
    "RGAgent": RGAgent,
    "SmartAgent": SmartAgent,
    "SuperAgent": SuperAgent,
    "ThirdAgent": ThirdAgent,
    "Tjaronchery10Agent": Tjaronchery10Agent,
}

# Add PinarAgent if available
if PINAR_AGENT_AVAILABLE:
    AGENTS["PinarAgent"] = PinarAgent

# Agent metadata with notes about known issues
AGENT_NOTES: dict[str, str] = {
    "BIUAgent": "May timeout >60 secs on some domains",
    "CompromisingAgent": "May cause 'Action cannot be None' errors",
    "GEAAgent": "Slow execution, ~1.5sec per turn",
    "LearningAgent": "May cause 'Action cannot be None' errors",
    "ProcrastinAgent": "May have issues handling first offer accepted",
    "PinarAgent": "Requires lightgbm package",
}

# Create GW-prefixed wrapped negotiator classes
Agent007 = make_geniusweb_negotiator(Agent007)
Agent4410 = make_geniusweb_negotiator(Agent4410)
AgentFish = make_geniusweb_negotiator(AgentFish)
AgentFO2 = make_geniusweb_negotiator(AgentFO2)
BIUAgent = make_geniusweb_negotiator(BIUAgent)
ChargingBoul = make_geniusweb_negotiator(ChargingBoul)
CompromisingAgent = make_geniusweb_negotiator(CompromisingAgent)
DreamTeam109Agent = make_geniusweb_negotiator(DreamTeam109Agent)
GEAAgent = make_geniusweb_negotiator(GEAAgent)
LearningAgent = make_geniusweb_negotiator(LearningAgent)
LuckyAgent2022 = make_geniusweb_negotiator(LuckyAgent2022)
MiCROAgent = make_geniusweb_negotiator(MiCROAgent)
ProcrastinAgent = make_geniusweb_negotiator(ProcrastinAgent)
RGAgent = make_geniusweb_negotiator(RGAgent)
SmartAgent = make_geniusweb_negotiator(SmartAgent)
SuperAgent = make_geniusweb_negotiator(SuperAgent)
ThirdAgent = make_geniusweb_negotiator(ThirdAgent)
Tjaronchery10Agent = make_geniusweb_negotiator(Tjaronchery10Agent)

# Dictionary of wrapped negotiator classes
WRAPPED_AGENTS: dict[str, Any] = {
    "Agent007": Agent007,
    "Agent4410": Agent4410,
    "AgentFish": AgentFish,
    "AgentFO2": AgentFO2,
    "BIUAgent": BIUAgent,
    "ChargingBoul": ChargingBoul,
    "CompromisingAgent": CompromisingAgent,
    "DreamTeam109Agent": DreamTeam109Agent,
    "GEAAgent": GEAAgent,
    "LearningAgent": LearningAgent,
    "LuckyAgent2022": LuckyAgent2022,
    "MiCROAgent": MiCROAgent,
    "ProcrastinAgent": ProcrastinAgent,
    "RGAgent": RGAgent,
    "SmartAgent": SmartAgent,
    "SuperAgent": SuperAgent,
    "ThirdAgent": ThirdAgent,
    "Tjaronchery10Agent": Tjaronchery10Agent,
}

# Add PinarAgent if available
if PINAR_AGENT_AVAILABLE:
    PinarAgent = make_geniusweb_negotiator(PinarAgent)
    WRAPPED_AGENTS["PinarAgent"] = PinarAgent
else:
    PinarAgent = None  # type: ignore[misc, assignment]

__all__ = [
    # Availability flags
    "PINAR_AGENT_AVAILABLE",
    # Raw agents
    "Agent007",
    "Agent4410",
    "AgentFish",
    "AgentFO2",
    "BIUAgent",
    "ChargingBoul",
    "CompromisingAgent",
    "DreamTeam109Agent",
    "GEAAgent",
    "LearningAgent",
    "LuckyAgent2022",
    "MiCROAgent",
    "PinarAgent",
    "ProcrastinAgent",
    "RGAgent",
    "SmartAgent",
    "SuperAgent",
    "ThirdAgent",
    "Tjaronchery10Agent",
    # Wrapped agents
    "Agent007",
    "Agent4410",
    "AgentFish",
    "AgentFO2",
    "BIUAgent",
    "ChargingBoul",
    "CompromisingAgent",
    "DreamTeam109Agent",
    "GEAAgent",
    "LearningAgent",
    "LuckyAgent2022",
    "MiCROAgent",
    "PinarAgent",
    "ProcrastinAgent",
    "RGAgent",
    "SmartAgent",
    "SuperAgent",
    "ThirdAgent",
    "Tjaronchery10Agent",
    # Dictionaries
    "AGENTS",
    "WRAPPED_AGENTS",
    "AGENT_NOTES",
]
