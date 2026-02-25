"""
Common utilities for ANAC2020 agents.

This module provides shared functionality used by multiple agents,
including SimpleLinearOrdering which is used for bid ordering.

It also provides utilities for SHAOP agents to work in SAOP mode by
generating comparisons from utility functions.
"""

from __future__ import annotations

import random
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from geniusweb.issuevalue.Bid import Bid
    from geniusweb.issuevalue.Domain import Domain
    from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive


class SimpleLinearOrdering:
    """
    A simple list of bids, ordered from worst to best.

    This class maintains a linear ordering of bids where the first bid
    has utility 0 and the last bid has utility 1.
    """

    def __init__(self, domain: Domain, bids: list[Bid] | None = None):
        """
        Initialize the ordering.

        Args:
            domain: The negotiation domain.
            bids: A list of bids ordered from lowest to highest utility.
        """
        self._domain = domain
        self._bids: list[Bid] = list(bids) if bids else []

    @property
    def domain(self) -> Domain:
        """Get the domain."""
        return self._domain

    def get_domain(self) -> Domain:
        """Get the domain (Java-style method)."""
        return self._domain

    def getDomain(self) -> Domain:
        """Get the domain (GeniusWeb compatibility)."""
        return self._domain

    def get_bids(self) -> list[Bid]:
        """Get the list of bids."""
        return list(self._bids)

    def getBids(self) -> list[Bid]:
        """Get the list of bids (GeniusWeb compatibility)."""
        return self.get_bids()

    def size(self) -> int:
        """Get the number of bids."""
        return len(self._bids)

    def contains(self, bid: Bid) -> bool:
        """Check if a bid is in the ordering."""
        return bid in self._bids

    def get_utility(self, bid: Bid) -> Decimal:
        """
        Get the utility of a bid.

        Args:
            bid: The bid to evaluate.

        Returns:
            The utility as a Decimal between 0 and 1.
        """
        if len(self._bids) < 2 or bid not in self._bids:
            return Decimal(0)

        index = self._bids.index(bid)
        return Decimal(index) / Decimal(len(self._bids) - 1)

    def getUtility(self, bid: Bid) -> Decimal:
        """Get utility (GeniusWeb compatibility)."""
        return self.get_utility(bid)

    def with_bid(self, bid: Bid, worse_bids: list[Bid]) -> SimpleLinearOrdering:
        """
        Create a new ordering with an additional bid.

        Args:
            bid: The new bid to insert.
            worse_bids: All bids that are worse than this bid.

        Returns:
            A new SimpleLinearOrdering with the bid inserted.
        """
        n = 0
        while n < len(self._bids) and self._bids[n] in worse_bids:
            n += 1

        new_bids = list(self._bids)
        new_bids.insert(n, bid)
        return SimpleLinearOrdering(self._domain, new_bids)

    # Alias for Java-style method name
    def with_(self, bid: Bid, worse_bids: list[Bid]) -> SimpleLinearOrdering:
        """Alias for with_bid."""
        return self.with_bid(bid, worse_bids)


class OpponentModel:
    """
    A simple frequency-based opponent model.

    Tracks the frequency of issue-value selections by the opponent
    to estimate their preferences.
    """

    def __init__(self, domain: Domain):
        """
        Initialize the opponent model.

        Args:
            domain: The negotiation domain.
        """
        self._domain = domain
        self._issue_counts: dict[str, dict[str, int]] = {}
        self._total_bids = 0

        # Initialize counts for all issues and values
        for issue in domain.getIssues():
            self._issue_counts[issue] = {}
            value_set = domain.getValues(issue)
            for value in value_set:
                self._issue_counts[issue][str(value)] = 0

    def update(self, bid: Bid) -> None:
        """
        Update the model with a new opponent bid.

        Args:
            bid: The opponent's bid.
        """
        self._total_bids += 1
        for issue in bid.getIssues():
            value = bid.getValue(issue)
            if value is not None:
                value_str = str(value)
                if (
                    issue in self._issue_counts
                    and value_str in self._issue_counts[issue]
                ):
                    self._issue_counts[issue][value_str] += 1

    def get_predicted_utility(self, bid: Bid) -> float:
        """
        Get the predicted utility of a bid for the opponent.

        Args:
            bid: The bid to evaluate.

        Returns:
            A value between 0 and 1 representing predicted opponent utility.
        """
        if self._total_bids == 0:
            return 0.5

        total_score = 0.0
        n_issues = len(bid.getIssues())

        for issue in bid.getIssues():
            value = bid.getValue(issue)
            if value is not None:
                value_str = str(value)
                if (
                    issue in self._issue_counts
                    and value_str in self._issue_counts[issue]
                ):
                    count = self._issue_counts[issue][value_str]
                    total_score += count / self._total_bids

        return total_score / n_issues if n_issues > 0 else 0.5


