"""
Anaconda - ANAC 2020 SHAOP negotiation agent.

AI-translated from Java.

This agent implements a sophisticated bidding strategy for the SHAOP protocol
with preference elicitation. It uses importance maps to track both self and
opponent preferences, with dynamic lower bounds for bid acceptance.

Original strategy:
- Uses importance maps (selfMap, opponentMap) to model preferences
- Performs elicitation comparisons to refine preference model
- Calculates variance-based uncertainty in bid rankings
- Dynamic lower bound adjustment based on time and opponent behavior
"""

from __future__ import annotations

import logging
import math
import random
from typing import TYPE_CHECKING, cast

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
from geniusweb.issuevalue.Value import Value
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.DefaultPartialOrdering import DefaultPartialOrdering
from geniusweb.profile.PartialOrdering import PartialOrdering
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


class ImpUnit:
    """
    Importance unit for tracking value statistics.

    Stores information about a single value within an issue, including
    how many times it has been observed and its estimated probability/weight.
    """

    def __init__(self, value: Value):
        """
        Initialize an importance unit.

        Args:
            value: The issue value this unit represents.
        """
        self.value_of_issue: Value = value
        self.victories: int = 0
        self.total_count: int = 0
        self.probability: float = 0.0

    def __str__(self) -> str:
        return f"{self.value_of_issue} {self.probability}"


class ImpMap(dict[str, list[ImpUnit]]):
    """
    Base importance map for tracking value importance across issues.

    Maps issue names to lists of ImpUnit objects containing value statistics.
    """

    def __init__(self, profile: PartialOrdering):
        """
        Initialize the importance map.

        Args:
            profile: The partial ordering profile.
        """
        super().__init__()
        self._domain = profile.getDomain()

        # Create empty importance map
        for issue in self._domain.getIssues():
            values = self._domain.getValues(issue)
            issue_imp_units: list[ImpUnit] = []
            for value in values:
                issue_imp_units.append(ImpUnit(value))
            self[issue] = issue_imp_units

    def get_importance(self, bid: Bid) -> float:
        """
        Get the importance of a bid.

        Args:
            bid: The bid to evaluate.

        Returns:
            The total importance score for the bid.
        """
        bid_importance = 0.0
        for issue in bid.getIssues():
            value = bid.getValue(issue)
            value_importance = 0.0
            for unit in self.get(issue, []):
                if unit.value_of_issue == value:
                    value_importance = unit.probability
                    break
            bid_importance += value_importance
        return bid_importance


