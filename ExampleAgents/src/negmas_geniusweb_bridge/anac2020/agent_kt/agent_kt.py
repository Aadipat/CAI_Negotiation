"""
AgentKT (ShaopParty) - A SHAOP negotiation agent using elicitation and opponent modeling.

This agent was translated from the original Java implementation from ANAC 2020.
Translation was performed using AI assistance.

Original strategy:
- Uses elicitation to learn own utility function through pairwise comparisons
- Models opponent preferences through frequency analysis
- Uses COBYLA optimization (via scipy) to fit utility parameters
- Game-theoretic threshold calculation based on opponent behavior
- Supports both SAOP and SHAOP protocols
"""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

import numpy as np
from scipy.optimize import minimize

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Comparison import Comparison
from geniusweb.actions.ElicitComparison import ElicitComparison
from geniusweb.actions.EndNegotiation import EndNegotiation
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
    A simple list of bids with linear utility ordering.

    Bids are ordered from worst (index 0) to best (last index).
    The utility is calculated as the position in the list divided by list size.
    """

    def __init__(self, domain: Domain, bids: list[Bid] | None = None):
        """
        Initialize the ordering.

        Args:
            domain: The negotiation domain.
            bids: List of bids ordered from worst to best.
        """
        self._domain = domain
        self._bids: list[Bid] = list(bids) if bids else []

    @classmethod
    def from_profile(cls, profile: Profile) -> SimpleLinearOrdering:
        """
        Create ordering from a profile.

        Args:
            profile: The profile (must be DefaultPartialOrdering or LinearAdditive).

        Returns:
            A new SimpleLinearOrdering instance.

        Raises:
            ValueError: If profile type is not supported.
        """
        domain = profile.getDomain()

        if isinstance(profile, LinearAdditive):
            # For LinearAdditive, we don't have initial ordering
            # Return empty ordering that will be built through elicitation
            return cls(domain, [])
        elif isinstance(profile, DefaultPartialOrdering):
            bids_list = list(profile.getBids())
            # Sort ascending (worse bids first) using pairwise comparison
            for i in range(len(bids_list)):
                for j in range(i + 1, len(bids_list)):
                    if profile.isPreferredOrEqual(bids_list[i], bids_list[j]):
                        bids_list[i], bids_list[j] = bids_list[j], bids_list[i]
            return cls(domain, bids_list)
        else:
            raise ValueError(f"Unsupported profile type: {type(profile)}")

    def get_domain(self) -> Domain:
        """Get the domain."""
        return self._domain

    def get_bids(self) -> list[Bid]:
        """Get the list of bids (copy)."""
        return list(self._bids)

    def get_utility(self, bid: Bid) -> Decimal:
        """
        Get the utility of a bid.

        Args:
            bid: The bid to evaluate.

        Returns:
            Utility value between 0 and 1.
        """
        if len(self._bids) < 2 or bid not in self._bids:
            return Decimal(0)
        index = self._bids.index(bid)
        return Decimal(index).quantize(Decimal("0.00000001")) / Decimal(
            len(self._bids) - 1
        ).quantize(Decimal("0.00000001"))

    def contains(self, bid: Bid) -> bool:
        """Check if bid is in the ordering."""
        return bid in self._bids

    def with_comparison(self, bid: Bid, worse_bids: list[Bid]) -> SimpleLinearOrdering:
        """
        Create new ordering with an additional bid.

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

    def max_bid(self) -> Bid | None:
        """Get the maximum utility bid."""
        if not self._bids:
            return None
        return self._bids[-1]

    def min_bid(self) -> Bid | None:
        """Get the minimum utility bid."""
        if not self._bids:
            return None
        return self._bids[0]


