"""
AgentXX (NewAgentGG/AgentGG) - A negotiation agent using importance maps.

This agent was translated from the original Java implementation from ANAC 2019/2020.
Translation was performed using AI assistance.

Original authors: Shaobo Xu and Peihao Ren of University of Southampton.

Strategy overview:
- Works with partial preferences by building importance maps from bid orderings
- Uses frequency-based opponent modeling to estimate opponent preferences
- Implements a time-dependent concession strategy with multiple phases
- Supports both SHAOP (with elicitation) and SAOP modes
- Estimates Nash point from opponent's early offers to guide bidding

Key components:
- ImpUnit: Stores importance information for each value of an issue
- ImpMap: Maintains importance mapping for all issues/values
- SimpleLinearOrdering: Maintains ordered bid list for utility estimation
- Agent uses Nash point estimation to determine optimal concession curve

The agent starts with high demands and gradually concedes based on:
1. Time-dependent threshold that considers estimated Nash point
2. Reservation value to avoid deals worse than disagreement
3. Opponent bid history to find mutually acceptable outcomes
"""

from __future__ import annotations

import logging
import random
import time as time_module
from collections.abc import Iterator
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Comparison import Comparison
from geniusweb.actions.ElicitComparison import ElicitComparison
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.DefaultPartialOrdering import DefaultPartialOrdering
from geniusweb.profile.PartialOrdering import PartialOrdering
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
    from geniusweb.issuevalue.ValueSet import ValueSet


# =============================================================================
# Helper Classes
# =============================================================================


class ImpUnit:
    """
    Importance unit for a single value of an issue.

    Contains importance information including:
    - valueOfIssue: The value this unit represents
    - weightSum: Sum of weights (position in ordered bids)
    - count: Number of occurrences in bid ordering
    - meanWeightSum: Average weight (weightSum/count)

    The meanWeightSum is used to rank values within an issue.
    """

    def __init__(self, value: Value):
        """
        Initialize an importance unit.

        Args:
            value: The value this unit represents.
        """
        self.value_of_issue: Value = value
        self.weight_sum: int = 0
        self.count: int = 0
        self.mean_weight_sum: float = 0.0

    def __str__(self) -> str:
        """String representation of the importance unit."""
        return f"{self.value_of_issue} {self.mean_weight_sum}"

    @staticmethod
    def mean_weight_sum_comparator(unit: ImpUnit) -> float:
        """
        Comparator key for sorting by mean weight sum (descending).

        Returns negative to sort in descending order (highest first).
        """
        return -unit.mean_weight_sum