class SelfMap(ImpMap):
    """
    Self importance map for tracking own preferences.

    Extends ImpMap with methods for comparison-based updates and
    bid ranking based on log-probability.
    """

    def __init__(self, profile: PartialOrdering):
        """
        Initialize the self map.

        Args:
            profile: The partial ordering profile.
        """
        super().__init__(profile)
        self._bids_rank: dict[Bid, float] = {}
        self._sorted_bids: list[tuple[Bid, float]] = []

    def comparison_update(self, better_bid: Bid, worse_bid: Bid) -> None:
        """
        Update importance based on a comparison between two bids.

        Args:
            better_bid: The bid that is preferred.
            worse_bid: The bid that is less preferred.
        """
        for issue in better_bid.getIssues():
            current_issue_list = self.get(issue, [])
            for unit in current_issue_list:
                if str(unit.value_of_issue) == str(better_bid.getValue(issue)):
                    if str(better_bid.getValue(issue)) != str(
                        worse_bid.getValue(issue)
                    ):
                        unit.victories += 1
                    unit.total_count += 1
                    break

        # Calculate weights
        for imp_unit_list in self.values():
            for unit in imp_unit_list:
                if unit.total_count == 0:
                    unit.probability = 0.0
                else:
                    unit.probability = float(unit.victories) / float(unit.total_count)

    def initial_update(self, bid_ordering: list[Bid], all_bids: AllBidsList) -> None:
        """
        Initialize importance map from a bid ordering.

        Args:
            bid_ordering: List of bids ordered from worst to best.
            all_bids: All possible bids in the domain.
        """
        # Compare all pairs in the ordering
        for i in range(len(bid_ordering)):
            for j in range(i + 1, len(bid_ordering)):
                worse_bid = bid_ordering[i]
                better_bid = bid_ordering[j]
                self.comparison_update(better_bid, worse_bid)

        if len(bid_ordering) > 0:
            min_bid = bid_ordering[0]
            max_bid = bid_ordering[-1]

            # Compare all bids not in ordering with min and max
            for bid in all_bids:
                if bid not in bid_ordering:
                    self.comparison_update(bid, min_bid)
                    self.comparison_update(max_bid, bid)

        self.update_bids_rank(all_bids)

    def get_bids_in_range(
        self, lower_importance: float, higher_importance: float, all_bids: AllBidsList
    ) -> list[Bid]:
        """
        Get bids within an importance range.

        Args:
            lower_importance: Lower bound of importance.
            higher_importance: Upper bound of importance.
            all_bids: All possible bids.

        Returns:
            List of bids within the range.
        """
        found_bids: list[Bid] = []
        for bid in all_bids:
            imp = self.get_importance(bid)
            if lower_importance <= imp <= higher_importance:
                found_bids.append(bid)
        return found_bids

    def get_bid_for_elicit(
        self, lower_importance: float, higher_importance: float, all_bids: AllBidsList
    ) -> Bid:
        """
        Get a bid to use for elicitation.

        Selects a bid with the least observed values to maximize information gain.

        Args:
            lower_importance: Lower bound of importance.
            higher_importance: Upper bound of importance.
            all_bids: All possible bids.

        Returns:
            A bid suitable for elicitation.
        """
        issue_values: dict[str, Value] = {}
        for issue in self._domain.getIssues():
            values = self._domain.getValues(issue)
            min_counter = float("inf")
            selected_value: Value | None = None
            for value in values:
                for unit in self.get(issue, []):
                    if unit.value_of_issue == value and unit.total_count < min_counter:
                        min_counter = unit.total_count
                        selected_value = value
                        break
            if selected_value is not None:
                issue_values[issue] = selected_value
        return Bid(issue_values)

    def update_bids_rank(self, all_bids: AllBidsList) -> None:
        """
        Update the bid rankings.

        Args:
            all_bids: All possible bids.
        """
        bids_imp: list[tuple[Bid, float]] = []

        for bid in all_bids:
            imp = self.get_importance(bid)
            self._bids_rank[bid] = imp
            bids_imp.append((bid, imp))

        bids_imp.sort(key=lambda x: x[1])
        self._sorted_bids = bids_imp

    def get_importance(self, bid: Bid) -> float:
        """
        Get the log-importance of a bid.

        Uses log-probability to avoid numerical underflow.

        Args:
            bid: The bid to evaluate.

        Returns:
            The log-importance score.
        """
        bid_importance = 0.0
        for issue in bid.getIssues():
            value = bid.getValue(issue)
            value_importance = 0.0
            for unit in self.get(issue, []):
                if unit.value_of_issue == value:
                    value_importance = unit.probability
                    break
            # Use log to avoid underflow
            if value_importance > 0:
                bid_importance += math.log(value_importance)
            else:
                bid_importance += -float("inf")
        return bid_importance

    def importance_to_rank_abs(self, importance: float) -> int:
        """
        Convert importance to absolute rank.

        Args:
            importance: The importance value.

        Returns:
            The rank (number of bids with lower importance).
        """
        rank = 0
        for bid, imp in self._bids_rank.items():
            if imp < importance:
                rank += 1
        return rank

    def get_best_bid(self, bids: list[Bid]) -> Bid | None:
        """
        Get the best bid from a list.

        Args:
            bids: List of bids to choose from.

        Returns:
            The bid with highest importance, or None if empty.
        """
        best_bid: Bid | None = None
        best_bid_imp = -float("inf")

        for bid in bids:
            bid_imp = self._bids_rank.get(bid, -float("inf"))
            if bid_imp > best_bid_imp:
                best_bid_imp = bid_imp
                best_bid = bid

        return best_bid

    def get_max_bid_imp(self) -> float:
        """
        Get the importance of the best bid.

        Returns:
            The maximum importance value.
        """
        if not self._sorted_bids:
            return 0.0
        return self._sorted_bids[-1][1]

    def rank_to_importance(self, rank: int) -> float:
        """
        Convert rank to importance.

        Args:
            rank: The bid rank.

        Returns:
            The importance at that rank.
        """
        if not self._sorted_bids or rank < 0 or rank >= len(self._sorted_bids):
            return 0.0
        return self._sorted_bids[rank][1]

    def get_bid_in_rank(self, rank: int) -> Bid | None:
        """
        Get the bid at a specific rank.

        Args:
            rank: The rank position.

        Returns:
            The bid at that rank, or None if invalid.
        """
        if not self._sorted_bids or rank < 0 or rank >= len(self._sorted_bids):
            return None
        return self._sorted_bids[rank][0]