class CompRegress:
    """
    Utility function learner using COBYLA optimization.

    Estimates utility weights for issue values based on pairwise comparisons.
    Uses scipy.optimize.minimize with COBYLA method for constrained optimization.
    """

    def __init__(
        self,
        profile: Profile,
        init_bid_order: list[Bid],
        indicator_bid_map: dict[Bid, str],
    ):
        """
        Initialize the regression model.

        Args:
            profile: The negotiation profile.
            init_bid_order: Initial list of bids ordered from worst to best.
            indicator_bid_map: Map of indicator bids to their issues.
        """
        self._domain = profile.getDomain()
        self._num_issues = len(self._domain.getIssues())
        self._min_bid = init_bid_order[0] if init_bid_order else None
        self._max_bid = init_bid_order[-1] if init_bid_order else None
        self._indicator_bid_map = indicator_bid_map

        # Issue ordering by importance (ascending)
        self._issue_order: list[str] = []
        # Theta weights for each issue (ascending order)
        self._est_theta: list[float] = []
        # Estimated utilities for each value
        self._est_util: dict[str, dict[Value, Decimal]] = {}
        # Non-min/max value indices for optimization
        self._non_min_max_index: dict[str, list[Value]] = {}
        # Number of values per issue
        self._num_values_per_issue: dict[str, int] = {}
        # Total number of non-min/max values
        self._total_non_min_max = 0
        # Full bid ordering
        self._full_bid_ordering: dict[Decimal, list[Bid]] = {}

        if init_bid_order and len(init_bid_order) >= 2:
            self._init_importance(init_bid_order)
            self._init_est_util_map()
            self.fit(init_bid_order)

    def _init_importance(self, init_bid_order: list[Bid]) -> None:
        """
        Initialize theta values and importance ordering of issues.

        Args:
            init_bid_order: Initial ordered bid list with indicator bids.
        """
        # Build issue importance ordered list from indicator bids
        count = self._num_issues
        index = len(init_bid_order) - 2  # Start from second to last

        while count > 0 and index >= 0:
            bid = init_bid_order[index]
            issue = self._indicator_bid_map.get(bid)
            if issue is not None:
                self._issue_order.append(issue)
                count -= 1
            index -= 1

        # Add any missing issues
        all_issues = list(self._domain.getIssues())
        for issue in all_issues:
            if issue not in self._issue_order:
                self._issue_order.insert(0, issue)

        # Initialize theta values
        if self._num_issues > 0:
            mult_inverse = 1.0 / self._num_issues
            min_theta = mult_inverse / 2.0
            incr = mult_inverse / max(self._num_issues - 1, 1)

            for i in range(self._num_issues):
                self._est_theta.append(min_theta + incr * i)

    def _init_est_util_map(self) -> None:
        """Initialize the HashMap of estimated utilities for each value."""
        for issue in self._issue_order:
            values = self._domain.getValues(issue)
            num_values = values.size().intValue()

            self._num_values_per_issue[issue] = num_values
            self._total_non_min_max += max(0, num_values - 2)

            self._est_util[issue] = {}
            self._non_min_max_index[issue] = []

            count = 1
            for value in values:
                if self._max_bid and value == self._max_bid.getValue(issue):
                    self._est_util[issue][value] = Decimal(1)
                elif self._min_bid and value == self._min_bid.getValue(issue):
                    self._est_util[issue][value] = Decimal(0)
                else:
                    # Initialize non-min/max values with spread around 0.5
                    init_val = 0.5 + 0.001 * (count - 0.5 * (num_values - 1))
                    self._est_util[issue][value] = Decimal(str(init_val))
                    self._non_min_max_index[issue].append(value)
                    count += 1

    def fit(self, ordered_bids: list[Bid]) -> None:
        """
        Update value utilities given a list of ordered bids.

        Uses COBYLA optimization to find utility values that respect the ordering.

        Args:
            ordered_bids: List of bids with ascending utility.
        """
        if not ordered_bids or self._total_non_min_max == 0:
            self._create_full_ordering()
            return

        num_bids = len(ordered_bids)
        num_constraints = num_bids - 1

        # Flatten estimated utilities to optimization vector
        x0 = self._flatten_est_util()

        # Define objective and constraints for COBYLA
        def objective(x: np.ndarray) -> float:
            """Minimize ordering inversions."""
            bid_utils = []
            for bid in ordered_bids:
                util = self._calc_bid_util(bid, x)
                bid_utils.append(util)

            # Penalize inversions
            err = 0.0
            for i in range(num_bids - 1):
                if bid_utils[i] > bid_utils[i + 1]:
                    err += bid_utils[i] - bid_utils[i + 1]
            return err / max(len(x), 1)

        def constraint(i: int):
            """Constraint: bid[i+1] utility >= bid[i] utility."""

            def cons_func(x: np.ndarray) -> float:
                util_i = self._calc_bid_util(ordered_bids[i], x)
                util_i1 = self._calc_bid_util(ordered_bids[i + 1], x)
                return util_i1 - util_i

            return cons_func

        # Build constraints list
        constraints = [
            {"type": "ineq", "fun": constraint(i)} for i in range(num_constraints)
        ]

        # Run COBYLA optimization
        try:
            result = minimize(
                objective,
                x0,
                method="COBYLA",
                constraints=constraints,
                options={"maxiter": 1000, "rhobeg": 1.0, "tol": 2.0e-4},
            )
            self._update_est_util(result.x)
        except Exception:
            # If optimization fails, keep current estimates
            pass

        self._create_full_ordering()

    def _calc_bid_util(self, bid: Bid, x: np.ndarray) -> float:
        """Calculate bid utility using current parameters."""
        util = 0.0
        base_index = 0

        for j, issue in enumerate(self._issue_order):
            value = bid.getValue(issue)
            if value is None:
                continue

            non_min_max = self._non_min_max_index.get(issue, [])
            if value in non_min_max:
                idx = non_min_max.index(value)
                if base_index + idx < len(x):
                    util += x[base_index + idx] * self._est_theta[j]
            else:
                est = self._est_util.get(issue, {}).get(value, Decimal(0))
                util += float(est) * self._est_theta[j]

            base_index += len(non_min_max)

        return util

    def _flatten_est_util(self) -> np.ndarray:
        """Flatten estimated utilities to a single array."""
        x = []
        for issue in self._issue_order:
            values_index = self._non_min_max_index.get(issue, [])
            for value in values_index:
                x.append(float(self._est_util.get(issue, {}).get(value, Decimal(0.5))))
        return np.array(x)

    def _update_est_util(self, x: np.ndarray) -> None:
        """Update estimated utilities from optimization result."""
        base_index = 0
        for issue in self._issue_order:
            values_index = self._non_min_max_index.get(issue, [])
            for i, value in enumerate(values_index):
                if base_index + i < len(x):
                    self._est_util[issue][value] = Decimal(str(x[base_index + i]))
            base_index += len(values_index)

    def _create_full_ordering(self) -> None:
        """Create full ordering of bids according to utility function."""
        self._full_bid_ordering = {}
        if self._max_bid:
            self._ordering_recursive(0, self._max_bid)

    def _ordering_recursive(self, i: int, bid: Bid) -> None:
        """Recursive helper to create bid ordering."""
        if i < len(self._issue_order):
            issue = self._issue_order[i]
            values = self._domain.getValues(issue)
            for value in values:
                new_bid = self._put_value(bid, issue, value)
                util = self.get_util(new_bid)
                if util not in self._full_bid_ordering:
                    self._full_bid_ordering[util] = []
                self._full_bid_ordering[util].append(new_bid)
                self._ordering_recursive(i + 1, new_bid)

    def get_util(self, bid: Bid | None) -> Decimal:
        """
        Calculate utility of a bid.

        Args:
            bid: The bid to evaluate.

        Returns:
            The estimated utility.
        """
        if bid is None:
            return Decimal(0)

        total_util = Decimal(0)
        for i, issue in enumerate(self._issue_order):
            value = bid.getValue(issue)
            if value is None:
                continue
            util = self._est_util.get(issue, {}).get(value, Decimal(0))
            if i < len(self._est_theta):
                total_util += util * Decimal(str(self._est_theta[i]))
        return total_util

    def get_issues(self) -> list[str]:
        """Get issues in ascending importance order."""
        return list(self._issue_order)

    def get_values(self, issue: str) -> ValueSet:
        """Get values for an issue."""
        return self._domain.getValues(issue)

    def get_better_than(self, threshold: Decimal) -> list[Bid]:
        """
        Get bids better than threshold.

        Args:
            threshold: Minimum utility threshold.

        Returns:
            List of bids with utility above threshold, in descending order.
        """
        better_bids = []
        # Sort keys in descending order
        for util in sorted(self._full_bid_ordering.keys(), reverse=True):
            if util <= threshold:
                break
            better_bids.extend(self._full_bid_ordering[util])

        if self._max_bid and self._max_bid not in better_bids:
            better_bids.append(self._max_bid)
        return better_bids

    def random_non_min_max(self, issue: str, index: int) -> Value | None:
        """Get a non-min/max value at index."""
        values = self._non_min_max_index.get(issue, [])
        if 0 <= index < len(values):
            return values[index]
        return None

    def _put_value(
        self, original_bid: Bid, input_issue: str, input_value: Value
    ) -> Bid:
        """Replace a value in a bid."""
        values: dict[str, Value] = {}
        for issue in original_bid.getIssues():
            if issue == input_issue:
                values[issue] = input_value
            else:
                value = original_bid.getValue(issue)
                if value is not None:
                    values[issue] = value
        return Bid(values)


