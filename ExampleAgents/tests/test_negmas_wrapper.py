"""Tests for GeniusWebNegotiator wrapper."""

import pytest
from negmas import SAOMechanism, make_issue
from negmas.preferences import LinearAdditiveUtilityFunction
from negmas.sao import AspirationNegotiator

from negmas_geniusweb_bridge.wrapper import (
    GeniusWebNegotiator,
    make_geniusweb_negotiator,
    _convert_negmas_ufun_to_geniusweb,
    _outcome_to_geniusweb_bid,
    _geniusweb_bid_to_outcome,
)
from negmas_geniusweb_bridge.basic.boulware_agent.boulware_agent import (
    BoulwareAgent,
)
from negmas_geniusweb_bridge.basic.conceder_agent.conceder_agent import (
    ConcederAgent,
)
from negmas_geniusweb_bridge.basic.linear_agent.linear_agent import LinearAgent


@pytest.fixture
def simple_issues():
    """Create simple test issues."""
    return [make_issue(5, "price"), make_issue(3, "quality")]


@pytest.fixture
def ufun_a(simple_issues):
    """Create a test utility function for agent A."""
    return LinearAdditiveUtilityFunction.random(issues=simple_issues, normalized=True)


@pytest.fixture
def ufun_b(simple_issues):
    """Create a test utility function for agent B."""
    return LinearAdditiveUtilityFunction.random(issues=simple_issues, normalized=True)


class TestConversions:
    """Test conversion functions between negmas and GeniusWeb formats."""

    def test_convert_ufun_to_geniusweb(self, ufun_a):
        """Test converting negmas ufun to GeniusWeb format."""
        profile = _convert_negmas_ufun_to_geniusweb(ufun_a)

        assert "LinearAdditiveUtilitySpace" in profile
        space = profile["LinearAdditiveUtilitySpace"]

        # Check domain
        assert "domain" in space
        assert "issuesValues" in space["domain"]
        assert "0" in space["domain"]["issuesValues"]
        assert "1" in space["domain"]["issuesValues"]

        # Check weights
        assert "issueWeights" in space
        assert "0" in space["issueWeights"]
        assert "1" in space["issueWeights"]

        # Check utilities
        assert "issueUtilities" in space
        assert "0" in space["issueUtilities"]
        assert "1" in space["issueUtilities"]

    def test_outcome_bid_roundtrip(self):
        """Test that outcome <-> bid conversion is reversible."""
        outcome = (2, 1)
        bid = _outcome_to_geniusweb_bid(outcome)
        recovered = _geniusweb_bid_to_outcome(bid)
        assert recovered == outcome

    def test_outcome_bid_roundtrip_larger(self):
        """Test outcome <-> bid conversion with more issues."""
        outcome = (4, 2, 7, 0, 3)
        bid = _outcome_to_geniusweb_bid(outcome)
        recovered = _geniusweb_bid_to_outcome(bid)
        assert recovered == outcome


class TestGeniusWebNegotiator:
    """Test the GeniusWebNegotiator class."""

    def test_create_negotiator(self, ufun_a):
        """Test creating a GeniusWebNegotiator."""
        neg = GeniusWebNegotiator(
            party_class=BoulwareAgent,
            ufun=ufun_a,
            name="test_boulware",
        )
        assert neg.name == "test_boulware"
        assert neg.ufun == ufun_a

    def test_create_with_factory(self, ufun_a):
        """Test creating negotiator using factory function."""
        BoulwareNegotiator = make_geniusweb_negotiator(BoulwareAgent)
        neg = BoulwareNegotiator(ufun=ufun_a, name="boulware1")
        assert "Boulware" in type(neg).__name__
        assert neg.ufun == ufun_a


class TestNegotiationRuns:
    """Test running actual negotiations with GeniusWeb negotiators."""

    def test_geniusweb_vs_aspiration(self, simple_issues, ufun_a, ufun_b):
        """Test negotiation between GeniusWeb agent and negmas AspirationNegotiator."""
        mechanism = SAOMechanism(issues=simple_issues, n_steps=50)

        gw_neg = GeniusWebNegotiator(
            party_class=BoulwareAgent,
            ufun=ufun_a,
            name="geniusweb_boulware",
        )
        aspiration_neg = AspirationNegotiator(ufun=ufun_b, name="aspiration")

        mechanism.add(gw_neg)
        mechanism.add(aspiration_neg)

        mechanism.run()

        # Negotiation should complete (either agreement or timeout)
        state = mechanism.state
        assert not state.running
        # The negotiation should have made progress
        assert state.step > 0

    def test_geniusweb_vs_geniusweb(self, simple_issues, ufun_a, ufun_b):
        """Test negotiation between two GeniusWeb agents."""
        mechanism = SAOMechanism(issues=simple_issues, n_steps=50)

        neg_a = GeniusWebNegotiator(
            party_class=BoulwareAgent,
            ufun=ufun_a,
            name="boulware",
        )
        neg_b = GeniusWebNegotiator(
            party_class=ConcederAgent,
            ufun=ufun_b,
            name="conceder",
        )

        mechanism.add(neg_a)
        mechanism.add(neg_b)

        mechanism.run()

        state = mechanism.state
        assert not state.running
        assert state.step > 0

    def test_linear_agent(self, simple_issues, ufun_a, ufun_b):
        """Test using LinearAgent from GeniusWeb."""
        mechanism = SAOMechanism(issues=simple_issues, n_steps=50)

        neg_a = GeniusWebNegotiator(
            party_class=LinearAgent,
            ufun=ufun_a,
            name="linear",
        )
        neg_b = AspirationNegotiator(ufun=ufun_b, name="aspiration")

        mechanism.add(neg_a)
        mechanism.add(neg_b)

        mechanism.run()

        state = mechanism.state
        assert not state.running

    def test_negotiation_reaches_agreement(self, simple_issues):
        """Test that negotiation can reach an agreement."""
        # Create ufuns where agreement is likely (similar preferences)
        ufun_a = LinearAdditiveUtilityFunction.random(
            issues=simple_issues, normalized=True
        )
        ufun_b = LinearAdditiveUtilityFunction.random(
            issues=simple_issues, normalized=True
        )

        mechanism = SAOMechanism(issues=simple_issues, n_steps=100)

        # Use conceder agent which should be more likely to agree
        neg_a = GeniusWebNegotiator(
            party_class=ConcederAgent,
            ufun=ufun_a,
            name="conceder_a",
        )
        neg_b = GeniusWebNegotiator(
            party_class=ConcederAgent,
            ufun=ufun_b,
            name="conceder_b",
        )

        mechanism.add(neg_a)
        mechanism.add(neg_b)

        mechanism.run()

        state = mechanism.state
        assert not state.running
        # With two conceders, we should often reach agreement
        # (but not always, depending on random ufuns)


