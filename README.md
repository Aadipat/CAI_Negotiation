# negmas-geniusweb-bridge

A bridge that allows you to run [GeniusWeb](https://tracinsy.ewi.tudelft.nl/pubtrac/GeniusWeb) negotiation agents within [NegMAS](https://github.com/yasserfarouk/negmas) mechanisms.

## Official GeniusWeb Resources

This project builds upon the official GeniusWeb framework. For the original implementations:

- **GeniusWeb (Java)**: [https://gitlab.ewi.tudelft.nl/interactive-intelligence/geniusweb/geniusweb](https://gitlab.ewi.tudelft.nl/interactive-intelligence/geniusweb/geniusweb)
- **GeniusWeb (Python)**: [https://gitlab.ewi.tudelft.nl/interactive-intelligence/geniusweb/geniuswebpython](https://gitlab.ewi.tudelft.nl/interactive-intelligence/geniusweb/geniuswebpython)
- **GeniusWeb Project Home**: [https://gitlab.ewi.tudelft.nl/interactive-intelligence/geniusweb](https://gitlab.ewi.tudelft.nl/interactive-intelligence/geniusweb)

The official repositories contain:
- Complete GeniusWeb framework implementation (Java and Python)
- Competition agents from ANAC 2020-2023
- Documentation and examples

## AI-Assisted Development Disclaimer

**Important Notice**: Parts of this project were developed with AI assistance:

- **GeniusWeb-to-NegMAS Wrapper** (`wrapper.py`): The bridge wrapper that enables GeniusWeb agents to run in NegMAS mechanisms was developed in part using AI assistance.
- **Java-to-Python Translations**: The negotiation agents in the `anac2020/` and `anac2021/` directories were translated from their original Java implementations to Python using AI. These translations aim to preserve the original algorithms and strategies but may contain differences from the original implementations.

The original Python agents (in `basic/`, `anl2022/`, `anl2023/`, `cse3210/`) were written directly in Python by their original authors and are not AI-translated.

Users should be aware that AI-translated code may require additional validation for research or production use.

## Installation

```bash
uv sync
```

For local development with a local negmas installation:
```bash
uv sync && uv pip install -e ../negmas
```

## Usage

### Basic Example

Run a negotiation between a GeniusWeb agent and a NegMAS agent:

```python
from negmas import SAOMechanism, make_issue
from negmas.preferences import LinearAdditiveUtilityFunction
from negmas.sao import AspirationNegotiator

from negmas_geniusweb_bridge import BoulwareAgent

# Define the negotiation issues
issues = [make_issue(5, "price"), make_issue(3, "quality")]

# Create utility functions for each agent
ufun_a = LinearAdditiveUtilityFunction.random(issues=issues, normalized=True)
ufun_b = LinearAdditiveUtilityFunction.random(issues=issues, normalized=True)

# Create the negotiation mechanism
mechanism = SAOMechanism(issues=issues, n_steps=50)

# Create a GeniusWeb agent (Boulware strategy)
gw_agent = BoulwareAgent(ufun=ufun_a, name="geniusweb_boulware")

# Create a NegMAS agent (Aspiration strategy)
negmas_agent = AspirationNegotiator(ufun=ufun_b, name="aspiration")

# Add agents to the mechanism
mechanism.add(gw_agent)
mechanism.add(negmas_agent)

# Run the negotiation
mechanism.run()

# Check results
state = mechanism.state
print(f"Agreement: {state.agreement}")
print(f"Steps: {state.step}")
```

### GeniusWeb vs GeniusWeb

Run a negotiation between two GeniusWeb agents:

```python
from negmas import SAOMechanism, make_issue
from negmas.preferences import LinearAdditiveUtilityFunction

from negmas_geniusweb_bridge import BoulwareAgent, ConcederAgent

issues = [make_issue(10, "price"), make_issue(5, "quality"), make_issue(3, "delivery")]

ufun_a = LinearAdditiveUtilityFunction.random(issues=issues, normalized=True)
ufun_b = LinearAdditiveUtilityFunction.random(issues=issues, normalized=True)

mechanism = SAOMechanism(issues=issues, n_steps=100)

# Boulware agent (reluctant to concede)
agent_a = BoulwareAgent(ufun=ufun_a, name="boulware")

# Conceder agent (willing to concede quickly)
agent_b = ConcederAgent(ufun=ufun_b, name="conceder")

mechanism.add(agent_a)
mechanism.add(agent_b)
mechanism.run()

print(f"Agreement: {mechanism.state.agreement}")
```

### Using the Factory Function

Create reusable negotiator classes:

```python
from negmas_geniusweb_bridge.wrapper import make_geniusweb_negotiator
from negmas_geniusweb_bridge.basic.boulware_agent.boulware_agent import BoulwareAgent

# Create a reusable negotiator class
BoulwareNegotiator = make_geniusweb_negotiator(BoulwareAgent)

# Use it like any other NegMAS negotiator
negotiator = BoulwareNegotiator(ufun=my_ufun, name="boulware1")
```

## Available Agents

The bridge includes **82+ agents** from several GeniusWeb competitions. Each module exports:
- `AGENTS`: Dictionary of raw GeniusWeb party classes
- `WRAPPED_AGENTS`: Dictionary of NegMAS-wrapped negotiator classes (GW-prefixed)
- `AGENT_NOTES`: Known issues/notes about specific agents

### Agent Summary

| Module | Count | Type | Description |
|--------|-------|------|-------------|
| `basic` | 7 | Python Native | Reference implementations (Boulware, Conceder, Linear, etc.) |
| `anac2020` | 13 | AI-Translated | ANAC 2020 competition agents (from Java) |
| `anac2021` | 6 | AI-Translated | ANAC 2021 competition agents (from Java) |
| `anl2022` | 18 | Python Native | Automated Negotiation League 2022 |
| `anl2023` | 14 | Python Native | Automated Negotiation League 2023 |
| `cse3210` | 25 | Python Native | TU Delft CSE3210 course agents |
| **Total** | **82** | | |

### Basic Agents (7)

Reference implementations of classic negotiation strategies.

| Agent | Description | Notes |
|-------|-------------|-------|
| `BoulwareAgent` | Time-dependent concession (hardliner early, concedes late) | |
| `ConcederAgent` | Time-dependent concession (concedes early) | |
| `LinearAgent` | Linear concession over time | |
| `HardlinerAgent` | Never concedes | Only useful for testing |
| `RandomAgent` | Random bid selection | |
| `StupidAgent` | Simple random behavior | Test agent |
| `TimeDependentAgent` | Base class for time-dependent strategies | Configurable via `e` parameter |

### ANAC 2020 Agents (13) - AI-Translated from Java

Agents from the Automated Negotiating Agents Competition 2020. These were translated from Java using AI assistance.

| Agent | Protocol | Description |
|-------|----------|-------------|
| `AgentKT` | SHAOP/SAOP | COBYLA optimization with game-theoretic thresholds |
| `AgentP1DAMO` | SHAOP | Hill climbing with importance maps |
| `AgentXX` | SHAOP/SAOP | Importance maps with Nash point estimation |
| `AhBuNeAgent` | SHAOP | Similarity-based bidding with elicitation |
| `Anaconda` | SHAOP | Dynamic lower bounds with elicitation |
| `Angel` | SHAOP/SAOP | Heuristic opponent modeling with elicitation |
| `AzarAgent` | SHAOP/SAOP | GravityEs user model with frequency modeling |
| `BlingBling` | SHAOP/SAOP | RankNet neural network for preference learning |
| `DUOAgent` | SHAOP/SAOP | Linear regression for bid prediction |
| `ForArisa` | SAOP | Genetic algorithm for utility estimation |
| `HammingAgent` | SAOP | Hamming distance for opponent modeling |
| `NiceAgent` | SHAOP/SAOP | Elicitation with mirroring strategy |
| `ShineAgent` | SAOP | Adaptive agent with dynamic strategy |

### ANAC 2021 Agents (6) - AI-Translated from Java

Agents from the Automated Negotiating Agents Competition 2021. These were translated from Java using AI assistance.

| Agent | Protocol | Description |
|-------|----------|-------------|
| `AgentFO2021` | SAOP | Learning-based agent with time-dependent concession |
| `AlphaBIU` | SAOP | Frequency-based opponent modeling with two-phase strategy |
| `GamblerAgent` | SAOP | UCB Multi-Armed Bandit selecting among sub-agents |
| `MatrixAlienAgent` | SAOP | Adaptive boulware-style with multi-factor bid scoring |
| `TheDiceHaggler2021` | SAOP | Multi-phase strategy with Pareto estimation and TOPSIS |
| `TripleAgent` | SAOP | Frequency model and utility space analysis |

### ANL 2022 Agents (18) - Python Native

Agents from the Automated Negotiation League 2022. Written in Python by their original authors.

| Agent | Notes |
|-------|-------|
| `Agent007` | |
| `Agent4410` | |
| `AgentFish` | |
| `AgentFO2` | |
| `BIUAgent` | May timeout >60 secs on some domains |
| `ChargingBoul` | |
| `CompromisingAgent` | May cause "Action cannot be None" errors |
| `DreamTeam109Agent` | |
| `GEAAgent` | Slow execution (~1.5sec per turn) |
| `LearningAgent` | May cause "Action cannot be None" errors |
| `LuckyAgent2022` | |
| `MiCROAgent` | |
| `PinarAgent` | Requires `lightgbm` package (optional) |
| `ProcrastinAgent` | May have issues with first offer accepted |
| `RGAgent` | |
| `SmartAgent` | |
| `SuperAgent` | |
| `ThirdAgent` | |
| `Tjaronchery10Agent` | |

### ANL 2023 Agents (14) - Python Native

Agents from the Automated Negotiation League 2023. Written in Python by their original authors.

| Agent | Notes |
|-------|-------|
| `AgentFO3` | |
| `AmbitiousAgent` | |
| `AntAllianceAgent` | |
| `AntHeartAgent` | |
| `ColmanAnacondotAgent2` | |
| `ExploitAgent` | |
| `GotAgent` | |
| `HybridAgent2023` | |
| `KBTimeDiffAgent` | |
| `MiCRO2023` | |
| `MSCAgent` | Requires `gym`, `torch`, `stable-baselines3` (optional) |
| `PopularAgent` | |
| `SmartAgent` | |
| `SpaghettiAgent` | |
| `TripleEAgent` | |

### CSE3210 Agents (25) - Python Native

Agents from the TU Delft CSE3210 Negotiation course. Written in Python by students.

| Agent | Notes |
|-------|-------|
| `Agent2` - `Agent68` | 25 agents total |
| `Agent22` | May throw scipy divide by zero errors |
| `Agent68` | May have issues handling opening bid |

## Accessing Agents Programmatically

```python
# Import all agents from a module
from negmas_geniusweb_bridge.anac2020 import AGENTS, WRAPPED_AGENTS, AGENT_METADATA
from negmas_geniusweb_bridge.anac2021 import AGENTS, WRAPPED_AGENTS, AGENT_NOTES
from negmas_geniusweb_bridge.anl2022 import AGENTS, WRAPPED_AGENTS, AGENT_NOTES
from negmas_geniusweb_bridge.anl2023 import AGENTS, WRAPPED_AGENTS
from negmas_geniusweb_bridge.cse3210 import AGENTS, WRAPPED_AGENTS
from negmas_geniusweb_bridge.basic import AGENTS, WRAPPED_AGENTS

# Import all wrapped agents at once
from negmas_geniusweb_bridge import ALL_AGENTS

# List all available agents
print(list(ALL_AGENTS.keys()))

# Use a wrapped agent directly
from negmas_geniusweb_bridge import HammingAgent, BoulwareAgent
agent = HammingAgent(name="my_agent")
```

## Testing

```bash
# Run all tests
python -m pytest

# Run a specific test
python -m pytest tests/test_negmas_wrapper.py::TestNegotiationRuns::test_geniusweb_vs_geniusweb -v
```

## License

This software is licensed for **academic, research, and non-commercial use only**.

Commercial use requires a separate license. Contact the author for commercial licensing inquiries.

See [LICENSE](LICENSE) for full terms.
