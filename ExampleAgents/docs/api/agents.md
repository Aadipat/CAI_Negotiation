# Agents Reference

This page documents all available negotiation agents in the bridge library.

## Importing Agents

All wrapped agents (NegMAS-compatible) are prefixed with `GW` and can be imported directly:

```python
# Import specific wrapped agents
from negmas_geniusweb_bridge import BoulwareAgent, HammingAgent

# Import all agents as a dictionary
from negmas_geniusweb_bridge import ALL_AGENTS

# Import from specific modules
from negmas_geniusweb_bridge.basic import BoulwareAgent, ConcederAgent
from negmas_geniusweb_bridge.anac2020 import HammingAgent, ShineAgent
from negmas_geniusweb_bridge.anac2021 import AgentFO2021, AlphaBIU
from negmas_geniusweb_bridge.anl2022 import Agent007, MiCROAgent
from negmas_geniusweb_bridge.anl2023 import AgentFO3, PopularAgent
from negmas_geniusweb_bridge.cse3210 import Agent11, Agent27
```

## Module Structure

Each agent module exports:

- `AGENTS` - Dictionary of raw GeniusWeb party classes
- `WRAPPED_AGENTS` - Dictionary of NegMAS-wrapped negotiator classes
- `AGENT_NOTES` - Known issues/notes about specific agents (where applicable)
- Individual agent classes (both raw and wrapped)

---

## Basic Agents

Reference implementations of common negotiation strategies.

| Agent | Wrapped Name | Description |
|-------|--------------|-------------|
| `BoulwareAgent` | `BoulwareAgent` | Time-dependent concession (hardliner early, concedes late) |
| `ConcederAgent` | `ConcederAgent` | Time-dependent concession (concedes early) |
| `LinearAgent` | `LinearAgent` | Linear concession over time |
| `HardlinerAgent` | `HardlinerAgent` | Never concedes (testing only) |
| `RandomAgent` | `RandomAgent` | Random bid selection |
| `StupidAgent` | `StupidAgent` | Simple random behavior (test agent) |
| `TimeDependentAgent` | `TimeDependentAgent` | Base class with configurable `e` parameter |

??? info "API Reference - Basic Agents"
    ::: negmas_geniusweb_bridge.basic
        options:
          show_source: false
          members:
            - AGENTS
            - WRAPPED_AGENTS
            - BoulwareAgent
            - ConcederAgent
            - LinearAgent
            - HardlinerAgent
            - RandomAgent
            - StupidAgent
            - TimeDependentAgent

---

## ANAC 2020 Agents

Agents translated from Java implementations submitted to ANAC 2020.

!!! warning "AI-Translated Code"
    These agents were translated from Java to Python using AI assistance.
    While functionally equivalent, they may have subtle differences from the originals.

| Agent | Wrapped Name | Protocol | Description |
|-------|--------------|----------|-------------|
| `AgentKT` | `AgentKT` | SHAOP/SAOP | COBYLA optimization with game-theoretic thresholds |
| `AgentP1DAMO` | `AgentP1DAMO` | SHAOP | Hill climbing with importance maps |
| `AgentXX` | `AgentXX` | SHAOP/SAOP | Importance maps with Nash point estimation |
| `AhBuNeAgent` | `AhBuNeAgent` | SHAOP | Similarity-based bidding with elicitation |
| `Anaconda` | `Anaconda` | SHAOP | Dynamic lower bounds with elicitation |
| `Angel` | `Angel` | SHAOP/SAOP | Heuristic opponent modeling with elicitation |
| `AzarAgent` | `AzarAgent` | SHAOP/SAOP | GravityEs user model with frequency modeling |
| `BlingBling` | `BlingBling` | SHAOP/SAOP | RankNet neural network for preference learning |
| `DUOAgent` | `DUOAgent` | SHAOP/SAOP | Linear regression for bid prediction |
| `ForArisa` | `ForArisa` | SAOP | Genetic algorithm for utility estimation |
| `HammingAgent` | `HammingAgent` | SAOP | Hamming distance for opponent modeling |
| `NiceAgent` | `NiceAgent` | SHAOP/SAOP | Elicitation with mirroring strategy |
| `ShineAgent` | `ShineAgent` | SAOP | Adaptive agent with dynamic strategy |

