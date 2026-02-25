"""
AzarAgent - A SHAOP negotiation agent using GravityEs user model.

This agent was translated from the original Java implementation (ShaopParty.java)
from the ANAC 2020 competition. Translation was performed using AI assistance.

Original author: Arash Ebrahinezhad (Arash.ebrah@gmail.com, arash.ebrah@nit.ac.ir)

Strategy overview:
- Works with partial preferences using the GravityEs user model from ANAC 2019
- Uses frequency-based opponent modeling
- Implements a time-dependent bidding strategy (boulware/conceder)
- Supports elicitation in SHAOP mode with cost-aware decisions
- Gracefully handles SAOP mode by working with available utility information

Key components:
- GravityEs: Copeland-based user model for estimating bid utilities from orderings
- FrequencyModel: Opponent model using value frequency tracking
- USpace: Utility space for opponent modeling with normalized value weights
- SimpleLinearOrdering: Maintains ordered bid list for utility estimation
- BidHistory: Tracks bid exchange history for opponent modeling
"""

from __future__ import annotations

import logging
import random
import time as time_module
from decimal import Decimal
from typing import TYPE_CHECKING

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Comparison import Comparison
from geniusweb.actions.ElicitComparison import ElicitComparison
from geniusweb.actions.EndNegotiation import EndNegotiation
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


# =============================================================================
# Helper Classes
# =============================================================================


class MyBidDetails:
    """
    Container for a bid and its expected utility.

    Used for tracking bids and their estimated utilities during
    bidding strategy evaluation.
    """

    def __init__(self, bid: Bid | None, eu: float):
        """
        Initialize bid details.

        Args:
            bid: The bid (can be None if no valid bid found).
            eu: The expected utility of the bid.
        """
        self._bid = bid
        self._eu = eu

    def get_bid(self) -> Bid | None:
        """Get the bid."""
        return self._bid

    def get_eu(self) -> float:
        """Get the expected utility."""
        return self._eu


class BidHistory:
    """
    Tracks the history of bids exchanged during negotiation.

    Maintains separate lists for agent's own bids and opponent bids,
    and provides utilities for comparing consecutive bids.
    """

    def __init__(self, utility_space: USpace):
        """
        Initialize bid history.

        Args:
            utility_space: The utility space for the domain.
        """
        self._utility_space = utility_space
        self._my_bids: list[tuple[float, Bid]] = []
        self._opponent_bids: list[Bid] = []

    def add_my_bid(self, bid_entry: tuple[float, Bid]) -> None:
        """Add a bid entry to agent's bid history."""
        if bid_entry is None:
            raise ValueError("bid_entry can't be None")
        self._my_bids.append(bid_entry)

    def get_my_bid_count(self) -> int:
        """Get the number of agent's bids."""
        return len(self._my_bids)

    def get_my_bid(self, index: int) -> tuple[float, Bid]:
        """Get agent's bid at a specific index."""
        return self._my_bids[index]

    def get_my_last_bid(self) -> tuple[float, Bid] | None:
        """Get the last bid made by the agent."""
        if self._my_bids:
            return self._my_bids[-1]
        return None

    def add_opponent_bid(self, bid: Bid) -> None:
        """Add a bid to opponent's bid history."""
        if bid is None:
            raise ValueError("bid can't be None")
        self._opponent_bids.append(bid)

    def get_opponent_bid_count(self) -> int:
        """Get the number of opponent bids."""
        return len(self._opponent_bids)

    def get_opponent_bid(self, index: int) -> Bid:
        """Get opponent's bid at a specific index."""
        return self._opponent_bids[index]

    def get_opponent_last_bid(self) -> Bid | None:
        """Get the last bid from the opponent."""
        if self._opponent_bids:
            return self._opponent_bids[-1]
        return None

    def get_opponent_second_last_bid(self) -> Bid | None:
        """Get the second last bid from the opponent."""
        if len(self._opponent_bids) > 1:
            return self._opponent_bids[-2]
        return None

    def bid_difference(self, first: Bid, second: Bid) -> dict[str, int]:
        """
        Compare two bids and return which issues differ.

        Args:
            first: First bid to compare.
            second: Second bid to compare.

        Returns:
            Dict mapping issue names to 0 (same) or 1 (different).
        """
        diff: dict[str, int] = {}
        try:
            for issue in self._utility_space.get_domain().getIssues():
                first_val = first.getValue(issue)
                second_val = second.getValue(issue)
                diff[issue] = 0 if first_val == second_val else 1
        except Exception as e:
            logging.warning(f"Error in bid_difference: {e}")
        return diff

    def bid_difference_of_opponents_last_two(self) -> dict[str, int]:
        """
        Compare the last two opponent bids.

        Returns:
            Dict mapping issue names to 0 (same) or 1 (different).

        Raises:
            IndexError: If fewer than 2 opponent bids exist.
        """
        if self.get_opponent_bid_count() < 2:
            raise IndexError("Need at least 2 opponent bids")
        last = self.get_opponent_last_bid()
        second_last = self.get_opponent_second_last_bid()
        if last is None or second_last is None:
            raise IndexError("Could not get opponent bids")
        return self.bid_difference(last, second_last)