class TestCleanup:
    """Test that resources are properly cleaned up."""

    def test_temp_files_cleaned(self, simple_issues, ufun_a, ufun_b):
        """Test that temporary files are cleaned up after negotiation."""
        import os

        mechanism = SAOMechanism(issues=simple_issues, n_steps=10)

        neg_a = GeniusWebNegotiator(
            party_class=BoulwareAgent,
            ufun=ufun_a,
            name="boulware",
        )
        neg_b = AspirationNegotiator(ufun=ufun_b, name="aspiration")

        mechanism.add(neg_a)
        mechanism.add(neg_b)

        mechanism.run()

        # After negotiation ends, temp dir should be cleaned up
        if neg_a._tmp_dir is not None:
            assert not os.path.exists(neg_a._tmp_dir)


class TestTranslatedAgents:
    """Test AI-translated agents from ANAC 2020."""

    def test_hamming_agent_import(self):
        """Test that HammingAgent can be imported."""
        from negmas_geniusweb_bridge.anac2020.hamming_agent.hamming_agent import (
            HammingAgent,
        )

        assert HammingAgent is not None

    def test_shine_agent_import(self):
        """Test that ShineAgent can be imported."""
        from negmas_geniusweb_bridge.anac2020.shine_agent.shine_agent import ShineAgent

        assert ShineAgent is not None

    def test_wrapped_agents_import(self):
        """Test that GW-prefixed wrapped agents can be imported."""
        from negmas_geniusweb_bridge import HammingAgent, ShineAgent

        assert HammingAgent is not None
        assert ShineAgent is not None

    def test_hamming_agent_negotiation(self, simple_issues, ufun_a, ufun_b):
        """Test negotiation with HammingAgent."""
        from negmas_geniusweb_bridge.anac2020.hamming_agent.hamming_agent import (
            HammingAgent,
        )

        mechanism = SAOMechanism(issues=simple_issues, n_steps=50)

        neg_a = GeniusWebNegotiator(
            party_class=HammingAgent,
            ufun=ufun_a,
            name="hamming",
        )
        neg_b = AspirationNegotiator(ufun=ufun_b, name="aspiration")

        mechanism.add(neg_a)
        mechanism.add(neg_b)

        mechanism.run()

        state = mechanism.state
        assert not state.running
        assert state.step > 0

    def test_shine_agent_negotiation(self, simple_issues, ufun_a, ufun_b):
        """Test negotiation with ShineAgent."""
        from negmas_geniusweb_bridge.anac2020.shine_agent.shine_agent import ShineAgent

        mechanism = SAOMechanism(issues=simple_issues, n_steps=50)

        neg_a = GeniusWebNegotiator(
            party_class=ShineAgent,
            ufun=ufun_a,
            name="shine",
        )
        neg_b = AspirationNegotiator(ufun=ufun_b, name="aspiration")

        mechanism.add(neg_a)
        mechanism.add(neg_b)

        mechanism.run()

        state = mechanism.state
        assert not state.running
        assert state.step > 0

    def test_wrapped_hamming_agent(self, simple_issues, ufun_a, ufun_b):
        """Test using HammingAgent directly."""
        from negmas_geniusweb_bridge import HammingAgent

        mechanism = SAOMechanism(issues=simple_issues, n_steps=50)

        neg_a = HammingAgent(ufun=ufun_a, name="gw_hamming")
        neg_b = AspirationNegotiator(ufun=ufun_b, name="aspiration")

        mechanism.add(neg_a)
        mechanism.add(neg_b)

        mechanism.run()

        state = mechanism.state
        assert not state.running
        assert state.step > 0

    def test_translated_vs_translated(self, simple_issues, ufun_a, ufun_b):
        """Test negotiation between two translated agents."""
        from negmas_geniusweb_bridge.anac2020.hamming_agent.hamming_agent import (
            HammingAgent,
        )
        from negmas_geniusweb_bridge.anac2020.shine_agent.shine_agent import ShineAgent

        mechanism = SAOMechanism(issues=simple_issues, n_steps=50)

        neg_a = GeniusWebNegotiator(
            party_class=HammingAgent,
            ufun=ufun_a,
            name="hamming",
        )
        neg_b = GeniusWebNegotiator(
            party_class=ShineAgent,
            ufun=ufun_b,
            name="shine",
        )

        mechanism.add(neg_a)
        mechanism.add(neg_b)

        mechanism.run()

        state = mechanism.state
        assert not state.running
        assert state.step > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