??? info "API Reference - ANAC 2020 Agents"
    ::: negmas_geniusweb_bridge.anac2020
        options:
          show_source: false
          members:
            - AGENTS
            - WRAPPED_AGENTS
            - AgentKT
            - AgentP1DAMO
            - AgentXX
            - AhBuNeAgent
            - Anaconda
            - Angel
            - AzarAgent
            - BlingBling
            - DUOAgent
            - ForArisa
            - HammingAgent
            - NiceAgent
            - ShineAgent

---

## ANAC 2021 Agents

Agents translated from Java implementations submitted to ANAC 2021.

!!! warning "AI-Translated Code"
    These agents were translated from Java to Python using AI assistance.

| Agent | Wrapped Name | Description |
|-------|--------------|-------------|
| `AgentFO2021` | `AgentFO2021` | Learning-based agent with time-dependent concession |
| `AlphaBIU` | `AlphaBIU` | Frequency-based opponent modeling with two-phase strategy |
| `GamblerAgent` | `GamblerAgent` | UCB Multi-Armed Bandit selecting among sub-agents |
| `MatrixAlienAgent` | `MatrixAlienAgent` | Adaptive boulware-style with multi-factor bid scoring |
| `TheDiceHaggler2021` | `TheDiceHaggler2021` | Multi-phase strategy with Pareto estimation and TOPSIS |
| `TripleAgent` | `TripleAgent` | Frequency model and utility space analysis |

??? info "API Reference - ANAC 2021 Agents"
    ::: negmas_geniusweb_bridge.anac2021
        options:
          show_source: false
          members:
            - AGENTS
            - WRAPPED_AGENTS
            - AgentFO2021
            - AlphaBIU
            - GamblerAgent
            - MatrixAlienAgent
            - TheDiceHaggler2021
            - TripleAgent

---

## ANL 2022 Agents

Native Python agents from the Automated Negotiation League 2022.

| Agent | Wrapped Name | Notes |
|-------|--------------|-------|
| `Agent007` | `Agent007` | |
| `Agent4410` | `Agent4410` | |
| `AgentFish` | `AgentFish` | |
| `AgentFO2` | `AgentFO2` | May timeout >60 secs |
| `BIUAgent` | `BIUAgent` | May timeout >60 secs |
| `ChargingBoul` | `ChargingBoul` | |
| `CompromisingAgent` | `CompromisingAgent` | May cause "Action cannot be None" |
| `DreamTeam109Agent` | `DreamTeam109Agent` | |
| `GEAAgent` | `GEAAgent` | Slow (~1.5sec per turn) |
| `LearningAgent` | `LearningAgent` | May cause "Action cannot be None" |
| `LuckyAgent2022` | `LuckyAgent2022` | |
| `MiCROAgent` | `MiCROAgent` | |
| `PinarAgent` | `PinarAgent` | Requires `lightgbm` (optional) |
| `ProcrastinAgent` | `ProcrastinAgent` | Issues with first offer |
| `RGAgent` | `RGAgent` | |
| `SmartAgent` | `SmartAgent` | |
| `SuperAgent` | `SuperAgent` | |
| `ThirdAgent` | `ThirdAgent` | |
| `Tjaronchery10Agent` | `Tjaronchery10Agent` | |

??? info "API Reference - ANL 2022 Agents"
    ::: negmas_geniusweb_bridge.anl2022
        options:
          show_source: false
          members:
            - AGENTS
            - WRAPPED_AGENTS
            - AGENT_NOTES

---

## ANL 2023 Agents

Native Python agents from the Automated Negotiation League 2023.