class USpace:
    """
    Utility space for opponent modeling.

    Maintains issue weights and value evaluations that are updated
    based on observed opponent behavior.
    """

    def __init__(self, domain: Domain):
        """
        Initialize utility space.

        Args:
            domain: The negotiation domain.
        """
        self._domain = domain
        self._weights: dict[str, float] = {}
        self._evals: dict[str, dict[Value, float]] = {}
        self._initialize()

    def _initialize(self) -> None:
        """Initialize weights and evaluations uniformly."""
        issues = list(self._domain.getIssues())
        w = 1.0 / len(issues) if issues else 0.0
        for issue in issues:
            self._weights[issue] = w
            values_dict: dict[Value, float] = {}
            for val in self._domain.getValues(issue):
                values_dict[val] = 1.0
            self._evals[issue] = values_dict

    def get_domain(self) -> Domain:
        """Get the domain."""
        return self._domain

    def set_weight(self, issue: str, w: float) -> None:
        """Set the weight for an issue."""
        self._weights[issue] = w

    def set_eval(self, issue: str, val: Value, evaluation: float) -> None:
        """Set the evaluation for a specific value of an issue."""
        if issue in self._evals:
            self._evals[issue][val] = evaluation

    def get_weights(self) -> dict[str, float]:
        """Get all issue weights."""
        return dict(self._weights)

    def get_evals(self) -> dict[str, dict[Value, float]]:
        """Get all value evaluations."""
        return {k: dict(v) for k, v in self._evals.items()}

    def get_weight(self, issue: str) -> float:
        """Get the weight for an issue."""
        return self._weights.get(issue, 0.0)

    def get_values(self, issue: str) -> dict[Value, float]:
        """Get the value evaluations for an issue."""
        return dict(self._evals.get(issue, {}))

    def get_value(self, issue: str, val: Value) -> float:
        """Get the evaluation for a specific value."""
        return self._evals.get(issue, {}).get(val, 0.0)

    def get_utility(self, bid: Bid) -> float:
        """
        Calculate the utility of a bid.

        Uses normalized value evaluations weighted by issue importance.

        Args:
            bid: The bid to evaluate.

        Returns:
            The utility value between 0 and 1.
        """
        # Find maximum value for each issue (for normalization)
        max_val_of_issue: dict[str, float] = {}
        for issue in self._domain.getIssues():
            max_val_of_issue[issue] = 0.0
            for val in self._domain.getValues(issue):
                val_eval = self.get_value(issue, val)
                if val_eval > max_val_of_issue[issue]:
                    max_val_of_issue[issue] = val_eval

        # Normalize evaluations
        evals_temp: dict[str, dict[Value, float]] = {}
        for issue in self._evals.keys():
            val_temp: dict[Value, float] = {}
            max_val = max_val_of_issue.get(issue, 1.0)
            if max_val == 0:
                max_val = 1.0
            for val in self.get_values(issue).keys():
                val_temp[val] = self.get_value(issue, val) / max_val
            evals_temp[issue] = val_temp

        # Calculate utility
        u = 0.0
        for issue, value in bid.getIssueValues().items():
            weight = self._weights.get(issue, 0.0)
            eval_val = evals_temp.get(issue, {}).get(value, 0.0)
            u += weight * eval_val

        return u

    def __str__(self) -> str:
        """String representation of the utility space."""
        s = "["
        for w in self._weights.keys():
            s += f"{w}=> W={self._weights[w]}=>["
            for val in self._evals.get(w, {}).keys():
                s += f"{val}={self._evals[w][val]}, "
        s += "]"
        return s


class FrequencyModel:
    """
    Frequency-based opponent model.

    Tracks opponent bid patterns to estimate their preferences by
    observing which issue values remain unchanged between bids.

    Based on the algorithm by Siamak Hajizadeh, Thijs van Krimpen, Daphne Looije.
    """

    LEARNING_COEF = 0.2
    LEARNING_VALUE_ADDITION = 1

    def __init__(self, utility_space: USpace):
        """
        Initialize the frequency model.

        Args:
            utility_space: The utility space for the domain.
        """
        self._bid_history = BidHistory(utility_space)
        self._opp_utility = utility_space
        self._domain = utility_space.get_domain()
        self._number_of_issues = len(self._domain.getIssues())
        self._opponent_last_bid: Bid | None = None

    def update_learner(self, bid: Bid) -> None:
        """
        Update the opponent model with a new bid.

        Args:
            bid: The received bid from the opponent.
        """
        self._opponent_last_bid = bid
        self._bid_history.add_opponent_bid(bid)

        if self._bid_history.get_opponent_bid_count() < 2:
            return

        number_of_unchanged = 0
        last_diff_set = self._bid_history.bid_difference_of_opponents_last_two()

        # Count unchanged issues
        for issue in last_diff_set.keys():
            if last_diff_set[issue] == 0:
                number_of_unchanged += 1

        # Calculate weight adjustments
        golden_value = self.LEARNING_COEF / self._number_of_issues
        total_sum = 1.0 + golden_value * number_of_unchanged
        maximum_weight = 1.0 - self._number_of_issues * golden_value / total_sum

        # Re-weigh issues
        for issue in last_diff_set.keys():
            current_weight = self._opp_utility.get_weight(issue)
            if last_diff_set[issue] == 0 and current_weight < maximum_weight:
                self._opp_utility.set_weight(
                    issue, (current_weight + golden_value) / total_sum
                )
            else:
                self._opp_utility.set_weight(issue, current_weight / total_sum)

        # Update value frequencies
        for issue, val in bid.getIssueValues().items():
            current_val = self._opp_utility.get_value(issue, val)
            self._opp_utility.set_eval(
                issue, val, current_val + self.LEARNING_VALUE_ADDITION
            )

    def get_opponent_utility_space(self) -> USpace:
        """Get the estimated opponent utility space."""
        return self._opp_utility


