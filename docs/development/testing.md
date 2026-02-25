# Testing Guide

This guide covers testing practices for the negmas-geniusweb-bridge library.

## Running Tests

### Basic Commands

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_negmas_wrapper.py -v

# Run a specific test class
uv run pytest tests/test_negmas_wrapper.py::TestConversions -v

# Run a specific test method
uv run pytest tests/test_negmas_wrapper.py::TestConversions::test_convert_ufun_to_geniusweb -v
```

### Test Coverage

```bash
# Run with coverage report
uv run pytest --cov=negmas_geniusweb_bridge

# Generate HTML coverage report
uv run pytest --cov=negmas_geniusweb_bridge --cov-report=html
```

## Test Organization

Tests are organized by functionality:

```
tests/
└── test_negmas_wrapper.py
    ├── TestConversions        # Data conversion tests
    ├── TestGeniusWebNegotiator # Wrapper tests
    ├── TestNegotiationRuns    # Integration tests
    ├── TestCleanup            # Resource cleanup tests
    └── TestTranslatedAgents   # Translated agent tests
```

### Test Classes

#### TestConversions

Tests for data conversion functions:

```python
class TestConversions:
    def test_convert_ufun_to_geniusweb(self) -> None:
        """Test utility function conversion."""

    def test_outcome_bid_roundtrip(self) -> None:
        """Test outcome <-> bid conversion preserves data."""
```

#### TestGeniusWebNegotiator

Tests for the wrapper class:

```python
class TestGeniusWebNegotiator:
    def test_create_negotiator(self) -> None:
        """Test negotiator creation."""

    def test_create_with_factory(self) -> None:
        """Test factory-based creation."""
```

#### TestNegotiationRuns

Integration tests running full negotiations:

```python
class TestNegotiationRuns:
    def test_negotiation_reaches_agreement(self) -> None:
        """Test that agents can reach agreement."""

    def test_geniusweb_vs_geniusweb(self) -> None:
        """Test two GeniusWeb agents negotiating."""
```

#### TestTranslatedAgents

Tests for AI-translated agents:

```python
class TestTranslatedAgents:
    def test_hamming_agent_import(self) -> None:
        """Test HammingAgent can be imported."""

    def test_hamming_agent_negotiation(self) -> None:
        """Test HammingAgent in negotiation."""
```

## Writing Tests

### Test Structure

Follow this pattern for new tests:

```python
import pytest
from negmas import Issue, SAOMechanism
from negmas.preferences import LinearAdditiveUtilityFunction

from negmas_geniusweb_bridge import GeniusWebNegotiator


class TestMyFeature:
    """Tests for my feature."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        """Set up test fixtures."""
        self.issues = [
            Issue(name="price", values=["low", "medium", "high"]),
            Issue(name="quality", values=["basic", "premium"]),
        ]
        self.ufun = LinearAdditiveUtilityFunction(
            values={
                "price": {"low": 0.2, "medium": 0.5, "high": 1.0},
                "quality": {"basic": 0.3, "premium": 1.0},
            },
            weights={"price": 0.6, "quality": 0.4},
        )

    def test_feature_works(self) -> None:
        """Test that the feature works correctly."""
        # Arrange
        mechanism = SAOMechanism(issues=self.issues, n_steps=100)

        # Act
        result = some_function()

        # Assert
        assert result is not None
```

### Testing Agents

When testing a new agent:

```python
def test_my_agent_negotiation(self) -> None:
    """Test MyAgent can complete a negotiation."""
    from negmas_geniusweb_bridge.anac2020.my_agent import MyAgent

    mechanism = SAOMechanism(issues=self.issues, n_steps=100)

    n1 = GeniusWebNegotiator(geniusweb_agent_class=MyAgent, name="my_agent")
    n2 = GeniusWebNegotiator(
        geniusweb_agent_class=RandomAgent, name="random"
    )

    mechanism.add(n1, ufun=self.ufun1)
    mechanism.add(n2, ufun=self.ufun2)

    mechanism.run()

    # Verify negotiation completed
    assert mechanism.state.step > 0

    # Optionally check for agreement
    if mechanism.agreement is not None:
        assert mechanism.agreement in mechanism.outcomes
```

### Testing Imports

Verify agents can be imported correctly:

```python
def test_my_agent_import(self) -> None:
    """Test MyAgent can be imported."""
    from negmas_geniusweb_bridge.anac2020.my_agent import MyAgent

    assert MyAgent is not None
    assert hasattr(MyAgent, "notifyChange")
    assert hasattr(MyAgent, "getCapabilities")
```

### Testing Wrapped Agents

Test the `GW`-prefixed wrapped versions:

```python
def test_wrapped_my_agent(self) -> None:
    """Test GWMyAgent wrapper works."""
    from negmas_geniusweb_bridge import GWMyAgent

    mechanism = SAOMechanism(issues=self.issues, n_steps=100)

    # GWMyAgent is already a negotiator class
    n1 = GWMyAgent(name="my_agent")
    n2 = GWMyAgent(name="opponent")

    mechanism.add(n1, ufun=self.ufun1)
    mechanism.add(n2, ufun=self.ufun2)

    mechanism.run()
    assert mechanism.state.step > 0
```

## Common Issues

### Import Errors

If you see import errors for geniusweb modules, ensure:

1. Virtual environment is activated
2. Dependencies are installed: `uv sync`
3. You're running from the project root

### Timeout Issues

Some tests may take longer. Use pytest timeout:

```bash
uv run pytest --timeout=60
```

### Flaky Tests

Negotiation outcomes can vary. For deterministic tests:

1. Use fixed random seeds
2. Test behavior rather than specific outcomes
3. Allow for multiple valid results

```python
def test_agent_makes_progress(self) -> None:
    """Test agent makes progress (not specific outcome)."""
    mechanism.run()
    # Agent should make at least one offer
    assert mechanism.state.step > 0
```

## Continuous Integration

Tests run automatically on GitHub Actions for:

- Python 3.13
- All pushes and pull requests

See `.github/workflows/test.yml` for CI configuration.
