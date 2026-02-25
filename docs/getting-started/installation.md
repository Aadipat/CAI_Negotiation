# Installation

## Requirements

- Python 3.13 or higher
- NegMAS

## Using pip

```bash
pip install negmas-geniusweb-bridge
```

## Using uv (recommended)

```bash
uv add negmas-geniusweb-bridge
```

## From source

```bash
git clone https://github.com/yasserfarouk/negmas-geniusweb-bridge.git
cd negmas-geniusweb-bridge
uv sync
```

## Verifying Installation

```python
from negmas_geniusweb_bridge import HammingAgent
print("Installation successful!")
```

## Development Installation

For development, install with dev dependencies:

```bash
uv sync --group dev
```

This includes:

- pytest for testing
- mkdocs for documentation
- Other development tools