class ImpMap(dict[str, list[ImpUnit]]):
    """
    Importance map for issues and their values.

    Maps each issue (string) to a list of ImpUnits representing the
    importance of each value. The list is sorted by meanWeightSum
    in descending order (most important value first).

    Used both for self-modeling (based on bid orderings) and
    opponent modeling (based on frequency counting).
    """

    def __init__(self, profile: PartialOrdering):
        """
        Initialize the importance map.

        Args:
            profile: The partial ordering profile for the domain.
        """
        super().__init__()
        self._domain: Domain = profile.getDomain()

        # Create empty importance map for each issue
        for issue in self._domain.getIssues():
            values = self._domain.getValues(issue)
            issue_imp_units: list[ImpUnit] = []
            for value in values:
                issue_imp_units.append(ImpUnit(value))
            self[issue] = issue_imp_units

    def opponent_update(self, received_offer_bid: Bid) -> None:
        """
        Update opponent map by incrementing frequency of bid values.

        Args:
            received_offer_bid: The received opponent bid.
        """
        for issue in received_offer_bid.getIssues():
            current_issue_list = self.get(issue, [])
            for current_unit in current_issue_list:
                if current_unit.value_of_issue == received_offer_bid.getValue(issue):
                    current_unit.mean_weight_sum += 1
                    break

        # Re-sort each issue's values by importance
        for imp_unit_list in self.values():
            imp_unit_list.sort(key=ImpUnit.mean_weight_sum_comparator)

    def self_update(self, bid_ordering: list[Bid]) -> None:
        """
        Update own importance map based on bid ordering.

        Traverses the known bidOrder and updates the weight sum and
        occurrence count in the importance table.

        Args:
            bid_ordering: List of ordered bids (worst bid first, best bid last).
        """
        current_weight = 0
        for bid in bid_ordering:
            current_weight += 1
            for issue in bid.getIssues():
                current_issue_list = self.get(issue, [])
                for current_unit in current_issue_list:
                    if str(current_unit.value_of_issue) == str(bid.getValue(issue)):
                        current_unit.weight_sum += current_weight
                        current_unit.count += 1
                        break

        # Calculate mean weights
        for imp_unit_list in self.values():
            for current_unit in imp_unit_list:
                if current_unit.count == 0:
                    current_unit.mean_weight_sum = 0.0
                else:
                    current_unit.mean_weight_sum = float(
                        current_unit.weight_sum
                    ) / float(current_unit.count)

        # Sort by mean weight sum (descending)
        for imp_unit_list in self.values():
            imp_unit_list.sort(key=ImpUnit.mean_weight_sum_comparator)

        # Find minimum mean weight sum
        min_mean_weight_sum = float("inf")
        for issue, units in self.items():
            if units:
                temp_mean_weight_sum = units[-1].mean_weight_sum
                if temp_mean_weight_sum < min_mean_weight_sum:
                    min_mean_weight_sum = temp_mean_weight_sum

        # Subtract minimum from all values (normalization)
        for imp_unit_list in self.values():
            for current_unit in imp_unit_list:
                current_unit.mean_weight_sum -= min_mean_weight_sum

    def get_importance(self, bid: Bid) -> float:
        """
        Calculate the importance of a bid.

        Args:
            bid: The bid to evaluate.

        Returns:
            The importance value (sum of value importances).
        """
        bid_importance = 0.0
        for issue in bid.getIssues():
            value = bid.getValue(issue)
            value_importance = 0.0
            for imp_unit in self.get(issue, []):
                if imp_unit.value_of_issue == value:
                    value_importance = imp_unit.mean_weight_sum
                    break
            bid_importance += value_importance
        return bid_importance


