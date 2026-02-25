# Running Tournaments

You can use NegMAS tournament functionality to compare GeniusWeb agents against each other or against native NegMAS agents.

## Basic Tournament

```python
from negmas import SAOMechanism, make_issue, make_os
from negmas.preferences import LinearAdditiveUtilityFunction as U
from negmas_geniusweb_bridge import HammingAgent, ShineAgent

def run_tournament():
    """Run a simple tournament between agents."""
    results = []
    
    for round_num in range(10):
        # Create scenario
        issues = [
            make_issue(name="price", values=10),
            make_issue(name="quantity", values=5),
        ]
        outcome_space = make_os(issues)
        
        # Create mechanism
        mechanism = SAOMechanism(
            outcome_space=outcome_space,
            n_steps=100,
        )
        
        # Random utility functions
        ufun1 = U.random(outcome_space=outcome_space)
        ufun2 = U.random(outcome_space=outcome_space)
        
        # Add agents
        mechanism.add(HammingAgent(name="hamming"), ufun=ufun1)
        mechanism.add(ShineAgent(name="shine"), ufun=ufun2)
        
        # Run
        state = mechanism.run()
        
        # Record results
        if state.agreement:
            results.append({
                "round": round_num,
                "agreement": state.agreement,
                "utility_hamming": float(ufun1(state.agreement)),
                "utility_shine": float(ufun2(state.agreement)),
            })
        else:
            results.append({
                "round": round_num,
                "agreement": None,
                "utility_hamming": 0,
                "utility_shine": 0,
            })
    
    return results

# Run tournament
results = run_tournament()
for r in results:
    print(r)
```

## Using NegMAS Tournament Infrastructure

For more sophisticated tournaments, use NegMAS's built-in tournament functionality:

```python
from negmas.tournaments import tournament
from negmas_geniusweb_bridge import HammingAgent, ShineAgent

# Define agent types
agent_types = [HammingAgent, ShineAgent]

# Run tournament (simplified example)
# See NegMAS documentation for full tournament API
```

## Comparing with NegMAS Agents

```python
from negmas.sao import AspirationNegotiator
from negmas_geniusweb_bridge import HammingAgent

# Mix GeniusWeb and NegMAS agents in tournament
agent_types = [
    HammingAgent,
    AspirationNegotiator,
]

# Run comparative tournament
```

## Analyzing Results

```python
import pandas as pd

# Convert results to DataFrame for analysis
df = pd.DataFrame(results)

# Calculate statistics
print(f"Agreement rate: {df['agreement'].notna().mean():.2%}")
print(f"Average utility (Hamming): {df['utility_hamming'].mean():.3f}")
print(f"Average utility (Shine): {df['utility_shine'].mean():.3f}")
```