class NegotiationInfo:
    """
    Stores and manages negotiation information including opponent modeling.

    Tracks bid history, opponent preferences, and calculates joint utilities.
    """

    def __init__(self, comp_regress: CompRegress):
        """
        Initialize negotiation info.

        Args:
            comp_regress: The utility regression model.
        """
        self._comp_regress = comp_regress
        self._issues = comp_regress.get_issues()

        self._my_bid_history: list[Bid] = []
        self._best_offered_bid_history: list[Bid] = []
        self._opponent_bid_history: list[Bid] = []

        self._opponent_sum = Decimal(0)
        self._opponent_pow_sum = Decimal(0)
        self._opponent_avg = Decimal(0)
        self._opponent_var = Decimal(0)

        self._value_relative_util: dict[str, dict[Value, Decimal]] = {}
        self._opponent_value_freq: dict[str, dict[Value, int]] = {}
        self._best_offered_util = Decimal(0)

        self._opponent_theta: dict[str, float] = {}
        self._est_opponent_util: dict[str, dict[Value, float]] = {}

        self._init_value_relative_util()

    def _init_value_relative_util(self) -> None:
        """Initialize relative utilities for all values."""
        for issue in self._issues:
            self._value_relative_util[issue] = {}
            values = self._comp_regress.get_values(issue)
            for value in values:
                self._value_relative_util[issue][value] = Decimal(0)

    def init_opponent(self) -> None:
        """Initialize opponent-related parameters."""
        self._init_opponent_value_freq()

    def _init_opponent_value_freq(self) -> None:
        """Initialize opponent value frequency tracking."""
        for issue in self._issues:
            self._opponent_value_freq[issue] = {}
            values = self._comp_regress.get_values(issue)
            for value in values:
                self._opponent_value_freq[issue][value] = 0

    def update_info(self, offered_bid: Bid) -> None:
        """
        Update negotiation info with new opponent bid.

        Args:
            offered_bid: The bid offered by opponent.
        """
        self._update_negotiating_info(offered_bid)
        self._update_freq_lists(offered_bid)

    def _update_negotiating_info(self, offered_bid: Bid) -> None:
        """Update statistics about opponent bids."""
        util = self._comp_regress.get_util(offered_bid)

        self._opponent_bid_history.append(offered_bid)
        self._opponent_sum += util
        self._opponent_pow_sum += util**2

        round_num = Decimal(len(self._opponent_bid_history))
        if round_num > 0:
            self._opponent_avg = self._opponent_sum / round_num
            self._opponent_var = (
                self._opponent_pow_sum / round_num
            ) - self._opponent_avg**2
            if self._opponent_var < 0:
                self._opponent_var = Decimal(0)

        if util > self._best_offered_util:
            self._best_offered_bid_history.append(offered_bid)
            self._best_offered_util = util

    def _update_freq_lists(self, offered_bid: Bid) -> None:
        """Update frequency counts for opponent values."""
        for issue in self._issues:
            value = offered_bid.getValue(issue)
            if value is not None and issue in self._opponent_value_freq:
                if value in self._opponent_value_freq[issue]:
                    self._opponent_value_freq[issue][value] += 1
                else:
                    self._opponent_value_freq[issue][value] = 1

    def update_my_bid_history(self, offer_bid: Bid) -> None:
        """Add bid to own history."""
        self._my_bid_history.append(offer_bid)

    def get_best_offered_bid(self) -> Bid | None:
        """Get best bid offered by opponent."""
        if not self._best_offered_bid_history:
            return None
        return self._best_offered_bid_history[-1]

    def get_best_offered_util(self) -> Decimal:
        """Get utility of best opponent bid."""
        return self._best_offered_util

    def init_opponent_probs(self) -> None:
        """Estimate opponent theta values and acceptance probabilities."""
        importance_map: dict[float, list[str]] = defaultdict(list)

        for issue in self._issues:
            total_freq = 0
            squared_sum = 0
            max_freq = 0
            max_freq_value: Value | None = None

            values = self._comp_regress.get_values(issue)
            self._est_opponent_util[issue] = {}

            for value in values:
                freq = self._opponent_value_freq.get(issue, {}).get(value, 0)
                total_freq += freq
                squared_sum += freq * freq
                if freq > max_freq:
                    max_freq = freq
                    max_freq_value = value

            for value in values:
                freq = self._opponent_value_freq.get(issue, {}).get(value, 0)
                if value == max_freq_value:
                    est_util = 1.0
                else:
                    if total_freq - max_freq == 0:
                        est_util = 0.0
                    else:
                        est_util = freq / (total_freq - max_freq)
                self._est_opponent_util[issue][value] = est_util

            # Calculate importance
            if total_freq - max_freq == 0:
                importance = 1.0
            else:
                importance = (
                    ((squared_sum - max_freq * max_freq) / (total_freq - max_freq))
                    + max_freq
                ) / max(total_freq, 1)
            importance_map[importance].append(issue)

        self._init_opponent_theta(importance_map)

    def _init_opponent_theta(self, importance_map: dict[float, list[str]]) -> None:
        """Create opponent theta values from importance map."""
        if not self._issues:
            return

        mult_inverse = 1.0 / len(self._issues)
        min_theta = mult_inverse / 2.0
        incr = mult_inverse / max(len(self._issues) - 1, 1)

        i = 0
        for importance in sorted(importance_map.keys()):
            issue_list = importance_map[importance]
            list_size = len(issue_list)
            theta = min_theta + incr * (i + 0.5 * (list_size - 1))
            for issue in issue_list:
                self._opponent_theta[issue] = theta
            i += list_size

    def get_joint_pref(self, my_pref_bids: list[Bid], time: float) -> list[Bid]:
        """
        Get bids ordered by joint utility preference.

        Args:
            my_pref_bids: List of my preferred bids.
            time: Current negotiation time.

        Returns:
            Bids ordered by joint utility (best first).
        """
        bias_factor = Decimal(str(1.8 - time * time * 0.3))
        joint_util: dict[Decimal, Bid] = {}

        for bid in my_pref_bids:
            opponent_util = Decimal(str(self._opponent_accept_prob(bid)))
            util = self._comp_regress.get_util(bid) * bias_factor + opponent_util
            joint_util[util] = bid

        return [joint_util[k] for k in sorted(joint_util.keys(), reverse=True)]

    def _opponent_accept_prob(self, bid: Bid) -> float:
        """Estimate opponent's acceptance probability for a bid."""
        prob = 0.0
        for issue in self._issues:
            value = bid.getValue(issue)
            if value is not None:
                theta = self._opponent_theta.get(issue, 0.0)
                util = self._est_opponent_util.get(issue, {}).get(value, 0.0)
                prob += theta * util
        return prob

    def update_comp_regress(self, new_comp_regress: CompRegress) -> None:
        """Update the utility regression model."""
        self._comp_regress = new_comp_regress