class SimpleLinearOrdering:
    """
    A simple list of bids ordered from worst to best.

    Used for maintaining preference orderings in SHAOP protocol.
    The first bid has utility 0, the last has utility 1.
    """

    def __init__(self, domain: Domain, bids: list[Bid] | None = None):
        """
        Initialize the ordering.

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
            profile: The profile (must be DefaultPartialOrdering).

        Returns:
            A new SimpleLinearOrdering.
        """
        if not isinstance(profile, DefaultPartialOrdering):
            raise ValueError("Only DefaultPartialOrdering supported")
        bids_list = list(profile.getBids())
        # Sort ascending by preference
        bids_list.sort(
            key=lambda b: sum(
                1 for other in bids_list if profile.isPreferredOrEqual(b, other)
            )
        )
        return cls(profile.getDomain(), bids_list)

    def get_domain(self) -> Domain:
        """Get the domain."""
        return self._domain

    def get_reservation_bid(self) -> Bid | None:
        """Get reservation bid (not supported)."""
        return None

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
        index = self._bids.index(bid)
        return Decimal(index) / Decimal(len(self._bids) - 1)

    def contains(self, bid: Bid) -> bool:
        """Check if bid is in the ordering."""
        return bid in self._bids

    def get_bids(self) -> list[Bid]:
        """Get the list of bids (worst to best)."""
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


