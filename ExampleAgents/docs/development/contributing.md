# Contributing Guide

Thank you for your interest in contributing to negmas-geniusweb-bridge!

## Development Setup

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager

### Installation

```bash
# Clone the repository
git clone https://github.com/yasserfarouk/negmas-geniusweb-bridge.git
cd negmas-geniusweb-bridge

# Install dependencies
uv sync

# Install docs dependencies (optional)
uv sync --group docs
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run a specific test
uv run pytest tests/test_negmas_wrapper.py::TestConversions::test_convert_ufun_to_geniusweb -v
```

### Building Documentation

```bash
# Serve docs locally
uv run mkdocs serve

# Build docs
uv run mkdocs build
```

## Code Style

### Formatting

- Use double quotes for strings
- 4-space indentation
- Line length: 88 characters (Black default)

### Type Hints

All function signatures must include type hints:

```python
def process_bid(bid: Bid, threshold: float) -> bool:
    """Process a bid against a threshold."""
    return bid.utility >= threshold
```

### Imports

Organize imports in this order:

1. Standard library
2. Third-party packages (geniusweb, negmas, numpy)
3. Local imports

```python
from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
from geniusweb.actions.Accept import Accept
from geniusweb.party.DefaultParty import DefaultParty

from ..utils import SimpleLinearOrdering

if TYPE_CHECKING:
    from geniusweb.issuevalue.Domain import Domain
```

### Docstrings

Use Google-style docstrings:

```python
def calculate_utility(bid: Bid, weights: dict[str, float]) -> float:
    """Calculate the utility of a bid.

    Args:
        bid: The bid to evaluate.
        weights: Issue weights for utility calculation.

    Returns:
        The calculated utility value between 0 and 1.

    Raises:
        ValueError: If bid contains unknown issues.
    """
    ...
```

## Adding New Agents

### Translating Java Agents

When translating a Java GeniusWeb agent to Python:

1. Create a new directory under the appropriate package:
   ```
   src/negmas_geniusweb_bridge/anac2020/my_agent/
   ```

2. Create the agent file with proper docstring:
   ```python
   """
   MyAgent - Brief description.

   This agent was translated from the original Java implementation.
   Translation was performed using AI assistance.

   Original strategy:
   - Point 1
   - Point 2
   """
   ```

3. Extend `DefaultParty` and implement `notifyChange`:
   ```python
   class MyAgent(DefaultParty):
       def notifyChange(self, info: Inform) -> None:
           ...
   ```

4. Create `__init__.py`:
   ```python
   from .my_agent import MyAgent

   __all__ = ["MyAgent"]
   ```

5. Register in parent `__init__.py`:
   ```python
   AGENTS["MyAgent"] = MyAgent
   WRAPPED_AGENTS["GWMyAgent"] = create_gw_negotiator(MyAgent)
   ```

6. Add tests for the new agent

### Testing New Agents

Add tests to verify:

1. Agent can be imported
2. Agent can negotiate (reaches agreement or respects protocol)
3. Wrapped version works with NegMAS

```python
def test_my_agent_negotiation(self) -> None:
    """Test MyAgent in a negotiation."""
    from negmas_geniusweb_bridge.anac2020.my_agent import MyAgent

    mechanism = SAOMechanism(issues=self.issues, n_steps=100)
    n1 = GeniusWebNegotiator(geniusweb_agent_class=MyAgent)
    n2 = GeniusWebNegotiator(geniusweb_agent_class=RandomAgent)

    mechanism.add(n1, ufun=self.ufun1)
    mechanism.add(n2, ufun=self.ufun2)

    mechanism.run()
    # Agent should complete negotiation
    assert mechanism.state.step > 0
```

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with appropriate tests
3. Ensure all tests pass: `uv run pytest`
4. Update documentation if needed
5. Submit a pull request with a clear description

## Questions?

Open an issue on GitHub for questions or discussions.
