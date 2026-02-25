# Available Agents

This page lists all 80+ negotiation agents available through the negmas-geniusweb-bridge.

## Naming Convention

- **Raw agents** (GeniusWeb DefaultParty classes): `AgentName` (e.g., `HammingAgent`)
- **Wrapped agents** (NegMAS-compatible): `GWAgentName` (e.g., `HammingAgent`)

## Agent Modules

| Module | Count | Type | Description |
|--------|-------|------|-------------|
| `basic` | 7 | Python Native | Reference implementations |
| `anac2020` | 13 | AI-Translated | ANAC 2020 competition (from Java) |
| `anac2021` | 6 | AI-Translated | ANAC 2021 competition (from Java) |
| `anl2022` | 18 | Python Native | ANL 2022 competition |
| `anl2023` | 14 | Python Native | ANL 2023 competition |
| `cse3210` | 25 | Python Native | TU Delft course agents |

---

## Basic Agents (7) - Python Native

Reference implementations of classic negotiation strategies.

| Agent | Wrapped Name | Description |
|-------|--------------|-------------|
| `BoulwareAgent` | `BoulwareAgent` | Time-dependent concession (hardliner early, concedes late) |
| `ConcederAgent` | `ConcederAgent` | Time-dependent concession (concedes early) |
| `LinearAgent` | `LinearAgent` | Linear concession over time |
| `HardlinerAgent` | `HardlinerAgent` | Never concedes (testing only) |
| `RandomAgent` | `RandomAgent` | Random bid selection |
| `StupidAgent` | `StupidAgent` | Simple random behavior (test agent) |
| `TimeDependentAgent` | `TimeDependentAgent` | Base class with configurable `e` parameter |

---

## ANAC 2020 Agents (13) - AI-Translated from Java

Agents from the Automated Negotiating Agents Competition 2020.

!!! warning "AI-Translated"
    These agents were translated from Java using AI assistance. They may contain differences from the original implementations.

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

---

## ANAC 2021 Agents (6) - AI-Translated from Java

Agents from the Automated Negotiating Agents Competition 2021.

!!! warning "AI-Translated"
    These agents were translated from Java using AI assistance. They may contain differences from the original implementations.

| Agent | Wrapped Name | Description |
|-------|--------------|-------------|
| `AgentFO2021` | `AgentFO2021` | Learning-based agent with time-dependent concession |
| `AlphaBIU` | `AlphaBIU` | Frequency-based opponent modeling with two-phase strategy |
| `GamblerAgent` | `GamblerAgent` | UCB Multi-Armed Bandit selecting among sub-agents |
| `MatrixAlienAgent` | `MatrixAlienAgent` | Adaptive boulware-style agent with multi-factor scoring |
| `TheDiceHaggler2021` | `TheDiceHaggler2021` | Multi-phase time-dependent strategy with TOPSIS |
| `TripleAgent` | `TripleAgent` | Frequency model and utility space analysis |

---

## ANL 2022 Agents (18) - Python Native

Agents from the Automated Negotiation League 2022.

| Agent | Wrapped Name | Notes |
|-------|--------------|-------|
| `Agent007` | `Agent007` | |
| `Agent4410` | `Agent4410` | |
| `AgentFish` | `AgentFish` | |
| `AgentFO2` | `AgentFO2` | |
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

---

## ANL 2023 Agents (14) - Python Native

Agents from the Automated Negotiation League 2023.

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

---

## CSE3210 Agents (25) - Python Native

Agents from the TU Delft CSE3210 Negotiation course.

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

---

## Usage Examples

### Using a Single Agent

```python
from negmas import SAOMechanism, make_issue
from negmas.preferences import LinearAdditiveUtilityFunction

from negmas_geniusweb_bridge.anac2020 import HammingAgent

issues = [make_issue(10, "price"), make_issue(5, "quality")]
ufun = LinearAdditiveUtilityFunction.random(issues=issues, normalized=True)

mechanism = SAOMechanism(issues=issues, n_steps=50)
mechanism.add(HammingAgent(ufun=ufun, name="agent1"))
# Add another agent...
mechanism.run()
```

### Accessing All Agents from a Module

```python
from negmas_geniusweb_bridge.anac2020 import AGENTS, WRAPPED_AGENTS, AGENT_METADATA
from negmas_geniusweb_bridge.anl2022 import AGENTS, WRAPPED_AGENTS, AGENT_NOTES

# List all available agents
print(list(AGENTS.keys()))  # Raw GeniusWeb agents
print(list(WRAPPED_AGENTS.keys()))  # NegMAS-wrapped agents

# Get metadata about an agent (ANAC 2020 only)
info = AGENT_METADATA["HammingAgent"]
print(info["description"])
print(info["tags"])  # ['AI-translated', 'SAOP']
```

### Creating Custom Wrapped Agents

```python
from negmas_geniusweb_bridge.wrapper import make_geniusweb_negotiator
from negmas_geniusweb_bridge.basic.boulware_agent.boulware_agent import BoulwareAgent

# Create a reusable negotiator class
BoulwareNegotiator = make_geniusweb_negotiator(BoulwareAgent)

# Use it like any other NegMAS negotiator
negotiator = BoulwareNegotiator(ufun=my_ufun, name="boulware1")
```

### Checking Optional Agent Availability

```python
from negmas_geniusweb_bridge.anl2022 import PINAR_AGENT_AVAILABLE, PinarAgent
from negmas_geniusweb_bridge.anl2023 import MSC_AGENT_AVAILABLE, MSCAgent

if PINAR_AGENT_AVAILABLE:
    print("PinarAgent is available (lightgbm installed)")
else:
    print("PinarAgent not available (install lightgbm)")

if MSC_AGENT_AVAILABLE:
    print("MSCAgent is available (gym/torch/stable-baselines3 installed)")
else:
    print("MSCAgent not available")
```