def generate_comparisons_from_ufun(
    ufun: LinearAdditive,
    domain: Domain,
    n_samples: int = 100,
    seed: int | None = None,
) -> list[tuple[Bid, list[Bid]]]:
    """
    Generate pairwise comparisons from a utility function.

    This enables SHAOP agents to work in SAOP mode by simulating
    the preference elicitation process using the available ufun.

    Args:
        ufun: The utility function to use for comparisons.
        domain: The negotiation domain.
        n_samples: Number of bids to sample for comparison generation.
        seed: Random seed for reproducibility.

    Returns:
        A list of (bid, worse_bids) tuples where worse_bids contains
        all sampled bids with lower utility than bid.
    """
    from geniusweb.bidspace.AllBidsList import AllBidsList

    if seed is not None:
        random.seed(seed)

    all_bids = AllBidsList(domain)
    total_bids = all_bids.size()

    # Sample bids if there are too many
    if total_bids <= n_samples:
        sampled_bids = [all_bids.get(i) for i in range(total_bids)]
    else:
        indices = random.sample(range(total_bids), n_samples)
        sampled_bids = [all_bids.get(i) for i in indices]

    # Sort bids by utility (ascending)
    bid_utilities = [(bid, float(ufun.getUtility(bid))) for bid in sampled_bids]
    bid_utilities.sort(key=lambda x: x[1])

    # Generate comparisons: for each bid, all bids before it are worse
    comparisons: list[tuple[Bid, list[Bid]]] = []
    for i, (bid, _) in enumerate(bid_utilities):
        worse_bids = [b for b, _ in bid_utilities[:i]]
        comparisons.append((bid, worse_bids))

    return comparisons


def create_ordering_from_ufun(
    ufun: LinearAdditive,
    domain: Domain,
    n_samples: int = 100,
    seed: int | None = None,
) -> SimpleLinearOrdering:
    """
    Create a SimpleLinearOrdering from a utility function.

    This enables SHAOP agents to work in SAOP mode by creating
    a bid ordering directly from the ufun.

    Args:
        ufun: The utility function to use for ordering.
        domain: The negotiation domain.
        n_samples: Number of bids to sample for the ordering.
        seed: Random seed for reproducibility.

    Returns:
        A SimpleLinearOrdering with bids sorted from worst to best.
    """
    from geniusweb.bidspace.AllBidsList import AllBidsList

    if seed is not None:
        random.seed(seed)

    all_bids = AllBidsList(domain)
    total_bids = all_bids.size()

    # Sample bids if there are too many
    if total_bids <= n_samples:
        sampled_bids = [all_bids.get(i) for i in range(total_bids)]
    else:
        indices = random.sample(range(total_bids), n_samples)
        sampled_bids = [all_bids.get(i) for i in indices]

    # Sort bids by utility (ascending - worst to best)
    sampled_bids.sort(key=lambda b: float(ufun.getUtility(b)))

    return SimpleLinearOrdering(domain, sampled_bids)


def build_ordering_incrementally(
    ufun: LinearAdditive,
    domain: Domain,
    ordering: SimpleLinearOrdering,
    n_comparisons: int = 50,
    seed: int | None = None,
) -> SimpleLinearOrdering:
    """
    Build up an ordering incrementally using simulated comparisons.

    This mimics how SHAOP agents learn preferences through elicitation,
    but uses the ufun to generate the comparison results.

    Args:
        ufun: The utility function to use for comparisons.
        domain: The negotiation domain.
        ordering: The initial ordering to extend.
        n_comparisons: Number of comparisons to simulate.
        seed: Random seed for reproducibility.

    Returns:
        An extended SimpleLinearOrdering.
    """
    from geniusweb.bidspace.AllBidsList import AllBidsList

    if seed is not None:
        random.seed(seed)

    all_bids = AllBidsList(domain)
    total_bids = all_bids.size()

    current_ordering = ordering
    existing_bids = set(str(b) for b in current_ordering.get_bids())

    for _ in range(n_comparisons):
        # Pick a random bid not in the ordering
        attempts = 0
        while attempts < 100:
            idx = random.randint(0, total_bids - 1)
            new_bid = all_bids.get(idx)
            if str(new_bid) not in existing_bids:
                break
            attempts += 1
        else:
            # All bids already in ordering
            break

        # Find all bids in current ordering that are worse than new_bid
        new_utility = float(ufun.getUtility(new_bid))
        worse_bids = [
            b
            for b in current_ordering.get_bids()
            if float(ufun.getUtility(b)) < new_utility
        ]

        # Add to ordering
        current_ordering = current_ordering.with_bid(new_bid, worse_bids)
        existing_bids.add(str(new_bid))

    return current_ordering
