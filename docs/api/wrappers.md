# Wrapper Classes

This module provides wrapper classes that allow GeniusWeb agents to work seamlessly within NegMAS mechanisms.

## GeniusWebNegotiator

The main wrapper class that adapts GeniusWeb `DefaultParty` agents to work as NegMAS `SAONegotiator` instances.

::: negmas_geniusweb_bridge.wrapper.GeniusWebNegotiator
    options:
      show_source: true

## Factory Function

### make_geniusweb_negotiator

Create a reusable NegMAS-compatible negotiator class from a GeniusWeb party class.

::: negmas_geniusweb_bridge.wrapper.make_geniusweb_negotiator

## Usage Example

```python
from negmas import SAOMechanism, make_issue
from negmas.preferences import LinearAdditiveUtilityFunction
from negmas_geniusweb_bridge import BoulwareAgent
from negmas_geniusweb_bridge.wrapper import make_geniusweb_negotiator
from negmas_geniusweb_bridge.basic import RandomAgent

# Option 1: Use pre-wrapped agents directly
issues = [make_issue(5, "price"), make_issue(3, "quality")]
ufun = LinearAdditiveUtilityFunction.random(issues=issues, normalized=True)

mechanism = SAOMechanism(issues=issues, n_steps=100)
mechanism.add(BoulwareAgent(ufun=ufun, name="boulware"))

# Option 2: Create your own wrapped negotiator class
RandomAgent = make_geniusweb_negotiator(RandomAgent)
mechanism.add(RandomAgent(ufun=ufun, name="random"))

# Run the negotiation
mechanism.run()
```