class NegotiationStrategy:
    """
    Negotiation strategy using game theory for threshold calculation.

    Uses a 2x2 game matrix to calculate acceptance thresholds based on
    expected opponent behavior.
    """

    PROB_FINAL = Decimal("0.5")  # Probability of compromising first in final round

    def __init__(
        self,
        comp_regress: CompRegress,
        negotiation_info: NegotiationInfo,
        reserve_bid: Bid | None,
    ):
        """
        Initialize negotiation strategy.

        Args:
            comp_regress: Utility regression model.
            negotiation_info: Negotiation information tracker.
            reserve_bid: Reservation bid.
        """
        self._comp_regress = comp_regress
        self._negotiation_info = negotiation_info
        self._reserve_value = comp_regress.get_util(reserve_bid)

        # Game matrix payoffs: A[strategy_self][strategy_opponent]
        # 1 = hardliner, 2 = conceder
        self._a11 = Decimal(0)  # hardliner vs hardliner
        self._a12 = Decimal(0)  # hardliner vs conceder
        self._a21 = Decimal(0)  # conceder vs hardliner
        self._a22 = Decimal(0)  # conceder vs conceder

    def select_accept(self, offered_bid: Bid | None, time: Decimal) -> bool:
        """
        Decide whether to accept an offered bid.

        Args:
            offered_bid: The bid offered by opponent.
            time: Current negotiation time.

        Returns:
            True if should accept.
        """
        if offered_bid is None:
            return False
        try:
            offered_bid_util = self._comp_regress.get_util(offered_bid)
            return offered_bid_util >= self.get_threshold(time)
        except Exception:
            return False

    def select_end_negotiation(self, time: Decimal) -> bool:
        """
        Decide whether to end negotiation.

        Args:
            time: Current negotiation time.

        Returns:
            True if should end negotiation.
        """
        return self._reserve_value >= self.get_threshold(time)

    def get_threshold(self, time: Decimal) -> Decimal:
        """
        Get acceptance threshold for current time.

        Args:
            time: Current negotiation time.

        Returns:
            Utility threshold for acceptance.
        """
        self._update_game_matrix()
        target = self._get_expected_util_in_final()

        # Linear interpolation from 1 to target
        threshold = target + (Decimal(1) - target) * (Decimal(1) - time)
        return threshold

    def _update_game_matrix(self) -> None:
        """Update the game theory payoff matrix."""
        util_concede = self._negotiation_info.get_best_offered_util()

        self._a11 = self._reserve_value
        self._a12 = Decimal(1)

        if util_concede >= self._reserve_value:
            self._a21 = util_concede
        else:
            self._a21 = self._reserve_value

        self._a22 = (
            self.PROB_FINAL * self._a21 + (Decimal(1) - self.PROB_FINAL) * self._a12
        )

    def _get_expected_util_in_final(self) -> Decimal:
        """Get expected utility in final round."""
        q = self._get_opponent_prob_hardliner()
        return q * self._a21 + (Decimal(1) - q) * self._a22

    def _get_opponent_prob_hardliner(self) -> Decimal:
        """Calculate opponent's probability of playing hardliner."""
        q = 1.0
        a11d = float(self._a11)
        a12d = float(self._a12)
        a21d = float(self._a21)
        a22d = float(self._a22)

        denom = a12d - a22d
        if denom != 0:
            ratio = (a11d - a21d) / denom
            if 1.0 - ratio != 0:
                q = 1.0 / (1.0 - ratio)

        if q < 0.0 or q > 1.0:
            q = 1.0

        return Decimal(str(q))


