# negmas-geniusweb-bridge

A bridge that allows you to run GeniusWeb negotiation agents in NegMAS SAOMechanism(s).

## Overview

This library provides a seamless way to use negotiation agents originally developed for the [GeniusWeb](https://tracinsy.ewi.tudelft.nl/pubtrac/GeniusWeb) platform within [NegMAS](https://negmas.readthedocs.io/) (Negotiation Agents, Mechanisms, and Simulations).

## Official GeniusWeb Resources

This project builds upon the official GeniusWeb framework. For the original implementations:

- **GeniusWeb (Java)**: [https://gitlab.ewi.tudelft.nl/interactive-intelligence/geniusweb/geniusweb](https://gitlab.ewi.tudelft.nl/interactive-intelligence/geniusweb/geniusweb)
- **GeniusWeb (Python)**: [https://gitlab.ewi.tudelft.nl/interactive-intelligence/geniusweb/geniuswebpython](https://gitlab.ewi.tudelft.nl/interactive-intelligence/geniusweb/geniuswebpython)
- **GeniusWeb Project Home**: [https://gitlab.ewi.tudelft.nl/interactive-intelligence/geniusweb](https://gitlab.ewi.tudelft.nl/interactive-intelligence/geniusweb)

The official repositories contain the complete GeniusWeb framework implementation (Java and Python), competition agents from ANAC 2020-2023, and documentation.

## Features

- **84+ negotiation agents** from ANAC/ANL competitions (2020-2023) and TU Delft courses
- Run GeniusWeb agents in NegMAS negotiation mechanisms
- Mix GeniusWeb and native NegMAS agents in the same negotiation
- Simple GW-prefixed wrapper classes for easy integration
- Comprehensive metadata and notes for each agent

## Quick Start

```python
from negmas import SAOMechanism, make_issue
from negmas.preferences import LinearAdditiveUtilityFunction
from negmas.sao import AspirationNegotiator

from negmas_geniusweb_bridge import BoulwareAgent

# Create a negotiation scenario
issues = [make_issue(name="price", values=10), make_issue(name="quantity", values=5)]
ufun_a = LinearAdditiveUtilityFunction.random(issues=issues, normalized=True)
ufun_b = LinearAdditiveUtilityFunction.random(issues=issues, normalized=True)

mechanism = SAOMechanism(issues=issues, n_steps=100)

# Add a wrapped GeniusWeb agent
mechanism.add(BoulwareAgent(ufun=ufun_a, name="gw_agent"))

# Add a NegMAS agent
mechanism.add(AspirationNegotiator(ufun=ufun_b, name="negmas_agent"))

# Run the negotiation
mechanism.run()

print(f"Agreement: {mechanism.state.agreement}")
```

## Agent Summary

| Module | Count | Type | Description |
|--------|-------|------|-------------|
| `basic` | 7 | Python Native | Reference implementations |
| `anac2020` | 13 | AI-Translated | ANAC 2020 competition (from Java) |
| `anac2021` | 6 | AI-Translated | ANAC 2021 competition (from Java) |
| `anl2022` | 19 | Python Native | ANL 2022 competition |
| `anl2023` | 14 | Python Native | ANL 2023 competition |
| `cse3210` | 25 | Python Native | TU Delft course agents |
| **Total** | **84** | | |

## Installation

```bash
pip install negmas-geniusweb-bridge
```

Or with uv:

```bash
uv add negmas-geniusweb-bridge
```

## Documentation

- [Getting Started](getting-started/installation.md) - Installation and setup
- [User Guide](user-guide/agents.md) - Available agents and usage patterns
- [API Reference](api/wrappers.md) - Detailed API documentation
- [Development](development/contributing.md) - Contributing guidelines

## AI-Assisted Development Disclaimer

!!! warning "AI-Translated Code"
    The agents in `anac2020/` and `anac2021/` directories were translated from Java to Python using AI assistance. These translations aim to preserve the original algorithms but may contain differences from the original implementations.

The original Python agents (in `basic/`, `anl2022/`, `anl2023/`, `cse3210/`) were written directly in Python by their original authors and are not AI-translated.

## License

This software is licensed for academic, research, and non-commercial use only. See [LICENSE](https://github.com/yasserfarouk/negmas-geniusweb-bridge/blob/main/LICENSE) for details.