class OpponentMap(ImpMap):
    """
    Opponent importance map for tracking opponent preferences.

    Uses frequency-based modeling to estimate opponent utility.
    """

    def __init__(self, profile: PartialOrdering):
        """
        Initialize the opponent map.

        Args:
            profile: The partial ordering profile.
        """
        super().__init__(profile)
        self._bids_rank: dict[Bid, float] = {}
        self._history_bids: list[Bid] = []

    def update_with_bid(self, received_bid: Bid) -> None:
        """
        Update opponent model with a new bid.

        Args:
            received_bid: The opponent's bid.
        """
        for issue in received_bid.getIssues():
            current_issue_list = self.get(issue, [])
            for unit in current_issue_list:
                if unit.value_of_issue == received_bid.getValue(issue):
                    unit.total_count += 1
                    break

        # Sort by count
        for imp_unit_list in self.values():
            imp_unit_list.sort(key=lambda x: x.total_count, reverse=True)

        self._history_bids.append(received_bid)

    def update_bids_rank(self, all_bids: AllBidsList) -> None:
        """
        Update bid rankings based on opponent model.

        Args:
            all_bids: All possible bids.
        """
        for bid in all_bids:
            self._bids_rank[bid] = self.get_importance(bid)

    def get_top_bids(self, bids: list[Bid], top_n: int) -> list[Bid]:
        """
        Get the top N bids by opponent importance.

        Args:
            bids: List of bids to choose from.
            top_n: Number of bids to return.

        Returns:
            List of top N bids.
        """
        if not bids:
            return []

        sorted_bids = sorted(bids, key=lambda b: self.get_importance(b), reverse=True)
        return sorted_bids[:top_n]

    def get_importance(self, bid: Bid) -> float:
        """
        Get opponent importance of a bid (frequency-based).

        Args:
            bid: The bid to evaluate.

        Returns:
            The total count score.
        """
        bid_importance = 0
        for issue in bid.getIssues():
            value = bid.getValue(issue)
            value_importance = 0
            for unit in self.get(issue, []):
                if unit.value_of_issue == value:
                    value_importance = unit.total_count
                    break
            bid_importance += value_importance
        return float(bid_importance)

    def get_bids_in_range(
        self, lower_importance: float, higher_importance: float, all_bids: AllBidsList
    ) -> list[Bid]:
        """
        Get bids within an importance range.

        Args:
            lower_importance: Lower bound.
            higher_importance: Upper bound.
            all_bids: All possible bids.

        Returns:
            List of bids in range.
        """
        found_bids: list[Bid] = []
        for bid in all_bids:
            imp = self.get_importance(bid)
            if lower_importance <= imp <= higher_importance:
                found_bids.append(bid)
        return found_bids


