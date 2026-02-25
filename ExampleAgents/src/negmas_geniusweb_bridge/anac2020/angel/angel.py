"""
Angel Agent - A SHAOP agent using heuristic-based opponent and self modeling.

AI-translated from Java (ANAC 2020 competition).

Original strategy:
- Uses an intuitive heuristic to model opponents and estimate bid values
- Weights and utilities of individual issue values are learned over time
- Estimations are made with a linear additive utility function
- Elicitation requests are made when expected value gain exceeds elicitation cost
- Greedy concession strategy with confidence-based decision making

Original design by Andrew DeVoss and Robert Geraghty.
"""

from __future__ import annotations

import logging
import random
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Comparison import Comparison
from geniusweb.actions.ElicitComparison import ElicitComparison
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Value import Value
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.DefaultPartialOrdering import DefaultPartialOrdering
from geniusweb.profile.Profile import Profile
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.profileconnection.ProfileInterface import ProfileInterface
from geniusweb.progress.Progress import Progress
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter

if TYPE_CHECKING:
    from geniusweb.issuevalue.Domain import Domain
    from geniusweb.issuevalue.ValueSet import ValueSet


class SimpleLinearOrdering:
    """
    A simple list of bids ordered from worst to best.

    All bids are fully ordered (better or worse than other bids in the list).
    """

    def __init__(self, domain: Domain, bids: list[Bid] | None = None):
        """
        Initialize the linear ordering.

        Args:
            domain: The negotiation domain.
            bids: Initial list of bids (worst first, best last).
        """
        self._domain = domain
        self._bids: list[Bid] = list(bids) if bids else []

    @classmethod
    def from_profile(cls, profile: Profile) -> SimpleLinearOrdering:
        """
        Create ordering from a profile.

        Args:
            profile: The profile (DefaultPartialOrdering or LinearAdditive).

        Returns:
            A new SimpleLinearOrdering.

        Raises:
            ValueError: If profile type is not supported.
        """
        if isinstance(profile, DefaultPartialOrdering):
            bids_list = list(profile.getBids())
            # Sort ascending: worse bids first, better bids last
            bids_list.sort(
                key=lambda b: sum(
                    1 for other in bids_list if profile.isPreferredOrEqual(b, other)
                )
            )
            return cls(profile.getDomain(), bids_list)
        elif isinstance(profile, LinearAdditive):
            # For LinearAdditive, we shouldn't need this but handle it
            from geniusweb.bidspace.AllBidsList import AllBidsList

            all_bids = AllBidsList(profile.getDomain())
            bids_list = [all_bids.get(i) for i in range(min(100, int(all_bids.size())))]
            bids_list.sort(key=lambda b: float(profile.getUtility(b)))
            return cls(profile.getDomain(), bids_list)
        else:
            raise ValueError(f"Unsupported profile type: {type(profile)}")

    @property
    def domain(self) -> Domain:
        """Get the domain."""
        return self._domain

    def get_utility(self, bid: Bid) -> Decimal:
        """
        Get the utility of a bid based on its position in the ordering.

        Args:
            bid: The bid to evaluate.

        Returns:
            Utility value between 0 and 1 based on position.
        """
        if len(self._bids) < 2 or bid not in self._bids:
            return Decimal(0)
        # Using 8 decimals precision
        return Decimal(self._bids.index(bid)).quantize(
            Decimal("0.00000001"), rounding=ROUND_HALF_UP
        ) / Decimal(len(self._bids) - 1)

    def contains(self, bid: Bid | None) -> bool:
        """Check if bid is in the ordering."""
        if bid is None:
            return False
        return bid in self._bids

    def get_bids(self) -> list[Bid]:
        """Get a copy of the bids list."""
        return list(self._bids)

    def with_comparison(self, bid: Bid, worse_bids: list[Bid]) -> SimpleLinearOrdering:
        """
        Create new ordering with an additional bid.

        Args:
            bid: The bid to add.
            worse_bids: Bids that are worse than this bid.

        Returns:
            A new SimpleLinearOrdering with the bid inserted.
        """
        n = 0
        while n < len(self._bids) and self._bids[n] in worse_bids:
            n += 1
        new_bids = list(self._bids)
        new_bids.insert(n, bid)
        return SimpleLinearOrdering(self._domain, new_bids)