class AgentKT(DefaultParty):
    """
    AgentKT (ShaopParty) - ANAC 2020 SHAOP negotiation agent.

    AI-translated from Java implementation.

    Uses elicitation to learn own utility function through pairwise comparisons,
    models opponent preferences through frequency analysis, and uses game theory
    for acceptance threshold calculation.

    Supports both SAOP and SHAOP protocols. In SAOP mode with LinearAdditive
    profiles, elicitation is disabled and standard utility computation is used.
    """

    def __init__(self, reporter: Reporter | None = None):
        """
        Initialize the agent.

        Args:
            reporter: Optional reporter for logging.
        """
        super().__init__(reporter)
        self._random = random.Random()

        # Profile and connection
        self._profile_interface: ProfileInterface | None = None
        self._me: PartyId | None = None
        self._sender: PartyId | None = None
        self._progress: Progress | None = None

        # Domain info
        self._all_issues: list[str] = []

        # Models
        self._comp_regress: CompRegress | None = None
        self._est_profile: SimpleLinearOrdering | None = None
        self._negotiation_info: NegotiationInfo | None = None

        # Timing
        self._time: float = 0.0
        self._total_rounds: int = 0
        self._current_round: int = 0

        # Elicitation phase
        self._init_elicit_phase: int = 0
        self._init_offered_list: list[Bid] = []
        self._init_sent_list: list[Bid] = []
        self._indicator_bid_map: dict[Bid, str] = {}

        # Key bids
        self._max_bid: Bid | None = None
        self._min_bid: Bid | None = None
        self._reserve_bid: Bid | None = None
        self._my_last_bid: Bid | None = None
        self._best_joint_bid: Bid | None = None
        self._last_received_bid: Bid | None = None

        # State tracking
        self._offer_num: int = 0
        self._my_turn_num: int = 0
        self._elicit_num: int = 0
        self._thru_comparison: bool = False

        # Linear additive flag (for SAOP without elicitation)
        self._is_linear_additive: bool = False
        self._linear_profile: LinearAdditive | None = None

    def notifyChange(self, info: Inform) -> None:
        """
        Handle incoming information from the protocol.

        Args:
            info: The information received.
        """
        try:
            if isinstance(info, Settings):
                self._handle_settings(info)
            elif isinstance(info, ActionDone):
                self._handle_action_done(info)
            elif isinstance(info, YourTurn):
                if self._my_turn_num == 0:
                    self._my_turn_num = 1
                self._my_turn()
            elif isinstance(info, Finished):
                self.getReporter().log(logging.INFO, f"Final outcome: {info}")
                self.terminate()
        except Exception as e:
            raise RuntimeError(f"Failed to handle info: {e}") from e

    def _handle_settings(self, settings: Settings) -> None:
        """Initialize agent with settings."""
        self._profile_interface = ProfileConnectionFactory.create(
            settings.getProfile().getURI(), self.getReporter()
        )
        self._me = settings.getID()
        self._progress = settings.getProgress()
        self._init()

    def _handle_action_done(self, info: ActionDone) -> None:
        """Handle completed actions."""
        done_action = info.getAction()

        if isinstance(done_action, Offer):
            self._offer_num += 1
            if self._my_turn_num == 0:
                self._my_turn_num = 2
            self._received_offer(done_action)
            self._last_received_bid = done_action.getBid()
        elif isinstance(done_action, Comparison):
            self._thru_comparison = True
            if self._est_profile is not None:
                self._est_profile = self._est_profile.with_comparison(
                    done_action.getBid(), list(done_action.getWorse())
                )
                if self._comp_regress is not None:
                    self._comp_regress.fit(self._est_profile.get_bids())
                    if self._negotiation_info is not None:
                        self._negotiation_info.update_comp_regress(self._comp_regress)
            self._my_turn()

    def _init(self) -> None:
        """Initialize parameters."""
        if self._profile_interface is None:
            return

        profile = self._profile_interface.getProfile()

        # Check if we have a LinearAdditive profile (no elicitation needed)
        if isinstance(profile, LinearAdditive):
            self._is_linear_additive = True
            self._linear_profile = profile
            self._init_linear_additive()
            return

        # DefaultPartialOrdering profile (SHAOP with elicitation)
        issues = profile.getDomain().getIssues()
        self._all_issues = list(issues)

        self._time = 0.0
        self._offer_num = 0

        if isinstance(self._progress, ProgressRounds):
            self._total_rounds = self._progress.getTotalRounds()

        self._est_profile = SimpleLinearOrdering.from_profile(profile)

        self._max_bid = self._est_profile.max_bid()
        self._min_bid = self._est_profile.min_bid()
        self._reserve_bid = profile.getReservationBid()

        self._init_elicit_phase = len(self._all_issues)
        self._indicator_bid_map = {}
        self._init_offered_list = []
        self._init_sent_list = []

    def _init_linear_additive(self) -> None:
        """Initialize for LinearAdditive profile (no elicitation)."""
        if self._linear_profile is None:
            return

        domain = self._linear_profile.getDomain()
        self._all_issues = list(domain.getIssues())

        self._time = 0.0
        self._offer_num = 0

        if isinstance(self._progress, ProgressRounds):
            self._total_rounds = self._progress.getTotalRounds()

        # Find max and min bids by iterating through bid space
        from geniusweb.bidspace.AllBidsList import AllBidsList

        all_bids = AllBidsList(domain)
        max_util = Decimal(-1)
        min_util = Decimal(2)

        # Sample bids to find max/min
        sample_size = min(10000, int(all_bids.size()))
        for i in range(sample_size):
            bid = all_bids.get(i)
            util = self._linear_profile.getUtility(bid)
            if util > max_util:
                max_util = util
                self._max_bid = bid
            if util < min_util:
                min_util = util
                self._min_bid = bid

        self._reserve_bid = self._linear_profile.getReservationBid()
        self._init_elicit_phase = -1  # Skip elicitation

    def _init_elicit(self, index: int) -> Action:
        """
        Perform initial elicitation round.

        Args:
            index: Current elicitation index.

        Returns:
            ElicitComparison or Offer action.
        """
        self._init_elicit_phase -= 1

        if index > 0:
            issue = self._all_issues[index - 1]
            if self._min_bid and self._max_bid:
                min_value = self._min_bid.getValue(issue)
                if min_value:
                    indicator_bid = self._put_value(self._max_bid, issue, min_value)
                    self._indicator_bid_map[indicator_bid] = issue

                    if self._est_profile is not None:
                        return ElicitComparison(
                            self._me, indicator_bid, self._est_profile.get_bids()
                        )

        # After initial elicitation, initialize models
        self._init_comp_regress()
        return self._choose_offer()

    def _init_comp_regress(self) -> None:
        """Initialize CompRegress and NegotiationInfo after elicitation."""
        if self._profile_interface is None or self._est_profile is None:
            return

        profile = self._profile_interface.getProfile()
        self._comp_regress = CompRegress(
            profile, self._est_profile.get_bids(), self._indicator_bid_map
        )
        self._negotiation_info = NegotiationInfo(self._comp_regress)
        self._negotiation_info.init_opponent()

        for offered_bid in self._init_offered_list:
            self._negotiation_info.update_info(offered_bid)
        for sent_bid in self._init_sent_list:
            self._negotiation_info.update_my_bid_history(sent_bid)

    def _put_value(
        self, original_bid: Bid, input_issue: str, input_value: Value
    ) -> Bid:
        """Replace a value in a bid."""
        values: dict[str, Value] = {}
        for issue in original_bid.getIssues():
            if issue == input_issue:
                values[issue] = input_value
            else:
                value = original_bid.getValue(issue)
                if value is not None:
                    values[issue] = value
        return Bid(values)

    def _received_offer(self, done_action: Offer) -> None:
        """Handle received offer."""
        self._sender = done_action.getActor()
        offered_bid = done_action.getBid()

        if self._offer_num % 2 != self._my_turn_num % 2:
            if self._negotiation_info is None:
                self._init_offered_list.append(offered_bid)
            elif self._sender is not None:
                self._negotiation_info.update_info(offered_bid)
        else:
            self._my_last_bid = offered_bid

    def _my_turn(self) -> None:
        """Execute agent's turn."""
        self._time = self._get_current_time()
        action: Action | None = None

        if self._is_linear_additive:
            # Use linear additive strategy
            action = self._my_turn_linear()
        elif self._init_elicit_phase >= 0:
            # Initial elicitation phase
            if self._thru_comparison:
                self._thru_comparison = False
                action = Offer(self._me, self._max_bid)
                if isinstance(self._progress, ProgressRounds):
                    self._progress = self._progress.advance()
            else:
                action = self._init_elicit(self._init_elicit_phase)
        elif (
            self._elicit_num < 3
            and self._my_last_bid is not None
            and self._est_profile is not None
            and not self._est_profile.contains(self._my_last_bid)
        ):
            # Elicit comparison for opponent's counter-offer
            action = ElicitComparison(
                self._me, self._my_last_bid, self._est_profile.get_bids()
            )
            self._elicit_num += 1
        else:
            # Normal negotiation
            if self._current_round == self._total_rounds:
                action = self._choose_final()
            elif self._in_start_phase():
                action = self._choose_start()
            elif self._select_accept(self._last_received_bid):
                action = Accept(self._me, self._last_received_bid)
            elif self._in_mid_phase():
                action = self._choose_mid()
            else:
                action = self._choose_offer()

            if isinstance(self._progress, ProgressRounds):
                self._progress = self._progress.advance()

        if action is not None:
            self.getConnection().send(action)

    def _my_turn_linear(self) -> Action:
        """Handle turn for LinearAdditive profile."""
        if self._linear_profile is None or self._me is None:
            return Offer(self._me, self._max_bid)

        # Accept in final round
        if isinstance(self._progress, ProgressRounds):
            if self._progress.getCurrentRound() + 1 >= self._progress.getTotalRounds():
                if self._last_received_bid is not None:
                    return Accept(self._me, self._last_received_bid)

        # Check if should accept
        if self._last_received_bid is not None:
            util = self._linear_profile.getUtility(self._last_received_bid)
            threshold = Decimal(str(0.95 - self._time * self._time * 0.5))
            if util >= threshold:
                return Accept(self._me, self._last_received_bid)

        # Generate offer
        from geniusweb.bidspace.AllBidsList import AllBidsList

        domain = self._linear_profile.getDomain()
        all_bids = AllBidsList(domain)
        threshold = Decimal(str(0.95 - self._time * self._time * 0.5))

        # Find bids above threshold
        good_bids = []
        sample_size = min(1000, int(all_bids.size()))
        for i in range(sample_size):
            bid = all_bids.get(i)
            if self._linear_profile.getUtility(bid) >= threshold:
                good_bids.append(bid)

        if good_bids:
            return Offer(self._me, self._random.choice(good_bids))
        return Offer(self._me, self._max_bid)

    def _get_current_time(self) -> float:
        """Get current normalized time."""
        if isinstance(self._progress, ProgressRounds):
            self._total_rounds = self._progress.getTotalRounds()
            self._current_round = self._progress.getCurrentRound() + self._my_turn_num

            if self._total_rounds == 0:
                return 0.0
            return self._current_round / self._total_rounds
        return 0.0

    def _in_start_phase(self) -> bool:
        """Check if in start phase."""
        return self._time <= 0.5

    def _in_mid_phase(self) -> bool:
        """Check if in middle phase."""
        return self._time < 0.95

    def _choose_start(self) -> Action:
        """Choose action during start phase."""
        if self._comp_regress is None:
            return Offer(self._me, self._max_bid)

        threshold = Decimal(str(0.95 - self._time * self._time * 0.5))
        high_util_bids = self._comp_regress.get_better_than(threshold)

        if high_util_bids:
            random_bid = self._random.choice(high_util_bids)
            random_bid = self._replace_min(random_bid)
            return Offer(self._me, random_bid)
        return Offer(self._me, self._max_bid)

    def _choose_mid(self) -> Action:
        """Choose action during middle phase."""
        if self._comp_regress is None or self._negotiation_info is None:
            return Offer(self._me, self._max_bid)

        init_threshold = Decimal(str(0.95 - self._time * self._time * 0.5))
        init_high_util_bids = self._comp_regress.get_better_than(init_threshold)

        self._negotiation_info.init_opponent_probs()
        joint_ordered_bids = self._negotiation_info.get_joint_pref(
            init_high_util_bids, self._time
        )

        if joint_ordered_bids:
            joint_threshold = self._comp_regress.get_util(joint_ordered_bids[0])
            threshold = max(init_threshold, joint_threshold)
        else:
            threshold = init_threshold

        high_util_bids = self._comp_regress.get_better_than(threshold)

        if high_util_bids:
            random_bid = self._random.choice(high_util_bids)
            random_bid = self._replace_min(random_bid)
            return Offer(self._me, random_bid)
        return Offer(self._me, self._max_bid)

    def _replace_min(self, bid: Bid) -> Bid:
        """Replace minimum values with random non-min values."""
        if self._comp_regress is None or self._min_bid is None:
            return bid

        new_bid = bid
        for issue in bid.getIssues():
            value = bid.getValue(issue)
            if value is None:
                continue

            values = self._comp_regress.get_values(issue)
            value_set_size = values.size().intValue()

            if value == self._min_bid.getValue(issue) and value_set_size > 2:
                i = self._random.randint(0, value_set_size - 3)
                new_value = self._comp_regress.random_non_min_max(issue, i)
                if new_value:
                    new_bid = self._put_value(new_bid, issue, new_value)

        return new_bid

    def _choose_final(self) -> Action:
        """Choose action in final round."""
        if self._my_turn_num == 1:
            return Offer(self._me, self._best_joint_bid or self._max_bid)
        elif self._comp_regress is not None and self._last_received_bid is not None:
            if self._comp_regress.get_util(
                self._last_received_bid
            ) > self._comp_regress.get_util(self._reserve_bid):
                return Accept(self._me, self._last_received_bid)
        return EndNegotiation(self._me)

    def _select_accept(self, bid: Bid | None) -> bool:
        """Decide whether to accept a bid."""
        if bid is None or self._comp_regress is None or self._negotiation_info is None:
            return False

        strategy = NegotiationStrategy(
            self._comp_regress, self._negotiation_info, self._reserve_bid
        )
        return strategy.select_accept(bid, Decimal(str(self._time)))

    def _choose_offer(self) -> Action:
        """Choose offer during remainder phases."""
        if self._comp_regress is None or self._negotiation_info is None:
            return Offer(self._me, self._max_bid)

        threshold = Decimal(str(0.85 - self._time * self._time * 0.15))
        high_util_bids = self._comp_regress.get_better_than(threshold)

        self._negotiation_info.init_opponent_probs()
        joint_ordered_bids = self._negotiation_info.get_joint_pref(
            high_util_bids, self._time
        )

        if joint_ordered_bids:
            self._best_joint_bid = joint_ordered_bids[0]
        else:
            self._best_joint_bid = self._max_bid

        return self._offer_bid_action(self._best_joint_bid)

    def _offer_bid_action(self, offer_bid: Bid | None) -> Action:
        """Create offer action and update history."""
        if offer_bid is None:
            offer_bid = self._max_bid

        if self._negotiation_info is not None and offer_bid is not None:
            self._negotiation_info.update_my_bid_history(offer_bid)

        return Offer(self._me, offer_bid)

    def getCapabilities(self) -> Capabilities:
        """
        Return agent capabilities.

        Returns:
            Capabilities indicating SAOP and SHAOP protocol support.
        """
        return Capabilities(
            {"SAOP", "SHAOP"},
            {"geniusweb.profile.Profile"},
        )

    def getDescription(self) -> str:
        """
        Return agent description.

        Returns:
            Description string.
        """
        return "AgentKT - ANAC 2020 SHAOP agent using elicitation and game theory (AI-translated from Java)"
