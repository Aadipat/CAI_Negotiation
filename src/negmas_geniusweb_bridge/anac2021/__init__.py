"""
ANAC 2021 Agents - AI-translated from Java.

These agents were originally implemented in Java for the ANAC 2021 competition
and have been translated to Python using AI assistance.

Exports both raw GeniusWeb party classes and GW-prefixed wrapped negotiators.

Agent Tags:
- "AI-translated": Agent was translated from Java using AI
- "SAOP": Agent supports standard SAOP protocol
- "learning": Agent uses learning protocol (persistent state across sessions)

Note: Some agents (AortaBoa, POMPFANAgent, etc.) are not yet translated.
"""

from typing import Any

from ..wrapper import make_geniusweb_negotiator

# Import raw agents
from .agent_fo2021.agent_fo2021 import AgentFO2021
from .alpha_biu.alpha_biu import AlphaBIU
from .dice_haggler.dice_haggler import TheDiceHaggler2021
from .gambler_agent.gambler_agent import GamblerAgent
from .matrix_alien_agent.matrix_alien_agent import MatrixAlienAgent
from .triple_agent.triple_agent import TripleAgent

# Dictionary of raw GeniusWeb party classes
AGENTS: dict[str, Any] = {
    "AgentFO2021": AgentFO2021,
    "AlphaBIU": AlphaBIU,
    "GamblerAgent": GamblerAgent,
    "MatrixAlienAgent": MatrixAlienAgent,
    "TheDiceHaggler2021": TheDiceHaggler2021,
    "TripleAgent": TripleAgent,
}

# Agent metadata with tags
AGENT_METADATA: dict[str, dict[str, Any]] = {
    "AgentFO2021": {
        "class": AgentFO2021,
        "tags": ["AI-translated", "SAOP", "learning"],
        "description": "Learning-based agent with time-dependent concession and opponent tracking",
    },
    "AlphaBIU": {
        "class": AlphaBIU,
        "tags": ["AI-translated", "SAOP", "learning"],
        "description": "Frequency-based opponent modeling with two-phase strategy",
    },
    "GamblerAgent": {
        "class": GamblerAgent,
        "tags": ["AI-translated", "SAOP", "learning"],
        "description": "UCB Multi-Armed Bandit selecting among 4 PonPoko-style sub-agents",
    },
    "MatrixAlienAgent": {
        "class": MatrixAlienAgent,
        "tags": ["AI-translated", "SAOP"],
        "description": "Adaptive boulware-style agent with multi-factor bid scoring",
    },
    "TheDiceHaggler2021": {
        "class": TheDiceHaggler2021,
        "tags": ["AI-translated", "SAOP"],
        "description": "Multi-phase time-dependent strategy with Pareto estimation and TOPSIS",
    },
    "TripleAgent": {
        "class": TripleAgent,
        "tags": ["AI-translated", "SAOP", "learning"],
        "description": "Uses frequency model and utility space analysis for bidding",
    },
}

# Known issues/notes for specific agents
AGENT_NOTES: dict[str, str] = {
    "AgentFO2021": "Persistent state features simplified (no file I/O)",
    "AlphaBIU": "Persistent state features simplified (no file I/O)",
    "GamblerAgent": "Persistent state features simplified (no file I/O)",
    "MatrixAlienAgent": "Adaptive learning parameters for e and min values",
    "TheDiceHaggler2021": "Simplified from original (uses sampling-based Pareto estimation)",
    "TripleAgent": "Persistent state features simplified (no file I/O)",
}

# Create GW-prefixed wrapped negotiator classes
AgentFO2021 = make_geniusweb_negotiator(AgentFO2021)
AlphaBIU = make_geniusweb_negotiator(AlphaBIU)
GamblerAgent = make_geniusweb_negotiator(GamblerAgent)
MatrixAlienAgent = make_geniusweb_negotiator(MatrixAlienAgent)
TheDiceHaggler2021 = make_geniusweb_negotiator(TheDiceHaggler2021)
TripleAgent = make_geniusweb_negotiator(TripleAgent)

# Dictionary of wrapped negotiator classes (for registration)
WRAPPED_AGENTS: dict[str, Any] = {
    "AgentFO2021": AgentFO2021,
    "AlphaBIU": AlphaBIU,
    "GamblerAgent": GamblerAgent,
    "MatrixAlienAgent": MatrixAlienAgent,
    "TheDiceHaggler2021": TheDiceHaggler2021,
    "TripleAgent": TripleAgent,
}

# Wrapped agent metadata (same tags as raw agents)
WRAPPED_AGENT_METADATA: dict[str, dict[str, Any]] = {
    "AgentFO2021": {
        "class": AgentFO2021,
        "tags": ["AI-translated", "SAOP", "learning"],
        "description": "Learning-based agent with time-dependent concession and opponent tracking",
    },
    "AlphaBIU": {
        "class": AlphaBIU,
        "tags": ["AI-translated", "SAOP", "learning"],
        "description": "Frequency-based opponent modeling with two-phase strategy",
    },
    "GamblerAgent": {
        "class": GamblerAgent,
        "tags": ["AI-translated", "SAOP", "learning"],
        "description": "UCB Multi-Armed Bandit selecting among 4 PonPoko-style sub-agents",
    },
    "MatrixAlienAgent": {
        "class": MatrixAlienAgent,
        "tags": ["AI-translated", "SAOP"],
        "description": "Adaptive boulware-style agent with multi-factor bid scoring",
    },
    "TheDiceHaggler2021": {
        "class": TheDiceHaggler2021,
        "tags": ["AI-translated", "SAOP"],
        "description": "Multi-phase time-dependent strategy with Pareto estimation and TOPSIS",
    },
    "TripleAgent": {
        "class": TripleAgent,
        "tags": ["AI-translated", "SAOP", "learning"],
        "description": "Uses frequency model and utility space analysis for bidding",
    },
}

__all__ = [
    # Raw agents
    "AgentFO2021",
    "AlphaBIU",
    "GamblerAgent",
    "MatrixAlienAgent",
    "TheDiceHaggler2021",
    "TripleAgent",
    # Wrapped agents
    "AgentFO2021",
    "AlphaBIU",
    "GamblerAgent",
    "MatrixAlienAgent",
    "TheDiceHaggler2021",
    "TripleAgent",
    # Dictionaries
    "AGENTS",
    "WRAPPED_AGENTS",
    "AGENT_NOTES",
    # Metadata
    "AGENT_METADATA",
    "WRAPPED_AGENT_METADATA",
]