class GravityEs:
    """
    GravityEs user model from ANAC 2019.

    Uses Copeland-based pairwise comparison to estimate issue and value
    utilities from a partial ordering of bids.

    This model builds utility estimates by analyzing which values tend
    to appear in higher-ranked bids and uses matrix operations to
    determine relative importance of issues.
    """

    def __init__(self, domain: Domain, bid_order: list[Bid]):
        """
        Initialize the GravityEs model.

        Args:
            domain: The negotiation domain.
            bid_order: List of bids ordered from worst to best.
        """
        self._domain = domain
        self._bid_order = bid_order
        self._issues_list: list[str] = list(domain.getIssues())
        self._number_of_issues = len(self._issues_list)

        # Index values for each issue
        # Note: Use getValues().getValues() to get a proper list, as the iterator
        # returned by getValues() (ItemIterator) doesn't support list comprehension
        self._issue_val_index: dict[str, list[Value]] = {}
        for issue in self._issues_list:
            values_obj = domain.getValues(issue)
            val_list = (
                list(values_obj.getValues())
                if hasattr(values_obj, "getValues")
                else list(values_obj)
            )
            self._issue_val_index[issue] = val_list

        # Copeland matrices for value comparison
        self._each_issue_values_matrix: dict[int, list[list[float]]] = {}
        self._each_issue_values_utility: dict[int, list[float]] = {}
        self._sum_squared_errors: list[float] = [0.0] * self._number_of_issues
        self._each_issue_utility: dict[int, float] = {}

        self._init_agent_variables()

    def _init_agent_variables(self) -> None:
        """Initialize agent variables and compute utilities."""
        self._create_copeland_matrices()
        self._fill_copeland_matrices()
        self._set_value_utilities()
        self._fill_matrice_of_no_change()
        self._set_issue_utilities_with_normalization()

    def _create_copeland_matrices(self) -> None:
        """Create empty Copeland comparison matrices for each issue."""
        for i, issue in enumerate(self._issues_list):
            value_size = len(self._issue_val_index[issue])
            matrix = [[0.0] * value_size for _ in range(value_size)]
            self._each_issue_values_matrix[i] = matrix

    def _fill_copeland_matrices(self) -> None:
        """
        Fill Copeland matrices with pairwise bid comparisons.

        For each pair of bids where one is preferred over another,
        updates the comparison matrices based on value similarities.
        """
        for i in range(len(self._bid_order) - 1, 0, -1):
            bigger_bid = self._bid_order[i]
            for j in range(i - 1, -1, -1):
                smaller_bid = self._bid_order[j]
                self._fill_copeland_with_comparison(bigger_bid, smaller_bid, i, j)

    def _fill_copeland_with_comparison(
        self, bigger_bid: Bid, smaller_bid: Bid, bigger_index: int, smaller_index: int
    ) -> None:
        """
        Update Copeland matrices for a pair of bids.

        Args:
            bigger_bid: The preferred bid.
            smaller_bid: The less preferred bid.
            bigger_index: Index of preferred bid.
            smaller_index: Index of less preferred bid.
        """
        for i, issue in enumerate(self._issues_list):
            bigger_value = bigger_bid.getValue(issue)
            bigger_idx = self._get_value_index(issue, bigger_value)
            smaller_value = smaller_bid.getValue(issue)
            smaller_idx = self._get_value_index(issue, smaller_value)
            num_similarities = self._count_equal_values(smaller_bid, bigger_bid)
            if num_similarities > 0 and bigger_idx >= 0 and smaller_idx >= 0:
                self._each_issue_values_matrix[i][bigger_idx][smaller_idx] += (
                    1.0 / (bigger_index - smaller_index)
                ) * num_similarities

    def _get_value_index(self, issue: str, value: Value | None) -> int:
        """Get the index of a value in an issue's value list."""
        if value is None:
            return -1
        val_list = self._issue_val_index.get(issue, [])
        for i, v in enumerate(val_list):
            if v == value:
                return i
        return -1

    def _count_equal_values(self, bid1: Bid, bid2: Bid) -> int:
        """Count the number of equal values between two bids."""
        count = 0
        for issue in bid2.getIssueValues().keys():
            if bid2.getValue(issue) == bid1.getValue(issue):
                count += 1
        return count

    def _set_value_utilities(self) -> None:
        """Calculate normalized utility for each value based on Copeland scores."""
        for i, issue in enumerate(self._issues_list):
            value_size = len(self._issue_val_index[issue])
            values_being_big_info: list[float] = []
            matrix = self._each_issue_values_matrix[i]

            for j in range(value_size):
                sum_row = self._get_sum_of_row(matrix, j)
                sum_col = self._get_sum_of_col(matrix, j)
                total = sum_col + sum_row
                if total == 0:
                    values_being_big_info.append(0.0)
                else:
                    being_big_percentage = sum_row / total
                    values_being_big_info.append(being_big_percentage)

            self._normalize_values(i, value_size, values_being_big_info)

    def _normalize_values(
        self, issue_idx: int, value_size: int, values_info: list[float]
    ) -> None:
        """Normalize value utilities to sum to 1."""
        utility_arr: list[float] = []
        total_sum = sum(values_info)
        for j in range(value_size):
            if total_sum == 0:
                utility_arr.append(0.0)
            else:
                utility_arr.append(values_info[j] / total_sum)
        self._each_issue_values_utility[issue_idx] = utility_arr

    def _fill_matrice_of_no_change(self) -> None:
        """Calculate standard deviation of matrix entries for issue weighting."""
        for i in range(self._number_of_issues):
            matrix = self._each_issue_values_matrix[i]
            sum_of_matrix = 0.0
            for j in range(len(matrix)):
                sum_of_matrix += self._get_sum_of_row(matrix, j)

            n_elements = len(matrix) * len(matrix)
            average = sum_of_matrix / n_elements if n_elements > 0 else 0.0

            sum_squared_errors = 0.0
            for j in range(len(matrix)):
                for k in range(len(matrix)):
                    sum_squared_errors += (matrix[j][k] - average) ** 2

            self._sum_squared_errors[i] = (
                (sum_squared_errors / n_elements) ** 0.5 if n_elements > 0 else 0.0
            )

    @staticmethod
    def _get_sum_of_row(matrix: list[list[float]], row: int) -> float:
        """Get sum of values in a row."""
        return sum(matrix[row])

    @staticmethod
    def _get_sum_of_col(matrix: list[list[float]], col: int) -> float:
        """Get sum of values in a column."""
        return sum(matrix[row][col] for row in range(len(matrix)))

    def _set_issue_utilities_with_normalization(self) -> None:
        """Set normalized issue utilities based on variance."""
        total_sum = sum(self._sum_squared_errors)
        for i in range(self._number_of_issues):
            if total_sum == 0:
                self._each_issue_utility[i] = 0.0
            else:
                self._each_issue_utility[i] = self._sum_squared_errors[i] / total_sum

    def get_utility_for_bid(self, bid: Bid | None) -> float:
        """
        Calculate the utility of a bid.

        Args:
            bid: The bid to evaluate.

        Returns:
            The utility value between 0 and 1.
        """
        if bid is None:
            return 0.0

        total_utility = 0.0
        for i, issue in enumerate(self._issues_list):
            utility_of_issue = self._each_issue_utility.get(i, 0.0)
            value = bid.getValue(issue)
            index_of_value = self._get_value_index(issue, value)
            if index_of_value >= 0:
                value_utilities = self._each_issue_values_utility.get(i, [])
                if index_of_value < len(value_utilities):
                    utility_of_value = value_utilities[index_of_value]
                    total_utility += utility_of_issue * utility_of_value

        return total_utility

    def update_gravity_model(self, bid_order: list[Bid]) -> GravityEs:
        """
        Create a new GravityEs model with updated bid ordering.

        Args:
            bid_order: The new bid ordering.

        Returns:
            A new GravityEs model.
        """
        return GravityEs(self._domain, bid_order)


# =============================================================================
# Main Agent Class
# =============================================================================