| Agent | Wrapped Name | Notes |
|-------|--------------|-------|
| `AgentFO3` | `AgentFO3` | |
| `AmbitiousAgent` | `AmbitiousAgent` | |
| `AntAllianceAgent` | `AntAllianceAgent` | |
| `AntHeartAgent` | `AntHeartAgent` | |
| `ColmanAnacondotAgent2` | `ColmanAnacondotAgent2` | |
| `ExploitAgent` | `ExploitAgent` | |
| `GotAgent` | `GotAgent` | |
| `HybridAgent2023` | `HybridAgent2023` | |
| `KBTimeDiffAgent` | `KBTimeDiffAgent` | |
| `MiCRO2023` | `MiCRO2023` | |
| `MSCAgent` | `MSCAgent` | Requires `gym`, `torch`, `stable-baselines3` (optional) |
| `PopularAgent` | `PopularAgent` | |
| `SmartAgent` | `SmartAgent` | |
| `SpaghettiAgent` | `SpaghettiAgent` | |
| `TripleEAgent` | `TripleEAgent` | |

??? info "API Reference - ANL 2023 Agents"
    ::: negmas_geniusweb_bridge.anl2023
        options:
          show_source: false
          members:
            - AGENTS
            - WRAPPED_AGENTS

---

## CSE3210 Agents

Agents from the TU Delft CSE3210 Negotiation course (25 agents).

| Agent | Wrapped Name | Notes |
|-------|--------------|-------|
| `Agent2` | `Agent2` | |
| `Agent3` | `Agent3` | |
| `Agent7` | `Agent7` | |
| `Agent11` | `Agent11` | |
| `Agent14` | `Agent14` | |
| `Agent18` | `Agent18` | |
| `Agent19` | `Agent19` | |
| `Agent22` | `Agent22` | May throw scipy divide by zero |
| `Agent24` | `Agent24` | |
| `Agent25` | `Agent25` | |
| `Agent26` | `Agent26` | |
| `Agent27` | `Agent27` | |
| `Agent29` | `Agent29` | |
| `Agent32` | `Agent32` | |
| `Agent33` | `Agent33` | |
| `Agent41` | `Agent41` | |
| `Agent43` | `Agent43` | |
| `Agent50` | `Agent50` | |
| `Agent52` | `Agent52` | |
| `Agent55` | `Agent55` | |
| `Agent58` | `Agent58` | |
| `Agent61` | `Agent61` | |
| `Agent64` | `Agent64` | |
| `Agent67` | `Agent67` | |
| `Agent68` | `Agent68` | Issues with opening bid |

??? info "API Reference - CSE3210 Agents"
    ::: negmas_geniusweb_bridge.cse3210
        options:
          show_source: false
          members:
            - AGENTS
            - WRAPPED_AGENTS
            - AGENT_NOTES

---

## Using Wrapped Agents

All agents are available in two forms:

1. **Raw GeniusWeb agents** - Extend `DefaultParty`, for use with GeniusWeb infrastructure
2. **Wrapped negotiators** - Prefixed with `GW`, for use with NegMAS mechanisms

```python
# Import wrapped agents directly
from negmas_geniusweb_bridge import HammingAgent, ShineAgent

# Or import raw agents
from negmas_geniusweb_bridge.anac2020 import HammingAgent, ShineAgent

# Create wrapped negotiators
negotiator = HammingAgent(name="hamming")
```

## Agent Capabilities

All agents support:

- **Protocol**: SAOP (Stacked Alternating Offers Protocol)
- **Profile Types**: LinearAdditive utility functions

## Agent Dictionaries

Access all agents programmatically:

```python
from negmas_geniusweb_bridge import ALL_AGENTS, TRAINING_AGENTS, TESTING_AGENTS

# ALL_AGENTS contains all 82 wrapped agents
print(f"Total agents: {len(ALL_AGENTS)}")

# Access by name
agent_class = ALL_AGENTS["BoulwareAgent"]
negotiator = agent_class(name="boulware")

# List all available agents
for name in sorted(ALL_AGENTS.keys()):
    print(name)
```

??? info "API Reference - Main Module Dictionaries"
    ::: negmas_geniusweb_bridge
        options:
          show_source: false
          members:
            - ALL_AGENTS
            - TRAINING_AGENTS
            - TESTING_AGENTS
            - GENIUS_WEB_AVAILABLE
            - REGISTRY_AVAILABLE
