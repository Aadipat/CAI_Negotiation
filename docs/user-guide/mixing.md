# Mixing Agents

One of the key features of negmas-geniusweb-bridge is the ability to mix GeniusWeb agents with native NegMAS agents in the same negotiation.

## Basic Example

```python
from negmas import SAOMechanism, make_issue, make_os
from negmas.sao import AspirationNegotiator
from negmas.preferences import LinearAdditiveUtilityFunction as U
from negmas_geniusweb_bridge import HammingAgent

# Create scenario
issues = [
    make_issue(name="price", values=10),
    make_issue(name="quantity", values=5),
]
outcome_space = make_os(issues)

# Create mechanism
mechanism = SAOMechanism(outcome_space=outcome_space, n_steps=100)

# Create utility functions
ufun1 = U.random(outcome_space=outcome_space)
ufun2 = U.random(outcome_space=outcome_space)

# Mix agents from different frameworks
mechanism.add(HammingAgent(name="geniusweb_agent"), ufun=ufun1)
mechanism.add(AspirationNegotiator(name="negmas_agent"), ufun=ufun2)

# Run
state = mechanism.run()
print(f"Agreement: {state.agreement}")
```

## Multi-Party Negotiations

You can mix multiple agents from both frameworks:

```python
from negmas import SAOMechanism, make_issue, make_os
from negmas.sao import AspirationNegotiator, NaiveTitForTatNegotiator
from negmas.preferences import LinearAdditiveUtilityFunction as U
from negmas_geniusweb_bridge import HammingAgent, ShineAgent

issues = [make_issue(name="x", values=10)]
outcome_space = make_os(issues)

mechanism = SAOMechanism(outcome_space=outcome_space, n_steps=100)

# Add agents from both frameworks
agents = [
    HammingAgent(name="hamming"),
    ShineAgent(name="shine"),
    AspirationNegotiator(name="aspiration"),
    NaiveTitForTatNegotiator(name="tft"),
]

for agent in agents:
    ufun = U.random(outcome_space=outcome_space)
    mechanism.add(agent, ufun=ufun)

state = mechanism.run()
```

## Considerations

### Utility Functions

Both GeniusWeb and NegMAS agents need utility functions. When using wrapped GeniusWeb agents, the utility function is automatically converted to the appropriate GeniusWeb format.

### Protocol Compatibility

The bridge currently supports the SAOP (Stacked Alternating Offers Protocol), which is the most common bilateral negotiation protocol.

### Performance

Wrapped GeniusWeb agents may have slightly higher overhead due to the translation layer, but this is typically negligible for most use cases.
