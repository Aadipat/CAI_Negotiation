"""
CSE3210 Agents - Python Native.

Agents from the TU Delft CSE3210 Negotiation course.
These agents were written in Python by students as part of their coursework.

Note: Some agents have known issues and are marked accordingly in AGENT_NOTES.
"""

from typing import Any

from ..wrapper import make_geniusweb_negotiator

# Import raw agents - all 25 agents
from .agent2.agent2 import Agent2
from .agent3.agent3 import Agent3
from .agent7.agent7 import Agent7
from .agent11.agent11 import Agent11
from .agent14.agent14 import Agent14
from .agent18.agent18 import Agent18
from .agent19.agent19 import Agent19
from .agent22.agent22 import Agent22
from .agent24.agent24 import Agent24
from .agent25.agent25 import Agent25
from .agent26.agent26 import Agent26
from .agent27.agent27 import Agent27
from .agent29.agent29 import Agent29
from .agent32.agent32 import Agent32
from .agent33.agent33 import Agent33
from .agent41.agent41 import Agent41
from .agent43.agent43 import Agent43
from .agent50.agent50 import Agent50
from .agent52.agent52 import Agent52
from .agent55.agent55 import Agent55
from .agent58.agent58 import Agent58
from .agent61.agent61 import Agent61
from .agent64.agent64 import Agent64
from .agent67.agent67 import Agent67
from .agent68.agent68 import Agent68

# Dictionary of raw GeniusWeb party classes
# All agents are included, with notes about known issues in AGENT_NOTES
AGENTS: dict[str, Any] = {
    "Agent2": Agent2,
    "Agent3": Agent3,
    "Agent7": Agent7,
    "Agent11": Agent11,
    "Agent14": Agent14,
    "Agent18": Agent18,
    "Agent19": Agent19,
    "Agent22": Agent22,  # NOTE: throws scipy divide by zero errors
    "Agent24": Agent24,
    "Agent25": Agent25,
    "Agent26": Agent26,
    "Agent27": Agent27,
    "Agent29": Agent29,
    "Agent32": Agent32,
    "Agent33": Agent33,
    "Agent41": Agent41,
    "Agent43": Agent43,
    "Agent50": Agent50,
    "Agent52": Agent52,
    "Agent55": Agent55,
    "Agent58": Agent58,
    "Agent61": Agent61,
    "Agent64": Agent64,
    "Agent67": Agent67,
    "Agent68": Agent68,  # NOTE: can't handle opening bid
}

# Agent metadata with notes about known issues
AGENT_NOTES: dict[str, str] = {
    "Agent22": "May throw scipy divide by zero errors",
    "Agent68": "May have issues handling opening bid",
}

# Create GW-prefixed wrapped negotiator classes
Agent2 = make_geniusweb_negotiator(Agent2)
Agent3 = make_geniusweb_negotiator(Agent3)
Agent7 = make_geniusweb_negotiator(Agent7)
Agent11 = make_geniusweb_negotiator(Agent11)
Agent14 = make_geniusweb_negotiator(Agent14)
Agent18 = make_geniusweb_negotiator(Agent18)
Agent19 = make_geniusweb_negotiator(Agent19)
Agent22 = make_geniusweb_negotiator(Agent22)
Agent24 = make_geniusweb_negotiator(Agent24)
Agent25 = make_geniusweb_negotiator(Agent25)
Agent26 = make_geniusweb_negotiator(Agent26)
Agent27 = make_geniusweb_negotiator(Agent27)
Agent29 = make_geniusweb_negotiator(Agent29)
Agent32 = make_geniusweb_negotiator(Agent32)
Agent33 = make_geniusweb_negotiator(Agent33)
Agent41 = make_geniusweb_negotiator(Agent41)
Agent43 = make_geniusweb_negotiator(Agent43)
Agent50 = make_geniusweb_negotiator(Agent50)
Agent52 = make_geniusweb_negotiator(Agent52)
Agent55 = make_geniusweb_negotiator(Agent55)
Agent58 = make_geniusweb_negotiator(Agent58)
Agent61 = make_geniusweb_negotiator(Agent61)
Agent64 = make_geniusweb_negotiator(Agent64)
Agent67 = make_geniusweb_negotiator(Agent67)
Agent68 = make_geniusweb_negotiator(Agent68)

# Dictionary of wrapped negotiator classes
WRAPPED_AGENTS: dict[str, Any] = {
    "Agent2": Agent2,
    "Agent3": Agent3,
    "Agent7": Agent7,
    "Agent11": Agent11,
    "Agent14": Agent14,
    "Agent18": Agent18,
    "Agent19": Agent19,
    "Agent22": Agent22,
    "Agent24": Agent24,
    "Agent25": Agent25,
    "Agent26": Agent26,
    "Agent27": Agent27,
    "Agent29": Agent29,
    "Agent32": Agent32,
    "Agent33": Agent33,
    "Agent41": Agent41,
    "Agent43": Agent43,
    "Agent50": Agent50,
    "Agent52": Agent52,
    "Agent55": Agent55,
    "Agent58": Agent58,
    "Agent61": Agent61,
    "Agent64": Agent64,
    "Agent67": Agent67,
    "Agent68": Agent68,
}

__all__ = [
    # Raw agents
    "Agent2",
    "Agent3",
    "Agent7",
    "Agent11",
    "Agent14",
    "Agent18",
    "Agent19",
    "Agent22",
    "Agent24",
    "Agent25",
    "Agent26",
    "Agent27",
    "Agent29",
    "Agent32",
    "Agent33",
    "Agent41",
    "Agent43",
    "Agent50",
    "Agent52",
    "Agent55",
    "Agent58",
    "Agent61",
    "Agent64",
    "Agent67",
    "Agent68",
    # Wrapped agents
    "Agent2",
    "Agent3",
    "Agent7",
    "Agent11",
    "Agent14",
    "Agent18",
    "Agent19",
    "Agent22",
    "Agent24",
    "Agent25",
    "Agent26",
    "Agent27",
    "Agent29",
    "Agent32",
    "Agent33",
    "Agent41",
    "Agent43",
    "Agent50",
    "Agent52",
    "Agent55",
    "Agent58",
    "Agent61",
    "Agent64",
    "Agent67",
    "Agent68",
    # Dictionaries
    "AGENTS",
    "WRAPPED_AGENTS",
    "AGENT_NOTES",
]
