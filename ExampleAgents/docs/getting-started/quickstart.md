# Quick Start

This guide will help you get started with using GeniusWeb agents in NegMAS negotiations.

## Basic Usage

### Creating a Simple Negotiation

```python
from negmas import SAOMechanism, make_issue, make_os
from negmas.preferences import LinearAdditiveUtilityFunction as U
from negmas_geniusweb_bridge import HammingAgent, ShineAgent

# Define the negotiation issues
issues = [
    make_issue(name="price", values=10),
    make_issue(name="quantity", values=5),
    make_issue(name="delivery", values=["fast", "standard", "slow"]),
]

# Create the outcome space
outcome_space = make_os(issues)

# Create the mechanism
mechanism = SAOMechanism(
    outcome_space=outcome_space,
    n_steps=100,
)

# Create utility functions for each agent
ufun1 = U.random(outcome_space=outcome_space)
ufun2 = U.random(outcome_space=outcome_space)

# Add agents with their utility functions
mechanism.add(HammingAgent(name="hamming"), ufun=ufun1)
mechanism.add(ShineAgent(name="shine"), ufun=ufun2)

# Run the negotiation
state = mechanism.run()

# Check the result
if state.agreement:
    print(f"Agreement reached: {state.agreement}")
else:
    print("No agreement reached")
```

### Mixing with Native NegMAS Agents

```python
from negmas import SAOMechanism, make_issue, make_os
from negmas.sao import AspirationNegotiator
from negmas.preferences import LinearAdditiveUtilityFunction as U
from negmas_geniusweb_bridge import HammingAgent

# Create scenario
issues = [make_issue(name="x", values=10)]
outcome_space = make_os(issues)

# Create mechanism
mechanism = SAOMechanism(outcome_space=outcome_space, n_steps=50)

# Add both GeniusWeb and NegMAS agents
ufun1 = U.random(outcome_space=outcome_space)
ufun2 = U.random(outcome_space=outcome_space)

mechanism.add(HammingAgent(name="gw_agent"), ufun=ufun1)
mechanism.add(AspirationNegotiator(name="negmas_agent"), ufun=ufun2)

# Run
state = mechanism.run()
```

## Available Agents

The bridge includes agents from various competitions:

### ANAC 2020
- `HammingAgent` - Uses Hamming distance for bid evaluation
- `ShineAgent` - Adaptive bidding strategy

### ANL 2022
- Various agents from the Automated Negotiation League

### ANL 2023
- Latest competition agents

See the [Available Agents](../user-guide/agents.md) page for a complete list.

## Next Steps

- Learn about [all available agents](../user-guide/agents.md)
- See how to [mix agents from different frameworks](../user-guide/mixing.md)
- Run [tournaments](../user-guide/tournaments.md) with multiple agents