class SimpleLinearOrdering:
    """
    A simple list of bids ordered from worst to best.

    Used for maintaining preference orderings. The first bid has
    utility 0, the last has utility 1. Bids not in the list have
    utility 0.
    """

    def __init__(
        self, profile_or_domain: Profile | Domain, bids: list[Bid] | None = None
    ):
        """
        Initialize the ordering.

        Args:
            profile_or_domain: Either a Profile to extract ordering from,
                             or a Domain if providing bids directly.
            bids: Initial list of bids (worst first, best last).
                  Required if profile_or_domain is a Domain.
        """
        if isinstance(profile_or_domain, Domain):
            self._domain: Domain = profile_or_domain
            self._bids: list[Bid] = list(bids) if bids else []
        else:
            # Profile case - extract sorted bids
            profile = profile_or_domain
            self._domain = profile.getDomain()
            self._bids = self._get_sorted_bids(profile)

    @staticmethod
    def _get_sorted_bids(profile: Profile) -> list[Bid]:
        """
        Get bids sorted by preference from a profile.

        Args:
            profile: The profile (DefaultPartialOrdering or LinearAdditive).

        Returns:
            List of bids sorted from worst to best.
        """
        domain = profile.getDomain()
        all_bids = AllBidsList(domain)

        if isinstance(profile, LinearAdditive):
            # For LinearAdditive, sort by utility
            bids_list = list(all_bids)
            bids_list.sort(key=lambda b: float(profile.getUtility(b)))
            return bids_list
        elif isinstance(profile, DefaultPartialOrdering):
            bids_list = list(profile.getBids())
            # Sort ascending by preference count
            bids_list.sort(
                key=lambda b1: sum(
                    1 for b2 in bids_list if profile.isPreferredOrEqual(b1, b2)
                )
            )
            return bids_list
        else:
            raise ValueError(f"Unsupported profile type: {type(profile)}")

    def get_name(self) -> str:
        """Get profile name (not supported)."""
        raise NotImplementedError()

    def get_domain(self) -> Domain:
        """Get the domain."""
        return self._domain

    def get_reservation_bid(self) -> Bid | None:
        """Get reservation bid (not supported)."""
        raise NotImplementedError()

    def get_utility(self, bid: Bid) -> Decimal:
        """
        Get the utility of a bid based on its position.

        Args:
            bid: The bid to evaluate.

        Returns:
            Utility as Decimal between 0 and 1.
        """
        if len(self._bids) < 2 or bid not in self._bids:
            return Decimal(0)
        # Using 8 decimals for precision
        index = Decimal(self._bids.index(bid))
        size = Decimal(len(self._bids) - 1)
        return index.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP) / size

    def contains(self, bid: Bid) -> bool:
        """Check if bid is in the ordering."""
        return bid in self._bids

    def get_bids(self) -> list[Bid]:
        """Get the list of bids (worst to best, unmodifiable copy)."""
        return list(self._bids)

    def with_comparison(self, bid: Bid, worse_bids: list[Bid]) -> SimpleLinearOrdering:
        """
        Create a new ordering with an additional bid inserted.

        The bid will be inserted after the first bid that is not
        in the worse_bids list.

        Args:
            bid: The bid to add.
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


# =============================================================================
# Main Agent Class
# =============================================================================


class AgentXX(DefaultParty):
    """
    AgentXX (NewAgentGG/AgentGG) - ANAC 2019/2020 agent.

    This agent uses importance maps to estimate utilities from
    partial orderings, combined with frequency-based opponent modeling.

    Strategy:
    - Phase 1 (0-1%): Very high threshold (0.9999) for initial exploration
    - Phase 2 (1-2%): High threshold (0.99) to adapt to domain
    - Phase 3 (2-20%): Gradual decrease to 0.9
    - Phase 4 (20-50%): Decrease toward estimated Nash point
    - Phase 5-8 (50-99.9%): Progressive compromise toward Nash point
    - Final round: Accept if utility > reservation + 0.2

    Supports both SHAOP (with elicitation) and SAOP protocols.
    """

    def __init__(self, reporter: Reporter | None = None):
        """
        Initialize the AgentXX.

        Args:
            reporter: Optional reporter for logging.
        """
        super().__init__(reporter)

        # Importance maps
        self._imp_map: ImpMap | None = None
        self._opponent_imp_map: ImpMap | None = None
        self._profile_linear_ordering: SimpleLinearOrdering | None = None

        # Thresholds
        self._offer_lower_ratio: float = 1.0
        self._offer_higher_ratio: float = 1.1

        # Importance bounds
        self._max_importance: float = 0.0
        self._min_importance: float = 0.0
        self._median_importance: float = 0.0
        self._max_importance_bid: Bid | None = None
        self._min_importance_bid: Bid | None = None

        # Bid tracking
        self._received_bid: Bid | None = None
        self._last_received_bid: Bid | None = None
        self._reservation_importance_ratio: float = 0.0
        self._offer_randomly: bool = True

        # Nash point estimation
        self._start_time: float = 0.0
        self._max_oppo_bid_imp_for_me_got: bool = False
        self._max_oppo_bid_imp_for_me: float = 0.0
        self._estimated_nash_point: float = 0.0
        self._initial_time_pass: bool = False

        # Protocol state
        self._profile_interface: ProfileInterface | None = None
        self._me: PartyId | None = None
        self._progress: Progress | None = None
        self._last_received_action: Action | None = None
        self._random = random.Random()
        self._all_bids: AllBidsList | None = None

        # SHAOP elicitation
        self._elicitation_active: bool = True
        self._elicitation_count: int = 0
        self._elicitation_cost: float = 0.01

    def notifyChange(self, info: Inform) -> None:
        """
        Handle incoming information from the negotiation protocol.

        Args:
            info: The information received.
        """
        try:
            if isinstance(info, Settings):
                self._init(info)
            elif isinstance(info, ActionDone):
                self._last_received_action = info.getAction()
                if isinstance(self._last_received_action, Offer):
                    self._received_bid = self._last_received_action.getBid()
                elif isinstance(self._last_received_action, Comparison):
                    current_comparison = self._last_received_action
                    self._process_elicitation_request_result(current_comparison)
                    self._do_my_turn()
            elif isinstance(info, YourTurn):
                self._do_my_turn()
            elif isinstance(info, Finished):
                self.getReporter().log(logging.INFO, f"Final outcome: {info}")
                self.terminate()
        except Exception as e:
            raise RuntimeError(f"Failed to handle info: {e}") from e

    def _do_my_turn(self) -> None:
        """Execute the agent's turn."""
        action = self._choose_action()
        if isinstance(self._progress, ProgressRounds):
            self._progress = self._progress.advance()
        self.getConnection().send(action)

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SAOP", "SHAOP"},
            {
                "geniusweb.profile.PartialOrdering",
                "geniusweb.profile.utilityspace.LinearAdditive",
            },
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return (
            "ANAC 2019 AgentGG (AgentXX) translated to GeniusWeb. "
            "Requires partial profile. Uses frequency counting to estimate "
            "important opponent values. (AI-translated from Java)"
        )

    def _init(self, info: Settings) -> None:
        """
        Initialize the agent with settings.

        Args:
            info: The negotiation settings.
        """
        self._me = info.getID()
        self._progress = info.getProgress()

        self._profile_interface = ProfileConnectionFactory.create(
            info.getProfile().getURI(), self.getReporter()
        )
        partial_profile = self._profile_interface.getProfile()

        if not isinstance(partial_profile, PartialOrdering):
            raise ValueError("Profile must be a PartialOrdering")

        self._all_bids = AllBidsList(partial_profile.getDomain())

        # Create empty importance maps
        self._imp_map = ImpMap(partial_profile)
        self._opponent_imp_map = ImpMap(partial_profile)

        # Get sorted bids from profile
        self._profile_linear_ordering = SimpleLinearOrdering(
            self._profile_interface.getProfile()
        )
        linear_order_bids = self._profile_linear_ordering.get_bids()

        # Update own importance map
        self._imp_map.self_update(linear_order_bids)

        # Get maximum, minimum, and median bids
        self._get_max_and_min_bid()
        self._get_median_bid(linear_order_bids)

        # Get reservation value ratio
        self._reservation_importance_ratio = self._get_reservation_ratio()

        self.getReporter().log(
            logging.INFO, f"reservation ratio: {self._reservation_importance_ratio}"
        )
        self.getReporter().log(
            logging.INFO, f"my max importance bid: {self._max_importance_bid}"
        )
        self.getReporter().log(
            logging.INFO, f"my max importance: {self._max_importance}"
        )
        self.getReporter().log(
            logging.INFO, f"my min importance bid: {self._min_importance_bid}"
        )
        self.getReporter().log(
            logging.INFO, f"my min importance: {self._min_importance}"
        )
        self.getReporter().log(
            logging.INFO, f"my median importance: {self._median_importance}"
        )
        self.getReporter().log(
            logging.INFO, f"Party {self._me} has finished initialization"
        )

    def _choose_action(self) -> Action:
        """
        Choose the next action to take.

        Returns:
            The action to perform.
        """
        time = self._progress.get(int(time_module.time() * 1000))

        # Start competition with max importance bid
        if not isinstance(self._last_received_action, Offer):
            return Offer(self._me, self._max_importance_bid)

        # Calculate importance ratio of received bid
        imp_ratio_for_me = (
            self._imp_map.get_importance(self._received_bid) - self._min_importance
        ) / (self._max_importance - self._min_importance)

        # Accept if offer meets threshold
        if imp_ratio_for_me >= self._offer_lower_ratio:
            self.getReporter().log(logging.INFO, f"\n\naccepted agent: Agent{self._me}")
            self.getReporter().log(logging.INFO, f"last bid: {self._received_bid}")
            self.getReporter().log(
                logging.INFO, f"\ncurrent threshold: {self._offer_lower_ratio}"
            )
            self.getReporter().log(logging.INFO, "\n\n")
            return Accept(self._me, self._received_bid)

        # Estimate Nash point from opponent's initial bids
        if not self._max_oppo_bid_imp_for_me_got:
            self._get_max_oppo_bid_imp_for_me(time, 3.0 / 1000.0)

        # Update opponent importance map during early negotiation
        if time < 0.3:
            self._opponent_imp_map.opponent_update(self._received_bid)

        # Get threshold (and possibly elicitation request)
        elicitation_request = self._get_threshold(time)
        if elicitation_request is not None:
            self.getReporter().log(
                logging.INFO,
                f"DOING ELICITATION REQUEST #{self._elicitation_count}",
            )
            return elicitation_request

        # Last round acceptance
        if time >= 0.9989:
            ratio = (
                self._imp_map.get_importance(self._received_bid) - self._min_importance
            ) / (self._max_importance - self._min_importance)
            if ratio > self._reservation_importance_ratio + 0.2:
                return Accept(self._me, self._received_bid)

        self.getReporter().log(
            logging.INFO, f"high threshold: {self._offer_higher_ratio}"
        )
        self.getReporter().log(
            logging.INFO, f"low threshold: {self._offer_lower_ratio}"
        )
        self.getReporter().log(
            logging.INFO, f"estimated nash: {self._estimated_nash_point}"
        )
        self.getReporter().log(
            logging.INFO, f"reservation: {self._reservation_importance_ratio}"
        )

        bid = self._get_needed_random_bid(
            self._offer_lower_ratio, self._offer_higher_ratio
        )
        self._last_received_bid = self._received_bid
        return Offer(self._me, bid)

    def _get_max_oppo_bid_imp_for_me(self, time: float, time_last: float) -> None:
        """
        Estimate Pareto optimal point from opponent's initial offers.

        When opponent's utility is around 1.0, find the best bid for us
        among their offers. This helps estimate the Nash point.

        Args:
            time: Current negotiation time.
            time_last: Duration to observe opponent bids.
        """
        this_bid_imp = self._imp_map.get_importance(self._received_bid)
        if this_bid_imp > self._max_oppo_bid_imp_for_me:
            self._max_oppo_bid_imp_for_me = this_bid_imp

        if self._initial_time_pass:
            if time - self._start_time > time_last:
                max_oppo_bid_ratio_for_me = (
                    self._max_oppo_bid_imp_for_me - self._min_importance
                ) / (self._max_importance - self._min_importance)
                # 1.414 is circle, 2 is straight line
                self._estimated_nash_point = (
                    1 - max_oppo_bid_ratio_for_me
                ) / 1.7 + max_oppo_bid_ratio_for_me
                self._max_oppo_bid_imp_for_me_got = True
        else:
            if self._last_received_bid != self._received_bid:
                self._initial_time_pass = True
                self._start_time = time

    def _process_elicitation_request_result(
        self, elicited_comparison: Comparison
    ) -> None:
        """
        Process the result of an elicitation request.

        Recreates the importance map with the new comparison information.

        Args:
            elicited_comparison: The comparison result from elicitation.
        """
        partial_profile = self._profile_interface.getProfile()
        if not isinstance(partial_profile, PartialOrdering):
            return

        self._profile_linear_ordering = self._profile_linear_ordering.with_comparison(
            elicited_comparison.getBid(), list(elicited_comparison.getWorse())
        )
        linear_order_bids = self._profile_linear_ordering.get_bids()
        self._imp_map = ImpMap(partial_profile)
        self._imp_map.self_update(linear_order_bids)
        self._get_max_and_min_bid()
        self._get_median_bid(linear_order_bids)

    def _generate_new_elicitation_comparison_request(self) -> ElicitComparison:
        """
        Generate a new elicitation comparison request.

        Returns:
            ElicitComparison action for the received bid.
        """
        return ElicitComparison(
            self._me, self._received_bid, self._profile_linear_ordering.get_bids()
        )

    def _decide_if_elicitation_request(self, time: float) -> bool:
        """
        Decide whether to make an elicitation request.

        Uses a simulated-annealing-like process considering
        negotiation progress and elicitation cost.

        Args:
            time: Current negotiation time.

        Returns:
            True if should make elicitation request.
        """
        exponent = 1
        exponented_elicitation_count = self._elicitation_count**exponent
        temperature = (
            1
            - time * exponented_elicitation_count
            - self._elicitation_cost * exponented_elicitation_count
        )

        if random.random() < temperature:
            self._elicitation_count += 1
            return True
        return False

    def _get_threshold(self, time: float) -> Action | None:
        """
        Calculate upper and lower thresholds based on time.

        Implements a multi-phase concession strategy.

        Args:
            time: Current negotiation time (0-1).

        Returns:
            ElicitComparison action if elicitation is requested, else None.
        """
        elicitation_request: Action | None = None

        if time < 0.01:
            # First 10 rounds: 0.9999 (adapt to special domains)
            self._offer_lower_ratio = 0.9999
            if (
                self._elicitation_active
                and self._received_bid is not None
                and self._decide_if_elicitation_request(time)
            ):
                elicitation_request = (
                    self._generate_new_elicitation_comparison_request()
                )

        elif time < 0.02:
            # 10-20 rounds: 0.99
            self._offer_lower_ratio = 0.99
            if (
                self._elicitation_active
                and self._received_bid is not None
                and self._decide_if_elicitation_request(time)
            ):
                elicitation_request = (
                    self._generate_new_elicitation_comparison_request()
                )

        elif time < 0.2:
            # 20-200 rounds: high price, drop to 0.9
            self._offer_lower_ratio = 0.99 - 0.5 * (time - 0.02)
            if (
                self._elicitation_active
                and self._received_bid is not None
                and self._decide_if_elicitation_request(time)
            ):
                elicitation_request = (
                    self._generate_new_elicitation_comparison_request()
                )

        elif time < 0.5:
            self._offer_randomly = False
            # 200-500 rounds: gradually reduce to Nash point + 0.3
            p2 = 0.3 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            self._offer_lower_ratio = 0.9 - (0.9 - p2) / (0.5 - 0.2) * (time - 0.2)
            if (
                self._elicitation_active
                and self._received_bid is not None
                and self._decide_if_elicitation_request(time)
            ):
                elicitation_request = (
                    self._generate_new_elicitation_comparison_request()
                )

        elif time < 0.9:
            # 500-900 rounds: quickly decrease to Nash + 0.15
            p1 = 0.3 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            p2 = 0.15 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            self._offer_lower_ratio = p1 - (p1 - p2) / (0.9 - 0.5) * (time - 0.5)
            if (
                self._elicitation_active
                and self._received_bid is not None
                and self._decide_if_elicitation_request(time)
            ):
                elicitation_request = (
                    self._generate_new_elicitation_comparison_request()
                )

        elif time < 0.98:
            # Compromise 1
            p1 = 0.15 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            p2 = 0.05 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            possible_ratio = p1 - (p1 - p2) / (0.98 - 0.9) * (time - 0.9)
            self._offer_lower_ratio = max(
                possible_ratio, self._reservation_importance_ratio + 0.3
            )
            if (
                self._elicitation_active
                and self._received_bid is not None
                and self._decide_if_elicitation_request(time)
            ):
                elicitation_request = (
                    self._generate_new_elicitation_comparison_request()
                )

        elif time < 0.995:
            # Compromise 2: 980-995 rounds
            p1 = 0.05 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            p2 = 0.0 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            possible_ratio = p1 - (p1 - p2) / (0.995 - 0.98) * (time - 0.98)
            self._offer_lower_ratio = max(
                possible_ratio, self._reservation_importance_ratio + 0.25
            )
            if (
                self._elicitation_active
                and self._received_bid is not None
                and self._decide_if_elicitation_request(time)
            ):
                elicitation_request = (
                    self._generate_new_elicitation_comparison_request()
                )

        elif time < 0.999:
            # Compromise 3: 995-999 rounds
            p1 = 0.0 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            p2 = -0.35 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            possible_ratio = p1 - (p1 - p2) / (0.9989 - 0.995) * (time - 0.995)
            self._offer_lower_ratio = max(
                possible_ratio, self._reservation_importance_ratio + 0.25
            )
            if (
                self._elicitation_active
                and self._received_bid is not None
                and self._decide_if_elicitation_request(time)
            ):
                elicitation_request = (
                    self._generate_new_elicitation_comparison_request()
                )

        else:
            possible_ratio = (
                -0.4 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            )
            self._offer_lower_ratio = max(
                possible_ratio, self._reservation_importance_ratio + 0.2
            )
            if (
                self._elicitation_active
                and self._received_bid is not None
                and self._decide_if_elicitation_request(time)
            ):
                elicitation_request = (
                    self._generate_new_elicitation_comparison_request()
                )

        self._offer_higher_ratio = self._offer_lower_ratio + 0.1

        return elicitation_request

    def _get_reservation_ratio(self) -> float:
        """
        Get the reservation value ratio.

        Calculates the ratio of the reservation bid's importance
        relative to the importance range.

        Returns:
            The reservation importance ratio.
        """
        median_bid_ratio = (self._median_importance - self._min_importance) / (
            self._max_importance - self._min_importance
        )
        res_bid = self._profile_interface.getProfile().getReservationBid()
        res_value = 0.1
        if res_bid is not None:
            res_value = self._imp_map.get_importance(res_bid)
        return res_value * median_bid_ratio / 0.5

    def _get_max_and_min_bid(self) -> None:
        """
        Calculate max and min importance bids.

        The max importance bid uses the most important value for each issue.
        The min importance bid uses the least important value for each issue.
        """
        l_values_1: dict[str, Value] = {}
        l_values_2: dict[str, Value] = {}

        for issue, units in self._imp_map.items():
            if units:
                value1 = units[0].value_of_issue  # Most important
                value2 = units[-1].value_of_issue  # Least important
                l_values_1[issue] = value1
                l_values_2[issue] = value2

        self._max_importance_bid = Bid(l_values_1)
        self._min_importance_bid = Bid(l_values_2)
        self._max_importance = self._imp_map.get_importance(self._max_importance_bid)
        self._min_importance = self._imp_map.get_importance(self._min_importance_bid)

    def _get_median_bid(self, ordered_bids: list[Bid]) -> None:
        """
        Calculate the median importance from ordered bids.

        Args:
            ordered_bids: List of bids ordered from low to high utility.
        """
        median = (len(ordered_bids) - 1) // 2
        median2 = -1
        if len(ordered_bids) % 2 == 0:
            median2 = median + 1

        current = 0
        for bid in ordered_bids:
            current += 1
            if current == median:
                self._median_importance = self._imp_map.get_importance(bid)
                if median2 == -1:
                    break
            if current == median2:
                self._median_importance += self._imp_map.get_importance(bid)
                break

        if median2 != -1:
            self._median_importance /= 2

    def _get_needed_random_bid(self, lower_ratio: float, upper_ratio: float) -> Bid:
        """
        Get a random bid within the threshold range.

        Generates k random bids and selects the one with highest
        opponent importance that falls within the threshold range.

        Args:
            lower_ratio: Lower limit for acceptable bids.
            upper_ratio: Upper limit for acceptable bids.

        Returns:
            A bid within the threshold range.
        """
        k = 2 * int(self._all_bids.size())
        lower_threshold = (
            lower_ratio * (self._max_importance - self._min_importance)
            + self._min_importance
        )
        upper_threshold = (
            upper_ratio * (self._max_importance - self._min_importance)
            + self._min_importance
        )

        for _ in range(3):  # Try 3 times
            highest_opponent_importance = 0.0
            returned_bid: Bid | None = None

            for _ in range(k):
                bid = self._generate_random_bid()
                bid_importance = self._imp_map.get_importance(bid)
                bid_opponent_importance = self._opponent_imp_map.get_importance(bid)

                if lower_threshold <= bid_importance <= upper_threshold:
                    if self._offer_randomly:
                        return bid  # Random bid for first 0.2 time
                    if bid_opponent_importance > highest_opponent_importance:
                        highest_opponent_importance = bid_opponent_importance
                        returned_bid = bid

            if returned_bid is not None:
                return returned_bid

        # Fallback: find any bid above lower threshold
        while True:
            bid = self._generate_random_bid()
            if self._imp_map.get_importance(bid) >= lower_threshold:
                return bid

    def _generate_random_bid(self) -> Bid:
        """
        Generate a random bid from all possible bids.

        Returns:
            A random bid from the domain.
        """
        return self._all_bids.get(
            self._random.randint(0, int(self._all_bids.size()) - 1)
        )