class AzarAgent(DefaultParty):
    """
    Azar Agent from ANAC 2020.

    A SHAOP agent that uses the GravityEs user model to estimate
    preferences from partial orderings, combined with frequency-based
    opponent modeling.

    Strategy:
    - Uses time-dependent (boulware) bidding strategy
    - Elicits comparisons when expected utility gain exceeds cost
    - Tracks opponent concession rate for acceptance decisions
    - Supports both SHAOP (with elicitation) and SAOP modes
    """

    def __init__(self, reporter: Reporter | None = None):
        """
        Initialize the Azar Agent.

        Args:
            reporter: Optional reporter for logging.
        """
        super().__init__(reporter)
        self._random = random.Random()

        # Bid tracking
        self._number_of_same_consecutive_bid = 0
        self._received_bid: Bid | None = None
        self._opp_bids: list[Bid] = []
        self._my_bids: list[Bid] = []
        self._bid_order: list[Bid] = []
        self._all_bid_size = 0
        self._expected_value: list[float] = []

        # Strategy parameters
        self._e = 0.8  # Boulware parameter
        self._k = 0.0
        self._after_rank = 2  # Ranks to check after estimated rank
        self._before_rank = 1  # Ranks to check before estimated rank
        self._agreement_similarity_threshold = 0.7
        self._opponent_concession_rate = 0.08
        self._how_many_rank_must_be_checked = 5
        self._p_agreement = 0.0
        self._my_concession_enough = False

        # Elicitation
        self._e_cost = 0.1  # Elicitation cost
        self._r_value = 0.0  # Reservation value
        self._total_bother = 0.0

        # Models
        self._op_model: FrequencyModel | None = None
        self._my_model: GravityEs | None = None

        # Protocol state
        self._reservation_bid: Bid | None = None
        self._me: PartyId | None = None
        self._profile_interface: ProfileInterface | None = None
        self._progress: Progress | None = None
        self._utility_space: USpace | None = None
        self._profile: Profile | None = None
        self._domain: Domain | None = None
        self._all_bids: AllBidsList | None = None
        self._estimated_profile: SimpleLinearOrdering | None = None

        # SAOP mode support
        self._is_saop_mode = False
        self._linear_additive_profile: LinearAdditive | None = None

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
                other_action = info.getAction()
                if isinstance(other_action, Offer):
                    actor = other_action.getActor()
                    # Only process offers from other parties
                    if actor != self._me:
                        self._received_bid = other_action.getBid()
                        if (
                            self._op_model is not None
                            and self._received_bid is not None
                        ):
                            self._op_model.update_learner(self._received_bid)
                elif isinstance(other_action, Comparison):
                    self._total_bother += self._e_cost
                    if self._estimated_profile is not None:
                        self._estimated_profile = (
                            self._estimated_profile.with_comparison(
                                other_action.getBid(), list(other_action.getWorse())
                            )
                        )
                        self._bid_order = self._estimated_profile.get_bids()
                        self._update_expected_utility()
                        if self._my_model is not None:
                            self._my_model = self._my_model.update_gravity_model(
                                self._bid_order
                            )
                        if (
                            self._reservation_bid is not None
                            and self._my_model is not None
                        ):
                            self._r_value = self._my_model.get_utility_for_bid(
                                self._reservation_bid
                            )
                    self._my_turn(elicitation=True)
            elif isinstance(info, YourTurn):
                self._my_turn(elicitation=False)
            elif isinstance(info, Finished):
                self.getReporter().log(logging.INFO, f"Final outcome: {info}")
                self.terminate()
        except Exception as e:
            raise RuntimeError(f"Failed to handle info: {e}") from e

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SHAOP", "SAOP"},
            {"geniusweb.profile.Profile"},
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return "Azar Agent ANAC 2020 (AI-translated from Java)"

    def _init(self, settings: Settings) -> None:
        """
        Initialize the agent with settings.

        Args:
            settings: The negotiation settings.
        """
        self._profile_interface = ProfileConnectionFactory.create(
            settings.getProfile().getURI(), self.getReporter()
        )
        self._me = settings.getID()
        self._progress = settings.getProgress()

        self._profile = self._profile_interface.getProfile()
        self._domain = self._profile.getDomain()
        self._utility_space = USpace(self._domain)
        self._all_bids = AllBidsList(self._domain)

        # Check if we're in SAOP mode with LinearAdditive profile
        if isinstance(self._profile, LinearAdditive):
            self._is_saop_mode = True
            self._linear_additive_profile = self._profile
            self._init_from_linear_additive()
        elif isinstance(self._profile, DefaultPartialOrdering):
            self._is_saop_mode = False
            self._init_from_partial_ordering()
        else:
            # Fallback: try to work with any profile
            self._is_saop_mode = False
            self._init_fallback()

        # Set up threshold based on reservation bid
        if self._reservation_bid is not None:
            self._agreement_similarity_threshold = 0.85
        else:
            self._agreement_similarity_threshold = 0.7

        # Get elicitation cost from parameters
        try:
            params = settings.getParameters()
            e_cost_param = params.get("elicitationcost")
            if e_cost_param is not None:
                self._e_cost = float(str(e_cost_param))
        except Exception:
            self._e_cost = 0.1

        # Get reservation bid from profile
        try:
            self._reservation_bid = self._profile.getReservationBid()
        except Exception:
            self._reservation_bid = None

        # Initialize opponent model
        self._op_model = FrequencyModel(self._utility_space)

        # Initialize expected value distribution
        self._all_bid_size = int(self._all_bids.size())
        self._expected_value = []
        self._init_expected_value()

        # Initialize user model
        self._my_model = GravityEs(self._domain, self._bid_order)

        # Set reservation value
        if self._reservation_bid is not None:
            self._r_value = self._my_model.get_utility_for_bid(self._reservation_bid)
        else:
            self._r_value = 0.0

    def _init_from_linear_additive(self) -> None:
        """Initialize from LinearAdditive profile (SAOP mode)."""
        if self._linear_additive_profile is None or self._all_bids is None:
            return

        # Sample and sort bids by utility
        sample_size = min(int(self._all_bids.size()), 200)
        sampled_bids: list[tuple[Bid, float]] = []

        for i in range(sample_size):
            if i < int(self._all_bids.size()):
                bid = self._all_bids.get(i)
                utility = float(self._linear_additive_profile.getUtility(bid))
                sampled_bids.append((bid, utility))

        # Sort by utility (ascending - worst first)
        sampled_bids.sort(key=lambda x: x[1])
        sorted_bids = [b for b, _ in sampled_bids]

        self._estimated_profile = SimpleLinearOrdering(self._domain, sorted_bids)
        self._bid_order = self._estimated_profile.get_bids()

    def _init_from_partial_ordering(self) -> None:
        """Initialize from partial ordering profile (SHAOP mode)."""
        self._estimated_profile = SimpleLinearOrdering.from_profile(self._profile)

        # If only 2 bids, add a third one
        if len(self._estimated_profile.get_bids()) == 2:
            bids = self._estimated_profile.get_bids()
            b_or = [bids[0]]

            # Try to add reservation bid or random bid
            if (
                self._reservation_bid is not None
                and self._reservation_bid != bids[0]
                and self._reservation_bid != bids[1]
            ):
                b_or.append(self._reservation_bid)
            else:
                # Add a random bid
                while True:
                    i = self._random.randint(0, int(self._all_bids.size()) - 1)
                    rand_bid = self._all_bids.get(i)
                    if rand_bid != bids[0] and rand_bid != bids[1]:
                        b_or.append(rand_bid)
                        break

            b_or.append(bids[1])
            self._estimated_profile = SimpleLinearOrdering(self._domain, b_or)

        self._bid_order = self._estimated_profile.get_bids()

    def _init_fallback(self) -> None:
        """Fallback initialization for other profile types."""
        # Create a minimal ordering with a random bid
        if self._all_bids is not None and int(self._all_bids.size()) > 0:
            random_bid = self._all_bids.get(0)
            self._estimated_profile = SimpleLinearOrdering(self._domain, [random_bid])
            self._bid_order = self._estimated_profile.get_bids()
        else:
            self._bid_order = []

    def _init_expected_value(self) -> None:
        """Initialize expected value distribution uniformly."""
        if len(self._bid_order) > 1:
            for _ in range(len(self._bid_order) - 1):
                self._expected_value.append(1.0 / (len(self._bid_order) - 1))

    def _update_expected_utility(self) -> None:
        """Update expected value distribution after elicitation."""
        self._expected_value.clear()
        if len(self._bid_order) > 1:
            for _ in range(len(self._bid_order) - 1):
                self._expected_value.append(1.0 / (len(self._bid_order) - 1))

    def _my_turn(self, elicitation: bool = False) -> None:
        """
        Execute the agent's turn.

        Args:
            elicitation: Whether this turn follows an elicitation response.
        """
        action: Action | None = None

        # Update agreement probability threshold
        if not elicitation and not self._my_concession_enough:
            t = self._get_time()
            self._p_agreement = self._get_p_agreement(t)

        # Elicitation and bidding strategy
        bid_detail: MyBidDetails | None = None

        if self._total_bother < 0.6 and not self._is_saop_mode:
            # Continue elicitation while under threshold
            bid_detail = self._get_best_bid_in_known_set(self._p_agreement, elicitation)
            bid_detail_prim = self._get_best_bid_in_unknown_set(self._p_agreement)

            # Check if elicitation is worth it
            if (
                bid_detail_prim.get_eu() - self._e_cost > bid_detail.get_eu()
                and self._estimated_profile is not None
                and bid_detail_prim.get_bid() is not None
            ):
                action = ElicitComparison(
                    self._me,
                    bid_detail_prim.get_bid(),
                    self._estimated_profile.get_bids(),
                )
        else:
            # Skip elicitation in SAOP mode or when budget exhausted
            bid_detail = self._get_best_bid_in_known_set(self._p_agreement, elicitation)

        # Fallback bid selection
        if bid_detail is None or bid_detail.get_bid() is None:
            if self._reservation_bid is not None:
                bid_detail = MyBidDetails(self._reservation_bid, 0.5)
            elif len(self._bid_order) > 10:
                bid_detail = MyBidDetails(
                    self._bid_order[len(self._bid_order) // 2], 1.0
                )
            elif self._bid_order:
                bid_detail = MyBidDetails(self._bid_order[-1], 1.0)
            else:
                # Last resort: pick a random bid
                if self._all_bids is not None and int(self._all_bids.size()) > 0:
                    random_bid = self._all_bids.get(
                        self._random.randint(0, int(self._all_bids.size()) - 1)
                    )
                    bid_detail = MyBidDetails(random_bid, 0.5)
                else:
                    bid_detail = MyBidDetails(None, 0.0)

        # Check acceptance
        if action is None and self._received_bid is not None:
            if bid_detail.get_bid() is not None and self._is_good(
                self._received_bid, bid_detail.get_bid()
            ):
                action = Accept(self._me, self._received_bid)

            if isinstance(self._progress, ProgressRounds):
                self._progress = self._progress.advance()

        # Make offer or end negotiation
        if action is None:
            my_bid = bid_detail.get_bid()

            if (
                my_bid is not None
                and self._my_model is not None
                and self._my_model.get_utility_for_bid(my_bid) > self._r_value
            ):
                # Track bid history
                if not self._my_bids:
                    self._my_bids.append(my_bid)
                if my_bid not in self._my_bids:
                    self._my_bids.append(my_bid)

                # Track consecutive same bids
                if len(self._my_bids) > 1:
                    if self._my_bids[-1] == self._my_bids[-2]:
                        self._number_of_same_consecutive_bid += 1
                    else:
                        self._number_of_same_consecutive_bid = 0

                action = Offer(self._me, my_bid)
            else:
                action = EndNegotiation(self._me)

        if action is not None:
            self.getConnection().send(action)

    def _get_time(self) -> float:
        """Get current negotiation time as fraction (0-1)."""
        if self._progress is not None:
            return self._progress.get(int(time_module.time() * 1000))
        return 0.0

    def _is_good(self, re_bid: Bid, next_bid: Bid) -> bool:
        """
        Acceptance strategy: determine if opponent's bid should be accepted.

        Args:
            re_bid: The received bid from opponent.
            next_bid: The next bid we would offer.

        Returns:
            True if we should accept the received bid.
        """
        if self._my_model is None:
            return False

        # Track opponent bid history
        if not self._opp_bids or re_bid not in self._opp_bids:
            self._opp_bids.append(re_bid)

        # Reject if below reservation value
        if self._my_model.get_utility_for_bid(re_bid) < self._r_value:
            return False

        # Accept if same as our next bid
        if re_bid == next_bid:
            return True

        # Accept if we offered this before
        if re_bid in self._my_bids:
            return True

        # Accept if better than our next bid
        if self._my_model.get_utility_for_bid(
            re_bid
        ) >= self._my_model.get_utility_for_bid(next_bid):
            return True

        # Accept if significantly better than any of our previous bids
        for b in self._my_bids:
            if (
                self._my_model.get_utility_for_bid(re_bid)
                >= self._my_model.get_utility_for_bid(b) + 0.07
            ):
                return True

        # Check similarity-based acceptance
        current_threshold = max(
            1 - self._p_agreement, self._agreement_similarity_threshold
        )
        acceptance_prob = self._get_acceptance_probability(re_bid, next_bid)

        return (
            acceptance_prob > current_threshold
            and self._my_model.get_utility_for_bid(re_bid) > self._r_value
        )

    def _get_acceptance_probability(self, re_bid: Bid, next_bid: Bid) -> float:
        """
        Calculate acceptance probability based on similarity to previous bids.

        Args:
            re_bid: The received bid.
            next_bid: Our next planned bid.

        Returns:
            Probability/similarity value between 0 and 1.
        """
        if self._my_model is None:
            return 0.0

        t = float("inf")
        re_bid_u = self._my_model.get_utility_for_bid(re_bid)

        for b in self._my_bids:
            temp = 1 - abs(self._my_model.get_utility_for_bid(b) - re_bid_u)
            if temp < t:
                t = temp

        next_bid_u = self._my_model.get_utility_for_bid(next_bid)
        if (1 - abs(next_bid_u - re_bid_u)) < t:
            return 1 - abs(next_bid_u - re_bid_u)

        return t if t != float("inf") else 0.0

    def _get_best_bid_in_known_set(
        self, p_agreement: float, elicitation: bool
    ) -> MyBidDetails:
        """
        Find the best bid from the known ordered set.

        Args:
            p_agreement: Minimum agreement probability threshold.
            elicitation: Whether this follows an elicitation response.

        Returns:
            MyBidDetails with the best bid found.
        """
        if self._my_model is None:
            return MyBidDetails(None, 0.0)

        for i in range(len(self._bid_order) - 1, 0, -1):
            bid = self._bid_order[i]
            pat = self._get_agreement_probability(bid)

            bid_utility = self._my_model.get_utility_for_bid(bid)

            if pat >= p_agreement and bid_utility > bid_utility / 2:
                # Check for too rapid concession
                if len(self._my_bids) > 1:
                    last_utility = self._my_model.get_utility_for_bid(self._my_bids[-1])
                    if last_utility - bid_utility > 0.3:
                        if bid_utility - 0.3 > 0:
                            return MyBidDetails(bid, bid_utility - 0.3)
                        else:
                            return MyBidDetails(None, 0.0)

                return MyBidDetails(bid, bid_utility)

        return MyBidDetails(None, 0.0)

    def _get_best_bid_in_unknown_set(self, p_agreement: float) -> MyBidDetails:
        """
        Find the best bid from the unknown (not yet ordered) set.

        Used for elicitation decisions.

        Args:
            p_agreement: Minimum agreement probability threshold.

        Returns:
            MyBidDetails with the best bid for elicitation.
        """
        if self._all_bids is None or self._my_model is None:
            return MyBidDetails(None, 0.0)

        best_eu = 0.0
        best_bid: Bid | None = None

        for i in range(int(self._all_bids.size())):
            bid = self._all_bids.get(i)

            if bid not in self._bid_order:
                pat = self._get_agreement_probability(bid)

                if pat > p_agreement:
                    estimate_rank = self._get_estimate_bid_rank(bid)

                    if (
                        estimate_rank
                        >= (len(self._bid_order) - 1)
                        - self._how_many_rank_must_be_checked
                    ):
                        temp_eu = self._get_new_eu(estimate_rank, bid)
                        temp_eeu = temp_eu

                        if temp_eeu > best_eu:
                            best_eu = temp_eeu
                            best_bid = bid

        if best_bid is not None:
            return MyBidDetails(best_bid, best_eu)
        return MyBidDetails(None, 0.0)

    def _get_estimate_bid_rank(self, bid: Bid) -> int:
        """
        Estimate the rank of a bid based on current model.

        Args:
            bid: The bid to rank.

        Returns:
            Estimated rank (0 = worst, higher = better).
        """
        if self._my_model is None:
            return 0

        temp_u = self._my_model.get_utility_for_bid(bid)
        rank = 0

        for b in self._bid_order:
            b_u = self._my_model.get_utility_for_bid(b)
            if temp_u <= b_u:
                break
            rank += 1

        if rank == 0:
            rank = 1

        return rank

    def _get_new_eu(self, rank: int, bid: Bid) -> float:
        """
        Calculate expected utility if a bid were to be elicited.

        Args:
            rank: Estimated rank of the bid.
            bid: The bid being considered.

        Returns:
            Expected utility after elicitation.
        """
        if self._domain is None or self._my_model is None:
            return 0.0

        self._expected_value = self._get_new_expected_value(rank)
        bid_order_size = len(self._bid_order)

        if rank == bid_order_size - 1:
            return self._my_model.get_utility_for_bid(bid)

        new_eu = 0.0

        # Check ranks after estimated rank
        after_count = 0
        for j in range(rank, min(rank + self._after_rank + 1, bid_order_size)):
            bid_order_copy = list(self._bid_order)

            if j - 1 >= 0 and j - 1 < len(self._expected_value):
                prob_belong = self._expected_value[j - 1]
            else:
                prob_belong = 0.0

            bid_order_copy.insert(j, bid)
            model_prob = GravityEs(self._domain, bid_order_copy)
            new_eu += prob_belong * model_prob.get_utility_for_bid(bid)
            after_count += 1

        # Check ranks before estimated rank
        if rank > 1:
            start_j = rank - 1
            end_j = max(0, max(after_count - 1, rank - self._before_rank))

            for j in range(start_j, end_j, -1):
                bid_order_copy = list(self._bid_order)

                if j - 1 >= 0 and j - 1 < len(self._expected_value):
                    prob_belong = self._expected_value[j - 1]
                else:
                    prob_belong = 0.0

                bid_order_copy.insert(j, bid)
                model_prob = GravityEs(self._domain, bid_order_copy)
                new_eu += prob_belong * model_prob.get_utility_for_bid(bid)

        return new_eu

    def _get_new_expected_value(self, rank: int) -> list[float]:
        """
        Calculate probability distribution of bid placement ranks.

        Args:
            rank: Estimated rank of the bid.

        Returns:
            List of probabilities for each possible rank.
        """
        certainty = (
            len(self._bid_order) / self._all_bid_size if self._all_bid_size > 0 else 0.0
        )

        expected = []
        if len(self._bid_order) > 1:
            for _ in range(len(self._bid_order)):
                expected.append(1.0 / (len(self._bid_order) - 1))
        else:
            return [1.0]

        # Adjust probabilities based on estimated rank
        temp1 = len(expected)
        for i in range(rank, 0, -1):
            if i - 1 < len(expected):
                expected[i - 1] = (temp1 * certainty) + expected[i - 1]
            temp1 -= 1

        temp2 = len(expected) - 1
        for i in range(rank + 1, len(expected) + 1):
            if i - 1 < len(expected):
                expected[i - 1] = (temp2 * certainty) + expected[i - 1]
            temp2 -= 1

        # Normalize
        total = sum(expected)
        if total > 0:
            expected = [e / total for e in expected]

        return expected

    def _f(self, t: float) -> float:
        """Time-dependent function for concession strategy."""
        if self._e == 0:
            return self._k
        return self._k + (1 - self._k) * (t ** (1 / self._e))

    def _get_p_agreement(self, t: float) -> float:
        """
        Get the agreement probability threshold based on time.

        Args:
            t: Current negotiation time (0-1).

        Returns:
            Agreement probability threshold.
        """
        return self._p_agreement + 0.01

    def _get_agreement_probability(self, bid: Bid) -> float:
        """
        Calculate probability that opponent will agree to a bid.

        Uses opponent model to estimate agreement likelihood.

        Args:
            bid: The bid to evaluate.

        Returns:
            Agreement probability between 0 and 1.
        """
        if self._op_model is None:
            return 1.0

        if not self._opp_bids:
            return 1.0

        if bid in self._my_bids:
            t = self._get_time()
            return self._opponent_concession_rate * t

        if bid in self._opp_bids:
            return 1.0

        t = float("inf")
        opp_utility_space = self._op_model.get_opponent_utility_space()

        for b in self._opp_bids:
            temp = 1 - abs(
                opp_utility_space.get_utility(b) - opp_utility_space.get_utility(bid)
            )
            if temp < t:
                t = temp

        return t if t != float("inf") else 0.0