class SimpleLinearOrdering:
    """
    Simple linear ordering of bids from worst to best.

    Provides utility estimation based on bid position in the ordering.
    """

    def __init__(self, profile: PartialOrdering):
        """
        Initialize from a profile.

        Args:
            profile: The partial ordering profile.
        """
        self._domain = profile.getDomain()
        self._bids: list[Bid] = self._get_sorted_bids(profile)

    def _get_sorted_bids(self, profile: PartialOrdering) -> list[Bid]:
        """
        Get sorted bids from profile.

        Args:
            profile: The profile to extract bids from.

        Returns:
            List of bids sorted from worst to best.
        """
        if not isinstance(profile, DefaultPartialOrdering):
            return []

        bids_list = list(profile.getBids())
        # Sort ascending (worse bids first)
        bids_list.sort(key=lambda b1: 1 if profile.isPreferredOrEqual(b1, b1) else -1)
        return bids_list

    def get_bids(self) -> list[Bid]:
        """Get the ordered list of bids."""
        return list(self._bids)

    def getBids(self) -> list[Bid]:
        """Get bids (Java-style compatibility)."""
        return self.get_bids()


class Anaconda(DefaultParty):
    """
    ANAC 2020 Anaconda agent for SHAOP protocol.

    This agent uses importance maps to model both self and opponent preferences,
    with dynamic acceptance thresholds and preference elicitation.
    """

    DEFAULT_ELICITATION_COST: float = 0.01

    def __init__(self, reporter: Reporter | None = None):
        """
        Initialize the Anaconda agent.

        Args:
            reporter: Optional reporter for logging.
        """
        super().__init__(reporter)
        self._rand = random.Random()
        self._imp_map: SelfMap | None = None
        self._opponent_imp_map: OpponentMap | None = None

        self._received_bid: Bid | None = None
        self._partial_order_bids_count: int = 0
        self._self_bids_history: list[Bid] = []
        self._opp_bids_history: list[Bid] = []

        self._bid_space_size: int = 0

        self._profile_interface: ProfileInterface | None = None
        self._me: PartyId | None = None
        self._progress: Progress | None = None
        self._last_received_action: Action | None = None
        self._all_bids: AllBidsList | None = None

        self._top_n: int = 106
        self._reservation_bid: Bid | None = None
        self._elicitation_cost: float = self.DEFAULT_ELICITATION_COST
        self._lower_bound_rank: int = 0
        self._minimal_lower_bound_rank: int = 0
        self._dynamic_lower_bound_rank: int = 0

    def notifyChange(self, info: Inform) -> None:
        """
        Handle incoming information from the protocol.

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
                    self._opp_bids_history.append(self._received_bid)
                elif isinstance(self._last_received_action, Comparison):
                    current_bid = self._last_received_action.getBid()
                    worse_bids = self._last_received_action.getWorse()
                    better_bids = self._last_received_action.getBetter()

                    if self._imp_map is not None:
                        for worse_bid in worse_bids:
                            self._imp_map.comparison_update(current_bid, worse_bid)
                        for better_bid in better_bids:
                            self._imp_map.comparison_update(better_bid, current_bid)
                        for better_bid in better_bids:
                            for worse_bid in worse_bids:
                                self._imp_map.comparison_update(better_bid, worse_bid)

                    self._partial_order_bids_count += 1
                    if self._imp_map is not None and self._all_bids is not None:
                        self._imp_map.update_bids_rank(self._all_bids)

            elif isinstance(info, YourTurn):
                if self._progress is None:
                    return

                time = self._progress.get(int(self._current_time_millis()))

                if self._imp_map is not None and self._all_bids is not None:
                    # Elicitation
                    lower_imp = self._imp_map.rank_to_importance(self._lower_bound_rank)
                    upper_imp = self._imp_map.get_max_bid_imp()
                    b_star = self._get_bid_star(lower_imp, upper_imp)

                    if b_star is not None and self._should_elicit(b_star):
                        elicit_bid = self._imp_map.get_bid_for_elicit(
                            lower_imp, upper_imp, self._all_bids
                        )
                        elicit_action = ElicitComparison(
                            self._me, elicit_bid, list(self._all_bids)
                        )
                        self.getConnection().send(elicit_action)

                # Update parameters
                self._update_params(time)

                # Choose action
                action = self._choose_action()
                self.getConnection().send(action)

                if isinstance(action, Offer):
                    sent_bid = action.getBid()
                    self._self_bids_history.append(sent_bid)

                if isinstance(self._progress, ProgressRounds):
                    self._progress = self._progress.advance()

            elif isinstance(info, Finished):
                self.getReporter().log(logging.INFO, f"Final outcome: {info}")
                self.terminate()

        except Exception as e:
            self.getReporter().log(logging.WARNING, f"Failed to handle info: {e}")
            raise RuntimeError(f"Failed to handle info: {e}") from e

    def _current_time_millis(self) -> int:
        """Get current time in milliseconds."""
        import time

        return int(time.time() * 1000)

    def _update_params(self, time: float) -> None:
        """
        Update agent parameters based on time.

        Args:
            time: Current negotiation progress (0-1).
        """
        # Linear decay
        self._lower_bound_rank = int(
            round(
                (self._bid_space_size - 1)
                - time * ((self._bid_space_size - 1) - self._minimal_lower_bound_rank)
            )
        )

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SHAOP"},
            {"geniusweb.profile.PartialOrdering"},
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return "ANAC 2020 Anaconda SHAOP agent (AI-translated from Java)"

    def _init(self, settings: Settings) -> None:
        """
        Initialize the agent from settings.

        Args:
            settings: The negotiation settings.
        """
        self._me = settings.getID()
        self._progress = settings.getProgress()

        self._profile_interface = ProfileConnectionFactory.create(
            settings.getProfile().getURI(), self.getReporter()
        )

        profile = self._profile_interface.getProfile()
        if not isinstance(profile, PartialOrdering):
            raise ValueError("Anaconda requires a PartialOrdering profile")

        partial_profile = cast(PartialOrdering, profile)

        self._reservation_bid = profile.getReservationBid()
        self._elicitation_cost = self.DEFAULT_ELICITATION_COST

        self._all_bids = AllBidsList(partial_profile.getDomain())
        self._bid_space_size = int(self._all_bids.size())

        self._imp_map = SelfMap(partial_profile)
        self._opponent_imp_map = OpponentMap(partial_profile)

        # Get bids from profile
        ordering = SimpleLinearOrdering(partial_profile)
        ordered_bids = ordering.get_bids()

        # Update importance map
        self._imp_map.initial_update(ordered_bids, self._all_bids)
        self._partial_order_bids_count = len(ordered_bids)

        # Initialize lower bound and minimal lower bound
        self._lower_bound_rank = self._bid_space_size - 1

        if self._reservation_bid is not None:
            rb_sigma = math.sqrt(self._bid_variance(self._reservation_bid))
            u_rb = self._imp_map.get_importance(self._reservation_bid)
            rb_rank_abs = self._imp_map.importance_to_rank_abs(u_rb)
            rise = self._imp_map.importance_to_rank_abs(u_rb + rb_sigma) - rb_rank_abs
            fall = rb_rank_abs - self._imp_map.importance_to_rank_abs(u_rb - rb_sigma)
            rb_sigma_rank_abs = int(round((rise + fall) / 2.0))
            self._minimal_lower_bound_rank = rb_rank_abs + rb_sigma_rank_abs
        else:
            self._minimal_lower_bound_rank = 0

    def _choose_action(self) -> Action:
        """
        Choose the next action.

        Returns:
            The action to take.
        """
        if self._imp_map is None or self._me is None:
            raise RuntimeError("Agent not initialized")

        # Start competition - offer our max importance bid
        if not isinstance(self._last_received_action, Offer):
            best_bid = self._imp_map.get_bid_in_rank(self._bid_space_size - 1)
            if best_bid is not None:
                return Offer(self._me, best_bid)
            else:
                # Fallback
                return Offer(self._me, Bid({}))

        # Check acceptance
        if self._received_bid is not None:
            received_bid_imp = self._imp_map.get_importance(self._received_bid)
            received_bid_rank = self._imp_map.importance_to_rank_abs(received_bid_imp)

            if received_bid_rank >= self._lower_bound_rank:
                return Accept(self._me, self._received_bid)

        # Make offer
        lower_imp = self._imp_map.rank_to_importance(self._lower_bound_rank)
        upper_imp = self._imp_map.get_max_bid_imp()
        bids_intersection = self._get_intersecting_bids(lower_imp, upper_imp)

        bid_offer: Bid | None = None

        if not bids_intersection:
            # No intersection - use opponent model
            if self._opponent_imp_map is not None:
                optional_bids = self._opponent_imp_map.get_top_bids(
                    bids_intersection, self._top_n
                )
                if optional_bids:
                    bid_offer = optional_bids[
                        self._rand.randint(0, len(optional_bids) - 1)
                    ]
        else:
            best_bid = self._imp_map.get_best_bid(bids_intersection)
            if best_bid is not None:
                self._dynamic_lower_bound_rank = self._imp_map.importance_to_rank_abs(
                    self._imp_map.get_importance(best_bid)
                )
                bid_offer = best_bid

        if bid_offer is None:
            # Fallback to best bid
            bid_offer = self._imp_map.get_bid_in_rank(self._bid_space_size - 1)
            if bid_offer is None:
                bid_offer = Bid({})

        return Offer(self._me, bid_offer)

    def _get_intersecting_bids(self, lower_imp: float, upper_imp: float) -> list[Bid]:
        """
        Get bids that satisfy both self and opponent constraints.

        Args:
            lower_imp: Lower importance bound.
            upper_imp: Upper importance bound.

        Returns:
            List of intersecting bids.
        """
        if self._imp_map is None or self._all_bids is None:
            return []

        self_bids = self._imp_map.get_bids_in_range(
            lower_imp, upper_imp, self._all_bids
        )
        opp_bids = self._get_opp_optional_bids()
        self_bids_set = set(self_bids)

        intersection: list[Bid] = []
        for bid in opp_bids:
            if bid in self_bids_set:
                intersection.append(bid)

        return intersection

    def _get_opp_optional_bids(self) -> list[Bid]:
        """
        Get bids the opponent might accept.

        Returns:
            List of potential opponent bids.
        """
        if self._opponent_imp_map is None or self._all_bids is None:
            return []

        opp_lower_bound = self._find_olb()
        return self._opponent_imp_map.get_bids_in_range(
            opp_lower_bound, float("inf"), self._all_bids
        )

    def _bid_variance(self, bid: Bid | None, n_diff: int = 0) -> float:
        """
        Calculate the variance of a bid's importance estimate.

        Args:
            bid: The bid to evaluate.
            n_diff: Adjustment to observation count.

        Returns:
            The variance.
        """
        if bid is None or self._imp_map is None:
            return 0.0

        variance = 0.0
        for issue in bid.getIssues():
            current_issue_list = self._imp_map.get(issue, [])
            for unit in current_issue_list:
                n = unit.total_count + n_diff
                p = unit.probability
                variance += self._issue_variance(n, p)

        return variance

    def _issue_variance(self, n: int, p: float) -> float:
        """
        Calculate variance for a single issue-value.

        Uses a binomial-like variance calculation.

        Args:
            n: Number of observations.
            p: Probability estimate.

        Returns:
            The variance.
        """
        if n < 2:
            return 0.0

        # E(x) and E(x^2)
        e1 = 0.0
        e2 = 0.0

        # Initialize for k = 2
        n_choose_k = n * (n - 1) // 2
        pow_p_k = p * p
        pow_1_p_n_k = (1 - p) ** (n - 2) if p < 1 else 0.0

        for k in range(2, n + 1):
            log_k = math.log(k) if k > 0 else 0.0
            val = n_choose_k * pow_p_k * pow_1_p_n_k * log_k
            e1 += val
            e2 += val * log_k

            # Update for next iteration
            if p > 0 and p < 1:
                pow_p_k *= p
                pow_1_p_n_k /= (1 - p) if (1 - p) > 0 else 1
                n_choose_k = (n_choose_k * (n - k)) // (k + 1) if k + 1 <= n else 0
            else:
                break

        # Var(x) = E(x^2) - (E(x)^2)
        variance = e2 - e1 * e1
        return max(0.0, variance)

    def _should_elicit(self, b_star: Bid) -> bool:
        """
        Determine whether to elicit a comparison.

        Args:
            b_star: The best candidate bid.

        Returns:
            True if elicitation is worthwhile.
        """
        if (
            self._progress is None
            or self._imp_map is None
            or self._reservation_bid is None
        ):
            return False

        time = self._progress.get(int(self._current_time_millis()))

        u_b_star = self._imp_map.get_importance(b_star)
        u_rb = self._imp_map.get_importance(self._reservation_bid)

        rb_sigma = math.sqrt(self._bid_variance(self._reservation_bid))
        n = self._partial_order_bids_count
        rb_sigma_new = math.sqrt(self._bid_variance(self._reservation_bid, n - 2))

        rb_rank_abs = self._imp_map.importance_to_rank_abs(u_rb)
        rise = self._imp_map.importance_to_rank_abs(u_rb + rb_sigma) - rb_rank_abs
        fall = rb_rank_abs - self._imp_map.importance_to_rank_abs(u_rb - rb_sigma)
        rb_sigma_rank_abs = int(round((rise + fall) / 2.0))

        rise = self._imp_map.importance_to_rank_abs(u_rb + rb_sigma_new) - rb_rank_abs
        fall = rb_rank_abs - self._imp_map.importance_to_rank_abs(u_rb - rb_sigma_new)
        rb_sigma_new_rank_abs = int(round((rise + fall) / 2.0))

        u_olb = self._find_olb()
        olb = self._imp_map.importance_to_rank_abs(u_olb) / max(self._bid_space_size, 1)
        orb = 0.5  # Prior

        omlb_prior = orb + (1.0 * rb_sigma_rank_abs / max(self._bid_space_size, 1))

        if olb < omlb_prior:
            bid_almost_worst = self._imp_map.get_bid_in_rank(1)
            if bid_almost_worst is not None:
                bid_sigma = math.sqrt(self._bid_variance(bid_almost_worst))
                u_bid = self._imp_map.get_importance(bid_almost_worst)
                bid_sigma_rank_abs = self._imp_map.importance_to_rank_abs(
                    u_bid + bid_sigma
                ) - self._imp_map.importance_to_rank_abs(u_bid)
                bid_sigma_rank = bid_sigma_rank_abs / max(self._bid_space_size, 1)
                projection = (1 - olb) * time
                omlb_prior = max(bid_sigma_rank, projection)

        alpha = time
        omlb = alpha * olb + (1 - alpha) * omlb_prior
        seg_omlb = 1 - omlb

        p_diff = (
            1.0
            * (rb_sigma_new_rank_abs - rb_sigma_rank_abs)
            * seg_omlb
            / max(self._bid_space_size, 1)
        )

        # Avoid division by zero
        denominator = u_b_star - u_rb
        if abs(denominator) < 1e-10:
            return False

        return (self._elicitation_cost / denominator) < p_diff

    def _find_olb(self) -> float:
        """
        Find opponent's lower bound.

        Returns:
            The minimum opponent importance in their bid history.
        """
        if self._opponent_imp_map is None:
            return float("inf")

        min_bid_imp = float("inf")
        for bid in self._opp_bids_history:
            bid_imp = self._opponent_imp_map.get_importance(bid)
            if bid_imp < min_bid_imp:
                min_bid_imp = bid_imp

        return min_bid_imp

    def _get_bid_star(self, lower_imp: float, upper_imp: float) -> Bid | None:
        """
        Get the best bid in the acceptable range.

        Args:
            lower_imp: Lower importance bound.
            upper_imp: Upper importance bound.

        Returns:
            The best bid, or None if unavailable.
        """
        if self._imp_map is None:
            return None

        optional_bids = self._get_intersecting_bids(lower_imp, upper_imp)

        if not optional_bids:
            if self._reservation_bid is not None:
                rb_imp = self._imp_map.get_importance(self._reservation_bid)
                rb_rank = self._imp_map.importance_to_rank_abs(rb_imp)
                best_rank = self._bid_space_size - 1
                mid_bid_rank = round((rb_rank + best_rank) / 2)
                return self._imp_map.get_bid_in_rank(mid_bid_rank)
            return None

        return self._imp_map.get_best_bid(optional_bids)
