# Architecture

This document describes the architecture of the negmas-geniusweb-bridge library.

## Overview

The bridge connects two negotiation frameworks:

- **NegMAS** - A Python framework for multi-agent simulations
- **GeniusWeb** - A Java/Python framework for automated negotiation

```
┌─────────────────────────────────────────────────────────────┐
│                      NegMAS                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ SAOMechanism│  │   Issues    │  │   UFuns     │         │
│  └──────┬──────┘  └─────────────┘  └─────────────┘         │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           GeniusWebNegotiator (wrapper.py)          │   │
│  │                                                     │   │
│  │  - Converts NegMAS outcomes <-> GeniusWeb Bids     │   │
│  │  - Converts NegMAS UFuns <-> GeniusWeb Profiles    │   │
│  │  - Manages temporary profile files                  │   │
│  │  - Handles protocol translation                     │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                    │
└─────────────────────────┼────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     GeniusWeb                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │DefaultParty │  │    Bids     │  │  Profiles   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              GeniusWeb Agents                        │   │
│  │  - ANAC 2020/2021 (translated from Java)            │   │
│  │  - ANL 2022/2023 (native Python)                    │   │
│  │  - CSE3210 course agents                            │   │
│  │  - Basic reference agents                            │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### GeniusWebNegotiator

The `GeniusWebNegotiator` class in `wrapper.py` is the core adapter:

```python
class GeniusWebNegotiator(SAONegotiator):
    """Wraps a GeniusWeb DefaultParty for use in NegMAS."""
```

**Responsibilities:**

1. **Lifecycle Management** - Creates and initializes GeniusWeb agents
2. **Protocol Translation** - Converts SAOP protocol messages
3. **Data Conversion** - Transforms bids, outcomes, and utility functions
4. **File Management** - Handles temporary profile files

### Data Conversion Layer

The bridge converts between frameworks:

| NegMAS | GeniusWeb |
|--------|-----------|
| `Outcome` | `Bid` |
| `Issue` | Issue in `Domain` |
| `LinearAdditiveUtilityFunction` | `LinearAdditive` profile |
| `SAOMechanism` | SAOP protocol |

Key functions:

- `outcome_to_bid()` - Convert NegMAS outcome to GeniusWeb Bid
- `bid_to_outcome()` - Convert GeniusWeb Bid to NegMAS outcome
- `ufun_to_geniusweb()` - Convert NegMAS utility function to GeniusWeb profile

### Agent Categories

Agents are organized by source:

```
src/negmas_geniusweb_bridge/
├── basic/           # Reference implementations
├── anac2020/        # AI-translated from Java (ANAC 2020)
├── anac2021/        # AI-translated from Java (ANAC 2021)
├── ai2020/          # AI-translated from Java (AI course)
├── anl2022/         # Native Python (ANL 2022)
├── anl2023/         # Native Python (ANL 2023)
├── cse3210/         # Native Python (TU Delft course)
└── wrapper.py       # Core wrapper class
```

## Protocol Flow

### Negotiation Initialization

```
1. NegMAS creates SAOMechanism
2. GeniusWebNegotiator added to mechanism
3. Wrapper creates temporary profile file
4. Wrapper instantiates GeniusWeb agent
5. Settings info sent to agent
```

### Turn Execution

```
1. NegMAS calls negotiator.propose() or negotiator.respond()
2. Wrapper sends YourTurn to GeniusWeb agent
3. Agent processes and returns Action
4. Wrapper intercepts action via connection
5. Wrapper converts Bid to Outcome
6. Response returned to NegMAS
```

### Message Flow Diagram

```
NegMAS                    Wrapper                    GeniusWeb Agent
  │                         │                              │
  │──propose()──────────────▶                              │
  │                         │──YourTurn info──────────────▶│
  │                         │                              │
  │                         │◀─────────Offer action────────│
  │                         │                              │
  │◀────Outcome─────────────│                              │
  │                         │                              │
  │──respond(bid)───────────▶                              │
  │                         │──ActionDone(opponent bid)───▶│
  │                         │──YourTurn info──────────────▶│
  │                         │                              │
  │                         │◀────Accept/Offer action──────│
  │◀────ResponseType────────│                              │
```

## Vendored Dependencies

The library vendors GeniusWeb and its dependencies:

```
vendor/
├── geniusweb-1.2.1/     # Main GeniusWeb library
└── others/
    ├── pyson/           # JSON handling
    ├── tudelft_utilities/
    ├── tudelft_utilities_logging/
    └── uri/
```

This ensures:

- Consistent versions across installations
- No dependency conflicts
- Offline availability

## Extension Points

### Adding New Agent Sources

1. Create a new package under `src/negmas_geniusweb_bridge/`
2. Implement agents extending `DefaultParty`
3. Create `__init__.py` with `AGENTS` and `WRAPPED_AGENTS` dicts
4. Import in main `__init__.py`

### Custom Wrappers

For specialized behavior, extend `GeniusWebNegotiator`:

```python
class MyCustomWrapper(GeniusWebNegotiator):
    def on_partner_proposal(self, state, partner, offer):
        # Custom logic before passing to agent
        super().on_partner_proposal(state, partner, offer)
```