class Angel(DefaultParty):
    """
    ANGEL agent for SHAOP negotiation protocol.

    Uses an intuitive heuristic to model opponents and estimate bid values.
    Weights and utilities of individual issue values are learned over time.
    Estimations are made with a linear additive utility function, and then
    additionally processed with a confidence measure. Elicitation requests
    are made when the expected value gain exceeds the elicitation cost.

    Original design by Andrew DeVoss and Robert Geraghty.
    """

    def __init__(self, reporter: Reporter | None = None):
        """
        Initialize the Angel agent.

        Args:
            reporter: Optional reporter for logging.
        """
        super().__init__(reporter)
        self._random = random.Random()

        # Back-end variables
        self._me: PartyId | None = None
        self._profile_interface: ProfileInterface | None = None
        self._progress: Progress | None = None

        # Bid space information
        self._m: int = 0  # Number of issues
        self._d: int = 0  # Number of bids in partial preference profile
        self._e: float = 0.01  # Elicitation cost (epsilon)
        self._spent: float = 0.0  # Amount spent on elicitation
        self._reservation: Bid | None = None  # Best alternative to negotiated agreement
        self._reserve_utility: float = 0.0  # Estimated reservation utility
        self._T: int = 0  # Total number of rounds
        self._t: int = 0  # Current round
        self._tmav: int = -1  # Last round on which mav was updated

        # Memory for modeling
        self._issues: set[str] = set()
        self._issue_values: dict[str, ValueSet] = {}

        # Angel's estimated utilities: au[issue][value] = estimate
        self._au: dict[str, dict[Value, float]] = {}
        # Angel's estimated weights: aW[issue] = estimate
        self._aW: dict[str, float] = {}
        # Angel's confidence in issue values: ac[issue][value] = confidence
        self._ac: dict[str, dict[Value, float]] = {}

        # Opponent's estimated utilities: ou[issue][value] = estimate
        self._ou: dict[str, dict[Value, float]] = {}
        # Opponent's estimated weights: oW[issue] = estimate
        self._oW: dict[str, float] = {}
        # Opponent's confidence: oc[issue][value] = confidence
        self._oc: dict[str, dict[Value, float]] = {}

        # Bid tracking
        self._highest_received_bid: Bid | None = None
        self._last_received_bid: Bid | None = None
        self._last_sent_offer: Bid | None = None
        self._steps_down: int = 0

        # Comparisons tracking
        self._comparisons: set[tuple[Bid, Bid]] = set()  # (better, worse) pairs
        self._opp_comparisons: set[tuple[Bid, Bid]] = set()
        self._estimated_profile: SimpleLinearOrdering | None = None
        self._already_initialized: bool = False
        self._mav: float = 1.0  # Minimum accepted value
        self._last_elicited_bid: Bid | None = None

    def notifyChange(self, info: Inform) -> None:
        """
        Handle incoming information from the negotiation protocol.

        Args:
            info: The information received.
        """
        try:
            if isinstance(info, Settings):
                self._handle_settings(info)
            elif isinstance(info, ActionDone):
                self._handle_action_done(info)
            elif isinstance(info, YourTurn):
                self._my_turn()
            elif isinstance(info, Finished):
                self.getReporter().log(logging.INFO, f"Final outcome: {info}")
                self.terminate()
        except Exception as e:
            raise RuntimeError(f"Failed to handle info: {e}") from e

    def _handle_settings(self, settings: Settings) -> None:
        """
        Initialize agent with settings.

        Args:
            settings: The negotiation settings.
        """
        self._profile_interface = ProfileConnectionFactory.create(
            settings.getProfile().getURI(), self.getReporter()
        )
        profile = self._profile_interface.getProfile()

        self._estimated_profile = SimpleLinearOrdering.from_profile(profile)
        self._reservation = profile.getReservationBid()
        self._issues = set(profile.getDomain().getIssues())
        self._m = len(self._issues)

        for issue in self._issues:
            self._issue_values[issue] = profile.getDomain().getValues(issue)

        self._me = settings.getID()
        self._progress = settings.getProgress()

        # Get elicitation cost from parameters
        params = settings.getParameters()
        if params.get("elicitationcost") is not None:
            self._e = float(params.get("elicitationcost"))

        if isinstance(self._progress, ProgressRounds):
            self._T = self._progress.getTotalRounds()

        if not self._already_initialized:
            self._initialize_agent()

    def _initialize_agent(self) -> None:
        """Initialize all estimates and data structures."""
        if self._estimated_profile is None:
            return

        # Fill bid issues for all known bids
        bids = self._estimated_profile.get_bids()
        filled_bids = [self._fill_bid_issues(bid) for bid in bids]
        self._estimated_profile = SimpleLinearOrdering(
            self._estimated_profile.domain, filled_bids
        )

        self._init_angel_comparisons()
        self._d = len(self._estimated_profile.get_bids())

        # Initialize with normal distribution utilities
        normal_utils = self._init_normal_utils()
        self._init_angel_weights(normal_utils)
        self._init_opp_weights()
        self._init_angel_utils(normal_utils)
        self._init_opp_utils()
        self._init_angel_confidences()
        self._init_opp_confidences()

        # Handle initial faults
        for comparison in list(self._comparisons):
            if self._is_fault(comparison):
                self._handle_fault_for_comparison(comparison)

        # Adjust confidences
        for issue in self._issues:
            for value in self._issue_values[issue]:
                self._adjust_confidence_for_issue_value(issue, value, self._comparisons)

    def _handle_action_done(self, info: ActionDone) -> None:
        """
        Handle opponent's action.

        Args:
            info: The action done information.
        """
        other_action = info.getAction()

        if isinstance(other_action, Offer):
            self._last_received_bid = self._fill_bid_issues(other_action.getBid())
            last_util = self._calculate_bid_utility(self._last_received_bid)
            best_util = self._calculate_bid_utility(self._highest_received_bid)
            if last_util > best_util:
                self._highest_received_bid = self._last_received_bid

        elif isinstance(other_action, Comparison):
            # Update profile with comparison result
            if self._estimated_profile is not None:
                self._estimated_profile = self._estimated_profile.with_comparison(
                    other_action.getBid(), list(other_action.getWorse())
                )

            # Add comparisons for better bids
            for better in other_action.getBetter():
                if self._last_elicited_bid is not None:
                    self._comparisons.add((better, self._last_elicited_bid))

            # Add comparisons for worse bids
            new_comparisons: set[tuple[Bid, Bid]] = set()
            for worse in other_action.getWorse():
                if self._last_elicited_bid is not None:
                    comparison = (self._last_elicited_bid, worse)
                    new_comparisons.add(comparison)
                    self._comparisons.add(comparison)

            # Handle faults in new comparisons
            for comparison in new_comparisons:
                if self._is_fault(comparison):
                    self._handle_fault_for_comparison(comparison)

            # Adjust confidences based on new info
            for issue in self._issues:
                for value in self._issue_values[issue]:
                    self._adjust_confidence_for_issue_value(
                        issue, value, new_comparisons
                    )

            # Take turn after comparison
            self._my_turn()

    def _my_turn(self) -> None:
        """Execute agent's turn."""
        action: Action | None = None
        self._t += 1

        if self._t != self._tmav:
            self._recalculate_mav()

        if not self._already_initialized:
            # First turn: offer best bid
            if self._estimated_profile is not None:
                bids = self._estimated_profile.get_bids()
                if bids:
                    best_bid = bids[-1]
                    self._last_sent_offer = best_bid
                    action = Offer(self._me, best_bid)
                    self._already_initialized = True

            if isinstance(self._progress, ProgressRounds):
                self._progress = self._progress.advance()

        # Generate counter offer
        co = self._counter_offer()

        # Check if we should elicit info about counter offer
        if self._should_elicit(co) and action is None and co != self._last_elicited_bid:
            action = self._create_elicit_action(co)

        # Check if we should accept
        if action is None and self._last_received_bid is not None:
            if self._is_good(self._last_received_bid):
                action = Accept(self._me, self._last_received_bid)
            elif self._last_sent_offer is not None:
                # Update opponent model
                comparison = (self._last_received_bid, self._last_sent_offer)
                self._opp_comparisons.add(comparison)

                # Handle faults in opponent comparisons
                for comp in self._opp_comparisons:
                    if self._is_fault_opp(comp):
                        self._handle_fault_for_comparison_opp(comp)

                # Adjust opponent confidences
                for issue in self._issues:
                    for value in self._issue_values[issue]:
                        self._adjust_confidence_for_issue_value_opp(
                            issue, value, self._opp_comparisons
                        )

            if isinstance(self._progress, ProgressRounds):
                self._progress = self._progress.advance()

        # Check again for elicitation
        if action is None and co != self._last_elicited_bid and self._should_elicit(co):
            action = self._create_elicit_action(co)
            self._t -= 1

        # Default to offering counter offer
        if action is None:
            action = Offer(self._me, co)
            self._last_sent_offer = co

        self.getConnection().send(action)

    def _create_elicit_action(self, bid: Bid) -> ElicitComparison:
        """Create an elicitation action."""
        self._tmav = self._t
        self._last_elicited_bid = bid
        bids_list = (
            self._estimated_profile.get_bids() if self._estimated_profile else []
        )
        return ElicitComparison(self._me, bid, bids_list)

    # =========================================================================
    # Initialization routines
    # =========================================================================

    def _init_normal_utils(self) -> list[float]:
        """Generate normally distributed utilities for initial bid evaluations."""
        normal_utils = [0.0] * self._d
        if self._d < 2:
            return normal_utils

        normal_utils[0] = 0.0
        normal_utils[self._d - 1] = 1.0

        # Sample from N(0.5, 1), clip to [0, 1], and sort
        temp_norms: list[float] = []
        for _ in range(self._d - 2):
            contender = self._random.gauss(0.5, 1.0)
            while contender < 0 or contender > 1:
                contender = self._random.gauss(0.5, 1.0)
            temp_norms.append(contender)

        temp_norms.sort()
        for i, val in enumerate(temp_norms):
            normal_utils[i + 1] = val

        return normal_utils

    def _init_angel_weights(self, utils: list[float]) -> None:
        """Initialize Angel's weight estimates for each issue."""
        if self._estimated_profile is None or self._d < 1:
            return

        bids = self._estimated_profile.get_bids()
        best_lambdas: dict[str, Value] = {}
        worst_lambdas: dict[str, Value] = {}

        # Get best/worst values from best/worst bids
        for issue in self._issues:
            best_lambdas[issue] = bids[-1].getValue(issue)
            worst_lambdas[issue] = bids[0].getValue(issue)

        high_sums: dict[str, float] = {issue: 0.0 for issue in self._issues}
        high_counts: dict[str, int] = {issue: 0 for issue in self._issues}
        low_sums: dict[str, float] = {issue: 0.0 for issue in self._issues}
        low_counts: dict[str, int] = {issue: 0 for issue in self._issues}

        # Sum utilities for bids containing best/worst values
        for bid_idx, bid in enumerate(bids):
            for issue in self._issues:
                bid_value = bid.getValue(issue)
                if bid_value == best_lambdas[issue]:
                    high_sums[issue] += utils[bid_idx]
                    high_counts[issue] += 1
                if bid_value == worst_lambdas[issue]:
                    low_sums[issue] += utils[bid_idx]
                    low_counts[issue] += 1

        # Compute weights: avg(bids with best lambda) - avg(bids with worst lambda) + 1
        weights: dict[str, float] = {}
        total = 0.0
        for issue in self._issues:
            high_avg = high_sums[issue] / max(high_counts[issue], 1)
            low_avg = low_sums[issue] / max(low_counts[issue], 1)
            amt = high_avg - low_avg + 1.0
            weights[issue] = amt
            total += amt

        # Normalize weights
        for issue in self._issues:
            self._aW[issue] = weights[issue] / total if total > 0 else 1.0 / self._m

    def _init_opp_weights(self) -> None:
        """Initialize opponent weight estimates (uniform)."""
        avg = 1.0 / self._m if self._m > 0 else 1.0
        for issue in self._issues:
            self._oW[issue] = avg

    def _init_angel_utils(self, utils: list[float]) -> None:
        """Initialize Angel's utility estimates for each issue value."""
        if self._estimated_profile is None:
            return

        bids = self._estimated_profile.get_bids()

        for issue in self._issues:
            self._au[issue] = {}
            unseen_lambdas: list[Value] = []

            best_bid = bids[-1] if bids else None
            worst_bid = bids[0] if bids else None
            best_lambda = best_bid.getValue(issue) if best_bid else None
            worst_lambda = worst_bid.getValue(issue) if worst_bid else None

            for value in self._issue_values[issue]:
                if value == best_lambda:
                    self._au[issue][value] = 1.0
                elif value == worst_lambda:
                    self._au[issue][value] = 0.0
                else:
                    # Compute average utility for bids containing this value
                    count = 0
                    total = 0.0
                    for bid_idx in range(1, self._d - 1):
                        if (
                            bid_idx < len(bids)
                            and bids[bid_idx].getValue(issue) == value
                        ):
                            count += 1
                            total += utils[bid_idx]

                    if count == 0:
                        unseen_lambdas.append(value)
                    else:
                        self._au[issue][value] = total / count

            # Assign median value to unseen lambdas
            if self._au[issue]:
                sorted_values = sorted(self._au[issue].values())
                n = len(sorted_values)
                if n % 2 == 0 and n > 0:
                    median = (sorted_values[n // 2] + sorted_values[n // 2 - 1]) / 2
                elif n > 0:
                    median = sorted_values[n // 2]
                else:
                    median = 0.5

                for value in unseen_lambdas:
                    self._au[issue][value] = median

    def _init_opp_utils(self) -> None:
        """Initialize opponent utility estimates (all 0.5)."""
        for issue in self._issues:
            self._ou[issue] = {}
            for value in self._issue_values[issue]:
                self._ou[issue][value] = 0.5

    def _init_angel_confidences(self) -> None:
        """Initialize Angel's confidence in utility estimates."""
        if self._estimated_profile is None:
            return

        bids = self._estimated_profile.get_bids()
        best_bid = bids[-1] if bids else None
        worst_bid = bids[0] if bids else None

        for issue in self._issues:
            self._ac[issue] = {}
            for value in self._issue_values[issue]:
                # High confidence for values in best/worst bids
                if best_bid and best_bid.getValue(issue) == value:
                    self._ac[issue][value] = 1.0
                elif worst_bid and worst_bid.getValue(issue) == value:
                    self._ac[issue][value] = 1.0
                else:
                    self._ac[issue][value] = 0.8

    def _init_opp_confidences(self) -> None:
        """Initialize opponent confidence estimates (all 0.8)."""
        for issue in self._issues:
            self._oc[issue] = {}
            for value in self._issue_values[issue]:
                self._oc[issue][value] = 0.8

    def _init_angel_comparisons(self) -> None:
        """Initialize comparisons from the known bid ordering."""
        if self._estimated_profile is None:
            return

        bids = self._estimated_profile.get_bids()
        for low_idx in range(len(bids)):
            for high_idx in range(len(bids)):
                if high_idx >= low_idx:
                    # high >= low
                    self._comparisons.add((bids[high_idx], bids[low_idx]))

    # =========================================================================
    # Main routines
    # =========================================================================

    def _fill_bid_issues(self, bid: Bid | None) -> Bid:
        """
        Fill missing issue values in a bid with worst values.

        Args:
            bid: The bid to fill.

        Returns:
            A complete bid with all issues.
        """
        if bid is None:
            return Bid({})

        if len(bid.getIssues()) == len(self._issues):
            return bid

        new_bid_values: dict[str, Value] = {}
        had_issues = bid.getIssues()

        for issue in self._issues:
            if issue in had_issues:
                new_bid_values[issue] = bid.getValue(issue)
            else:
                # Use worst bid's value for missing issues
                if self._estimated_profile is not None:
                    bids = self._estimated_profile.get_bids()
                    if bids:
                        new_bid_values[issue] = bids[0].getValue(issue)

        return Bid(new_bid_values)

    def _handle_fault_for_comparison(self, comparison: tuple[Bid, Bid]) -> None:
        """
        Adjust estimates when a comparison creates a fault.

        Args:
            comparison: Tuple of (better_bid, worse_bid).
        """
        too_low, too_high = comparison[0], comparison[1]
        difference = self._calculate_bid_utility(too_low) - self._calculate_bid_utility(
            too_high
        )

        if difference <= 0:
            return

        altered_weights: dict[str, float] = {}
        original_est: dict[str, float] = {}
        total = 0.0

        for issue in self._issues:
            w_issue = self._aW.get(issue, 0.0)
            u_issue = self._au.get(issue, {}).get(too_high.getValue(issue), 0.0)
            original_est[issue] = w_issue * u_issue

            conf = self._ac.get(issue, {}).get(too_high.getValue(issue), 0.8)
            w_alt = 1 + w_issue - conf * difference / len(self._issues)
            altered_weights[issue] = w_alt
            total += w_alt

        # Normalize weights
        if total > 0:
            for issue in self._issues:
                self._aW[issue] = altered_weights[issue] / total

        # Adjust utilities
        distribute_amt = 0.0
        count = 1
        for issue in self._issues:
            conf = self._ac.get(issue, {}).get(too_high.getValue(issue), 0.8)
            if conf == 1.0:
                count += 1
                new_w = self._aW.get(issue, 0.0)
                new_u = self._au.get(issue, {}).get(too_high.getValue(issue), 0.0)
                distribute_amt += original_est[issue] - new_w * new_u

        for issue in self._issues:
            conf = self._ac.get(issue, {}).get(too_high.getValue(issue), 0.8)
            if conf != 1.0:
                w = self._aW.get(issue, 0.0)
                if w > 0:
                    new_val = (
                        original_est[issue]
                        - (difference / len(self._issues) + distribute_amt / count)
                    ) / w
                    new_val = min(0.99, new_val)
                    if issue not in self._au:
                        self._au[issue] = {}
                    self._au[issue][too_high.getValue(issue)] = new_val

    def _count_faults(self, comparisons: set[tuple[Bid, Bid]]) -> int:
        """Count the number of faults in comparisons."""
        num_faults = 0
        for comparison in comparisons:
            high_val = self._calculate_bid_utility(comparison[0])
            low_val = self._calculate_bid_utility(comparison[1])
            if high_val < low_val:
                num_faults += 1
        return num_faults

    def _adjust_confidence_for_issue_value(
        self, issue: str, value: Value, comparisons: set[tuple[Bid, Bid]]
    ) -> None:
        """Adjust confidence for an issue value based on faults."""
        if self._ac.get(issue, {}).get(value, 0.0) == 1.0:
            return

        faults = 0
        for comparison in comparisons:
            high_val = self._calculate_bid_utility(comparison[0])
            low_val = self._calculate_bid_utility(comparison[1])
            if high_val < low_val:
                high_bid, low_bid = comparison[0], comparison[1]
                if (
                    high_bid.getValue(issue) == value
                    or low_bid.getValue(issue) == value
                ):
                    faults += 1

        if comparisons:
            old_conf = self._ac.get(issue, {}).get(value, 0.8)
            new_conf = (old_conf + (1.0 - faults) / len(comparisons)) / 2
            if issue not in self._ac:
                self._ac[issue] = {}
            self._ac[issue][value] = new_conf

    def _recalculate_mav(self) -> None:
        """Recalculate minimum accepted value based on progress."""
        hi_opp = self._calculate_bid_utility(self._highest_received_bid)
        reserve = self._calculate_bid_utility(self._reservation)

        # Slightly lower hiOpp to prevent being overly greedy
        if hi_opp > reserve:
            hi_opp = hi_opp - 0.2 * (hi_opp - reserve)

        end = max(reserve, hi_opp)

        if self._t <= 0.7 * self._T:
            y2 = 1.0
            y1 = 1 - 0.3 * (1 - end)
            x2 = 0
            x1 = 0.7 * self._T
            if x1 != x2:
                m = (y2 - y1) / (x2 - x1)
                self._mav = m * self._t + 1
        elif self._t <= 0.8 * self._T:
            y2 = 1 - 0.3 * (1 - end)
            y1 = 1 - 0.5 * (1 - end)
            x2 = 0.7 * self._T
            x1 = 0.8 * self._T
            if x1 != x2:
                m = (y2 - y1) / (x2 - x1)
                b = y2 - m * x2
                self._mav = m * self._t + b
        else:
            y2 = 1 - 0.5 * (1 - end)
            y1 = end
            x2 = 0.8 * self._T
            x1 = self._T
            if x1 != x2:
                m = (y2 - y1) / (x2 - x1)
                b = y2 - m * x2
                self._mav = m * self._t + b

        self._mav = max(self._mav, max(reserve, hi_opp))

    def _counter_offer(self) -> Bid:
        """
        Generate a counter offer based on various strategies.

        Returns:
            The best counter offer bid.
        """
        bid1: Bid | None = None
        bid2: Bid | None = None
        bid3: Bid | None = None

        if self._last_received_bid is not None:
            bid1 = self._bid_step_up(self._last_received_bid)

        if self._highest_received_bid is not None:
            bid2 = self._bid_step_up(self._highest_received_bid)

        if self._last_sent_offer is not None:
            bid3 = self._bid_step_down(self._last_sent_offer)

        est1 = self._calculate_bid_utility(bid1)
        est2 = self._calculate_bid_utility(bid2)
        est3 = self._calculate_bid_utility(bid3)

        if est1 >= self._mav and est1 >= est2 and est1 >= est3:
            return bid1
        elif est2 >= self._mav and est2 >= est1 and est2 >= est3:
            return bid2
        elif est3 >= self._mav and est3 >= est1 and est3 >= est2:
            return bid3
        elif self._estimated_profile is not None:
            bids = self._estimated_profile.get_bids()
            idx = self._d - 1 - self._steps_down
            if self._steps_down < self._d and idx >= 0 and idx < len(bids):
                known = bids[idx]
                if self._calculate_bid_utility(known) > self._mav:
                    self._steps_down += 1
                    return known

            if self._calculate_bid_utility(self._last_sent_offer) > self._mav:
                return self._last_sent_offer

            # Default to best bid
            return bids[-1] if bids else Bid({})

        return Bid({})

    def _should_elicit(self, counteroffer: Bid | None) -> bool:
        """Check if we should elicit information about a bid."""
        if counteroffer is None or self._estimated_profile is None:
            return False

        if self._estimated_profile.contains(counteroffer):
            return False

        expected_value = self._calculate_bid_utility(
            counteroffer
        ) - self._calculate_confidence_scaled_bid_utility(counteroffer)

        if expected_value > self._spent + self._e:
            self._spent += self._e
            return True

        return False

    # =========================================================================
    # Utility calculation
    # =========================================================================

    def _is_good(self, bid: Bid | None) -> bool:
        """Check if a bid is acceptable."""
        if bid is None:
            return False

        # Check ordering constraints
        if (
            self._estimated_profile is not None
            and self._estimated_profile.contains(bid)
            and self._estimated_profile.contains(self._reservation)
        ):
            bids = self._estimated_profile.get_bids()
            bidx = bids.index(bid) if bid in bids else -1
            ridx = bids.index(self._reservation) if self._reservation in bids else -1
            if bidx >= 0 and ridx >= 0 and bidx < ridx:
                return False

        # Check explicit comparisons
        for comparison in self._comparisons:
            if comparison[0] == self._reservation and comparison[1] == bid:
                return False

        return self._calculate_bid_utility(bid) >= self._mav

    def _calculate_bid_utility(self, bid: Bid | None) -> float:
        """
        Calculate estimated utility of a bid.

        Args:
            bid: The bid to evaluate.

        Returns:
            Estimated utility value.
        """
        if bid is None:
            return 0.0

        utility = 0.0
        issue_values = bid.getIssueValues()

        for issue, value in issue_values.items():
            weight = self._aW.get(issue, 0.0)
            u = self._au.get(issue, {}).get(value, 0.0)
            utility += weight * u

        return min(utility, 1.0)

    def _calculate_confidence_scaled_bid_utility(self, bid: Bid | None) -> float:
        """Calculate confidence-scaled utility of a bid."""
        if bid is None:
            return 0.0

        scaled_utility = 0.0
        issue_values = bid.getIssueValues()

        for issue, value in issue_values.items():
            weight = self._aW.get(issue, 0.0)
            u = self._au.get(issue, {}).get(value, 0.0)
            conf = self._ac.get(issue, {}).get(value, 0.8)
            scaled_utility += weight * u * conf

        return scaled_utility

    def _bid_step_down(self, greedy_bid: Bid) -> Bid:
        """
        Concede from a greedy bid by changing one issue value.

        Args:
            greedy_bid: The bid to concede from.

        Returns:
            A slightly worse bid for us (possibly better for opponent).
        """
        greedy_bid = self._fill_bid_issues(greedy_bid)

        # Find issue with greatest (opponent weight - our weight)
        pivot_issue = next(iter(self._issues)) if self._issues else ""
        highest_diff = 0.0

        for issue in self._issues:
            diff = self._oW.get(issue, 0.0) - self._aW.get(issue, 0.0)
            if diff > highest_diff:
                highest_diff = diff
                pivot_issue = issue

        # Find next lowest value for this issue
        current_val = greedy_bid.getValue(pivot_issue)
        current_util = self._au.get(pivot_issue, {}).get(current_val, 0.0)

        next_lowest_value: Value | None = None
        low = -2.0

        for value in self._issue_values.get(pivot_issue, []):
            util = self._au.get(pivot_issue, {}).get(value, 0.0)
            if util > low and util < current_util:
                low = util
                next_lowest_value = value

        # Create new bid
        new_bid_values: dict[str, Value] = {}
        for issue in self._issues:
            if issue == pivot_issue and next_lowest_value is not None:
                new_bid_values[issue] = next_lowest_value
            else:
                new_bid_values[issue] = greedy_bid.getValue(issue)

        return Bid(new_bid_values)

    def _bid_step_up(self, icky_bid: Bid) -> Bid:
        """
        Improve a bid by changing one issue value to be better for us.

        Args:
            icky_bid: The bid to improve.

        Returns:
            A better bid for us.
        """
        icky_bid = self._fill_bid_issues(icky_bid)

        # Find issue with greatest (our weight - opponent weight)
        pivot_issue = ""
        highest_diff = 0.0

        for issue in self._issues:
            diff = self._aW.get(issue, 0.0) - self._oW.get(issue, 0.0)
            if diff > highest_diff:
                highest_diff = diff
                pivot_issue = issue

        if not pivot_issue:
            return icky_bid

        # Get best value for this issue from our best bid
        best_value: Value | None = None
        if self._estimated_profile is not None:
            bids = self._estimated_profile.get_bids()
            if bids:
                best_value = bids[-1].getValue(pivot_issue)

        # Create new bid
        new_bid_values: dict[str, Value] = {}
        for issue in self._issues:
            if issue == pivot_issue and best_value is not None:
                new_bid_values[issue] = best_value
            else:
                new_bid_values[issue] = icky_bid.getValue(issue)

        return Bid(new_bid_values)

    def _is_fault(self, comparison: tuple[Bid, Bid]) -> bool:
        """Check if a comparison is a fault (utilities are reversed)."""
        high_val = self._calculate_bid_utility(comparison[0])
        low_val = self._calculate_bid_utility(comparison[1])
        return high_val < low_val

    # =========================================================================
    # Opponent model routines
    # =========================================================================

    def _calculate_bid_utility_opp(self, bid: Bid | None) -> float:
        """Calculate estimated opponent utility of a bid."""
        if bid is None:
            return 0.0

        utility = 0.0
        issue_values = bid.getIssueValues()

        for issue, value in issue_values.items():
            weight = self._oW.get(issue, 0.0)
            u = self._ou.get(issue, {}).get(value, 0.0)
            utility += weight * u

        return utility

    def _is_fault_opp(self, comparison: tuple[Bid, Bid]) -> bool:
        """Check if a comparison is a fault for opponent model."""
        high_val = self._calculate_bid_utility_opp(comparison[0])
        low_val = self._calculate_bid_utility_opp(comparison[1])
        return high_val < low_val

    def _handle_fault_for_comparison_opp(self, comparison: tuple[Bid, Bid]) -> None:
        """Adjust opponent estimates when a comparison creates a fault."""
        too_low, too_high = comparison[0], comparison[1]
        difference = self._calculate_bid_utility_opp(
            too_low
        ) - self._calculate_bid_utility_opp(too_high)

        if difference <= 0:
            return

        altered_weights: dict[str, float] = {}
        original_est: dict[str, float] = {}
        total = 0.0

        for issue in self._issues:
            w_issue = self._oW.get(issue, 0.0)
            u_issue = self._ou.get(issue, {}).get(too_high.getValue(issue), 0.0)
            original_est[issue] = w_issue * u_issue

            conf = self._oc.get(issue, {}).get(too_high.getValue(issue), 0.8)
            w_alt = 1 + w_issue - conf * difference / len(self._issues)
            altered_weights[issue] = w_alt
            total += w_alt

        # Normalize weights
        if total > 0:
            for issue in self._issues:
                self._oW[issue] = altered_weights[issue] / total

        # Adjust utilities
        distribute_amt = 0.0
        count = 1
        for issue in self._issues:
            conf = self._oc.get(issue, {}).get(too_high.getValue(issue), 0.8)
            if conf == 1.0:
                count += 1
                new_w = self._oW.get(issue, 0.0)
                new_u = self._ou.get(issue, {}).get(too_high.getValue(issue), 0.0)
                distribute_amt += original_est[issue] - new_w * new_u

        for issue in self._issues:
            conf = self._oc.get(issue, {}).get(too_high.getValue(issue), 0.8)
            if conf != 1.0:
                w = self._oW.get(issue, 0.0)
                if w > 0:
                    new_val = (
                        original_est[issue]
                        - (difference / len(self._issues) + distribute_amt / count)
                    ) / w
                    if issue not in self._ou:
                        self._ou[issue] = {}
                    self._ou[issue][too_high.getValue(issue)] = new_val

    def _adjust_confidence_for_issue_value_opp(
        self, issue: str, value: Value, comparisons: set[tuple[Bid, Bid]]
    ) -> None:
        """Adjust opponent confidence for an issue value."""
        faults = 0
        for comparison in comparisons:
            if self._is_fault_opp(comparison):
                high_lambdas = set(comparison[0].getIssueValues().values())
                low_lambdas = set(comparison[1].getIssueValues().values())
                if value in high_lambdas or value in low_lambdas:
                    faults += 1

        if comparisons:
            old_conf = self._oc.get(issue, {}).get(value, 0.8)
            new_conf = (old_conf + (1.0 - faults) / len(comparisons)) / 2
            if issue not in self._oc:
                self._oc[issue] = {}
            self._oc[issue][value] = new_conf

    # =========================================================================
    # Protocol methods
    # =========================================================================

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SHAOP", "SAOP"},
            {"geniusweb.profile.Profile"},
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return (
            "Angel Agent: Greedy concession strategy with elicitation "
            "when there is low confidence in best counter-offer prediction. "
            "Original design by Andrew DeVoss and Robert Geraghty. "
            "AI-translated from Java (ANAC 2020)."
        )
