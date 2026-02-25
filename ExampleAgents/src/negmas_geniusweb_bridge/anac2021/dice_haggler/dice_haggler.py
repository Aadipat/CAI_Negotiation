"""
TheDiceHaggler2021 - A negotiation agent using Pareto estimation and TOPSIS.

This agent was translated from the original Java implementation from ANAC 2021.
Translation was performed using AI assistance.

Original strategy:
- Uses a time-dependent bidding strategy with multiple phases
- Phase 1 (t < 0.4): Boulware time-dependent concession
- Phase 2 (0.4 <= t <= 0.85): Pareto optimal bid generation using opponent model
- Phase 3 (t > 0.85): Random bids above target utility
- Uses TOPSIS for selecting best bid from Pareto front
- Frequency-based opponent modeling with chi-square statistical tests
- Adaptive acceptance strategy based on time and opponent history

Translation Notes:
-----------------
Complexity: Medium-High (multi-objective optimization, statistical modeling)

Simplifications made:
- **NSGA-II replaced with sampling-based Pareto estimation**: The original used
  the jMetal library's NSGA-II genetic algorithm for multi-objective optimization
  to find Pareto-optimal bids. This translation uses random sampling (500 bids)
  and dominance checking to approximate the Pareto front.
- Chi-square statistical test simplified to distance-based stability check for
  opponent issue weight updates
- Persistent state removed (original tracked opponent data across sessions)

Known differences from original:
- Pareto front quality may differ due to sampling vs NSGA-II optimization
- Original NSGA-II used 100 generations with population size 100; sampling
  approach may miss some Pareto-optimal solutions in large bid spaces
- Statistical significance testing for issue weight changes simplified
- No cross-session learning of opponent preferences

Library replacements:
- jMetal NSGA-II → Python sampling-based Pareto estimation (no external deps)
- Apache Commons Math chi-square → simplified distance-based comparison

Type handling:
- Uses `size.intValue() if hasattr(size, "intValue") else int(size)` pattern
  throughout for BigInteger compatibility
"""

from __future__ import annotations

import logging
import math
import random
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.DiscreteValue import DiscreteValue
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.Progress import Progress
from geniusweb.progress.ProgressRounds import ProgressRounds

if TYPE_CHECKING:
    from geniusweb.issuevalue.Domain import Domain
    from geniusweb.issuevalue.Value import Value
    from geniusweb.profileconnection.ProfileInterface import ProfileInterface
    from tudelft_utilities_logging.Reporter import Reporter


class DHIssue:
    """Represents an issue in the opponent model with weight and value utilities."""

    def __init__(self):
        self.issue_weight: float = 0.0
        self.value_utils: dict[str, float] = {}


class DHOpponentModel:
    """
    Frequency-based opponent modeling with statistical analysis.

    Tracks opponent bid history and estimates:
    - Issue weights (importance to opponent)
    - Value utilities (opponent's preference for each value)
    """

    def __init__(self, domain: "Domain"):
        self._domain = domain
        self._issues = list(domain.getIssuesValues().keys())
        self._opponent_model: dict[str, DHIssue] = {}
        self._window_size = 5
        self._alpha = 0.5
        self._beta = 0.5
        self._gamma = 0.3

    def initialize(self) -> dict[str, DHIssue]:
        """Initialize opponent model with uniform weights."""
        for issue in self._issues:
            dh_issue = DHIssue()
            dh_issue.issue_weight = 1.0 / len(self._issues)

            # Initialize value utilities to 1.0
            values = self._domain.getValues(issue)
            for i in range(
                values.size().intValue()
                if hasattr(values.size(), "intValue")
                else int(values.size())
            ):
                val = values.get(i)
                dh_issue.value_utils[str(val)] = 1.0

            self._opponent_model[issue] = dh_issue

        return self._opponent_model

    def update(
        self, current_time: float, opponent_history: list[Bid]
    ) -> dict[str, DHIssue]:
        """Update opponent model based on bid history."""
        if len(opponent_history) < 2 * self._window_size:
            return self._opponent_model

        # Get recent and previous windows
        current_window = opponent_history[-(self._window_size) :]
        previous_window = opponent_history[
            -(2 * self._window_size) : -(self._window_size)
        ]

        # Calculate frequency distributions
        prev_freq = self._calc_freq_distribution(previous_window)
        curr_freq = self._calc_freq_distribution(current_window)

        # Estimate issue values
        value_utils = self._estimate_issue_values(opponent_history)

        # Update issue weights
        self._update_issue_weights(prev_freq, curr_freq, value_utils, current_time)

        return self._opponent_model

    def _calc_freq_distribution(self, bids: list[Bid]) -> dict[str, list[float]]:
        """Calculate frequency distribution of values for each issue."""
        freq_dist: dict[str, list[float]] = {}

        for issue in self._issues:
            values = self._domain.getValues(issue)
            num_values = (
                values.size().intValue()
                if hasattr(values.size(), "intValue")
                else int(values.size())
            )
            counts = [0] * num_values

            for bid in bids:
                bid_val = bid.getValue(issue)
                for i in range(num_values):
                    if values.get(i) == bid_val:
                        counts[i] += 1
                        break

            # Convert to distribution
            total = sum(counts) + num_values  # Laplace smoothing
            freq_dist[issue] = [(c + 1) / total for c in counts]

        return freq_dist

    def _estimate_issue_values(self, history: list[Bid]) -> dict[str, list[float]]:
        """Estimate value utilities based on frequency."""
        value_utils: dict[str, list[float]] = {}

        for issue in self._issues:
            values = self._domain.getValues(issue)
            num_values = (
                values.size().intValue()
                if hasattr(values.size(), "intValue")
                else int(values.size())
            )
            counts = [0] * num_values

            # Count occurrences
            for bid in history:
                bid_val = bid.getValue(issue)
                for i in range(num_values):
                    if values.get(i) == bid_val:
                        counts[i] += 1
                        break

            # Calculate utilities using power function
            max_count = max(counts) if counts else 1
            utils = []
            for c in counts:
                util = ((c + 1) ** self._gamma) / ((max_count + 1) ** self._gamma)
                utils.append(util)

            value_utils[issue] = utils

            # Update opponent model values
            dh_issue = self._opponent_model[issue]
            for i in range(num_values):
                val_str = str(values.get(i))
                dh_issue.value_utils[val_str] = utils[i]

        return value_utils

    def _update_issue_weights(
        self,
        prev_freq: dict[str, list[float]],
        curr_freq: dict[str, list[float]],
        value_utils: dict[str, list[float]],
        current_time: float,
    ) -> None:
        """Update issue weights based on frequency stability."""
        stable_issues = []

        for issue in self._issues:
            # Check if distribution is stable (simplified chi-square approximation)
            prev = prev_freq[issue]
            curr = curr_freq[issue]

            # Calculate simple distance measure
            distance = sum(abs(p - c) for p, c in zip(prev, curr))

            # If distributions are similar, issue is stable (important)
            if distance < 0.3:  # Threshold for stability
                stable_issues.append(issue)

        # Increase weight of stable issues
        if stable_issues and len(stable_issues) < len(self._issues):
            delta = self._alpha * (1 - current_time**self._beta)
            for issue in stable_issues:
                self._opponent_model[issue].issue_weight += delta

        # Normalize weights
        total_weight = sum(dh.issue_weight for dh in self._opponent_model.values())
        if total_weight > 0:
            for dh_issue in self._opponent_model.values():
                dh_issue.issue_weight /= total_weight

    def get_opponent_utility(self, bid: Bid) -> float:
        """Estimate opponent utility for a bid."""
        utility = 0.0
        for issue in self._issues:
            if issue not in self._opponent_model:
                continue
            dh_issue = self._opponent_model[issue]
            val = bid.getValue(issue)
            val_util = dh_issue.value_utils.get(str(val), 0.5)
            utility += dh_issue.issue_weight * val_util
        return utility


class DHBiddingStrategy:
    """
    Time-dependent bidding strategy with Pareto optimization.

    Phases:
    - t < 0.4: Boulware concession
    - 0.4 <= t <= 0.85: Pareto optimal bids with TOPSIS selection
    - t > 0.85: Random bids above target
    - t > 0.95: Random bids above reservation threshold
    """

    def __init__(self, profile: LinearAdditive, opponent_model: DHOpponentModel):
        self._profile = profile
        self._opponent_model = opponent_model
        self._all_bids = AllBidsList(profile.getDomain())
        self._reservation_threshold = 0.75
        self._random = random.Random()

    def generate_bid(
        self,
        t: float,
        opponent_history: list[Bid],
    ) -> Bid:
        """Generate a bid based on current time and opponent history."""
        if t < 0.4:
            # Phase 1: Boulware strategy
            target = self._boulware_target(t)
            return self._get_bid_near_utility(target)

        elif t <= 0.85:
            # Phase 2: Pareto optimal with TOPSIS
            target = self._calculate_dynamic_target(t)
            try:
                pareto_bids = self._estimate_pareto_front(target)
                if len(pareto_bids) == 1:
                    selected = pareto_bids[0]
                else:
                    selected = self._topsis_select(t, pareto_bids)

                if float(self._profile.getUtility(selected)) >= target:
                    return selected
            except Exception:
                pass
            return self._generate_random_above_target(target)

        elif t <= 0.95:
            # Phase 3: Random above target
            target = self._calculate_dynamic_target(t)
            return self._generate_random_above_target(target)

        else:
            # Phase 4: Random above reservation
            return self._generate_random_above_target(self._reservation_threshold)

    def _boulware_target(self, t: float) -> float:
        """Calculate boulware target utility at time t."""
        p_min = self._get_min_utility()
        p_max = self._get_max_utility()
        e = 0.2  # Boulware constant
        k = 0
        f_t = k + (1 - k) * (t ** (1.0 / e))
        return p_min + (p_max - p_min) * (1 - f_t)

    def _calculate_dynamic_target(self, t: float) -> float:
        """Calculate dynamic target utility."""
        # Linear decrease from 0.95 at t=0.4 to ~0.83 at t=0.85
        return -0.27 * (t - 0.4) + 0.95

    def _get_min_utility(self) -> float:
        """Get minimum utility in bid space."""
        min_util = 1.0
        num_bids = self._all_bids.size()
        count = num_bids.intValue() if hasattr(num_bids, "intValue") else int(num_bids)
        for i in range(min(count, 1000)):  # Sample for large bid spaces
            bid = self._all_bids.get(i)
            util = float(self._profile.getUtility(bid))
            if util < min_util:
                min_util = util
        return min_util

    def _get_max_utility(self) -> float:
        """Get maximum utility in bid space."""
        max_util = 0.0
        num_bids = self._all_bids.size()
        count = num_bids.intValue() if hasattr(num_bids, "intValue") else int(num_bids)
        for i in range(min(count, 1000)):
            bid = self._all_bids.get(i)
            util = float(self._profile.getUtility(bid))
            if util > max_util:
                max_util = util
        return max_util

    def _get_bid_near_utility(self, target: float) -> Bid:
        """Get bid closest to target utility."""
        best_bid = None
        best_distance = float("inf")

        num_bids = self._all_bids.size()
        count = num_bids.intValue() if hasattr(num_bids, "intValue") else int(num_bids)

        for i in range(count):
            bid = self._all_bids.get(i)
            util = float(self._profile.getUtility(bid))
            distance = abs(util - target)
            if distance < best_distance:
                best_distance = distance
                best_bid = bid

        return best_bid if best_bid else self._all_bids.get(0)

    def _generate_random_above_target(self, target: float) -> Bid:
        """Generate random bid above target utility."""
        num_bids = self._all_bids.size()
        count = num_bids.intValue() if hasattr(num_bids, "intValue") else int(num_bids)

        for _ in range(100):
            idx = self._random.randint(0, count - 1)
            bid = self._all_bids.get(idx)
            if float(self._profile.getUtility(bid)) >= target:
                return bid

        # Fallback: return best bid found
        return self._get_bid_near_utility(target)

    def _estimate_pareto_front(self, min_self_util: float) -> list[Bid]:
        """
        Estimate Pareto front using simplified approach.

        Note: Original used NSGA-II optimization. This version uses
        a sampling-based approach to find non-dominated solutions.
        """
        candidates: list[tuple[Bid, float, float]] = []

        num_bids = self._all_bids.size()
        count = num_bids.intValue() if hasattr(num_bids, "intValue") else int(num_bids)

        # Sample bids
        sample_size = min(count, 500)
        indices = (
            self._random.sample(range(count), sample_size)
            if count > sample_size
            else range(count)
        )

        for i in indices:
            bid = self._all_bids.get(i)
            self_util = float(self._profile.getUtility(bid))

            if self_util < min_self_util:
                continue

            opp_util = self._opponent_model.get_opponent_utility(bid)
            candidates.append((bid, self_util, opp_util))

        if not candidates:
            # Fallback
            return [self._get_bid_near_utility(min_self_util)]

        # Find non-dominated solutions
        pareto_front: list[Bid] = []
        for bid, self_u, opp_u in candidates:
            dominated = False
            for other_bid, other_self, other_opp in candidates:
                if other_bid == bid:
                    continue
                # Check if other dominates current
                if (
                    other_self >= self_u
                    and other_opp >= opp_u
                    and (other_self > self_u or other_opp > opp_u)
                ):
                    dominated = True
                    break

            if not dominated:
                pareto_front.append(bid)

        return pareto_front if pareto_front else [candidates[0][0]]

    def _topsis_select(self, t: float, pareto_bids: list[Bid]) -> Bid:
        """
        Select best bid from Pareto front using TOPSIS.

        TOPSIS (Technique for Order of Preference by Similarity to Ideal Solution)
        weights shift from self-utility to opponent-utility over time.
        """
        # Weights shift linearly: self-weight decreases, opponent-weight increases
        self_weight = max(0.3, -0.6 * (t - 0.4) + 0.6)
        opp_weight = 1.0 - self_weight

        # Calculate utilities for all bids
        decision_matrix: list[tuple[Bid, float, float]] = []
        for bid in pareto_bids:
            self_util = float(self._profile.getUtility(bid))
            opp_util = self._opponent_model.get_opponent_utility(bid)
            decision_matrix.append((bid, self_util, opp_util))

        if not decision_matrix:
            return pareto_bids[0]

        # Normalize
        sum_self_sq = sum(d[1] ** 2 for d in decision_matrix)
        sum_opp_sq = sum(d[2] ** 2 for d in decision_matrix)

        norm_self = math.sqrt(sum_self_sq) if sum_self_sq > 0 else 1
        norm_opp = math.sqrt(sum_opp_sq) if sum_opp_sq > 0 else 1

        normalized = [
            (bid, (s / norm_self) * self_weight, (o / norm_opp) * opp_weight)
            for bid, s, o in decision_matrix
        ]

        # Find ideal best and worst
        best_self = max(n[1] for n in normalized)
        worst_self = min(n[1] for n in normalized)
        best_opp = max(n[2] for n in normalized)
        worst_opp = min(n[2] for n in normalized)

        # Calculate performance scores
        best_bid = None
        best_score = -1

        for bid, ns, no in normalized:
            # Distance to ideal best
            d_best = math.sqrt((ns - best_self) ** 2 + (no - best_opp) ** 2)
            # Distance to ideal worst
            d_worst = math.sqrt((ns - worst_self) ** 2 + (no - worst_opp) ** 2)

            # Performance score
            if d_best + d_worst > 0:
                score = d_worst / (d_best + d_worst)
            else:
                score = 0.5

            if score > best_score:
                best_score = score
                best_bid = bid

        return best_bid if best_bid else pareto_bids[0]


class TheDiceHaggler2021(DefaultParty):
    """
    A negotiation agent using Pareto estimation and TOPSIS selection.

    Features:
    - Multi-phase time-dependent strategy
    - Frequency-based opponent modeling
    - Pareto front estimation for win-win bids
    - TOPSIS decision making for bid selection
    - Adaptive acceptance strategy

    Note: This is a simplified translation that doesn't use NSGA-II optimization.
    """

    FIXED_UTILITY = 0.95
    RESERVATION_THRESHOLD = 0.75

    def __init__(self, reporter: "Reporter | None" = None):
        super().__init__(reporter)
        self._me: PartyId | None = None
        self._profile_interface: "ProfileInterface | None" = None
        self._progress: Progress | None = None
        self._profile: LinearAdditive | None = None
        self._opponent_name: str | None = None

        # Strategy components
        self._all_bids: AllBidsList | None = None
        self._opponent_model: DHOpponentModel | None = None
        self._bidding_strategy: DHBiddingStrategy | None = None

        # State
        self._received_bid: Bid | None = None
        self._opponent_history: list[Bid] = []
        self._time: float = 0.0

        # Persistent state (simplified)
        self._negotiation_data: dict[str, Any] = {
            "max_received_util": 0.0,
            "agreement_util": 0.0,
            "opponent_name": None,
        }

    def notifyChange(self, info: Inform) -> None:
        """Handle incoming information from the negotiation protocol."""
        try:
            if isinstance(info, Settings):
                self._handle_settings(info)
            elif isinstance(info, ActionDone):
                self._handle_action_done(info)
            elif isinstance(info, YourTurn):
                self._handle_your_turn()
            elif isinstance(info, Finished):
                self._handle_finished(info)
        except Exception as e:
            self.getReporter().log(logging.WARNING, f"Failed to handle info: {e}")
            raise RuntimeError(f"Failed to handle info: {e}") from e

    def _handle_settings(self, settings: Settings) -> None:
        """Initialize agent with settings."""
        self._me = settings.getID()
        self._progress = settings.getProgress()

        self._profile_interface = ProfileConnectionFactory.create(
            settings.getProfile().getURI(), self.getReporter()
        )

        profile = self._profile_interface.getProfile()
        if isinstance(profile, LinearAdditive):
            self._profile = profile
            self._all_bids = AllBidsList(profile.getDomain())
            self._opponent_model = DHOpponentModel(profile.getDomain())
            self._opponent_model.initialize()
            self._bidding_strategy = DHBiddingStrategy(profile, self._opponent_model)
            self._time = (
                self._progress.get(int(time.time() * 1000)) if self._progress else 0
            )

    def _handle_action_done(self, info: ActionDone) -> None:
        """Handle opponent's action."""
        action = info.getAction()

        if self._me is not None and action.getActor() != self._me:
            # Extract opponent name
            if self._opponent_name is None:
                full_name = action.getActor().getName()
                index = full_name.rfind("_")
                self._opponent_name = full_name[:index] if index > 0 else full_name
                self._negotiation_data["opponent_name"] = self._opponent_name

            # Process opponent's offer
            if isinstance(action, Offer):
                self._received_bid = action.getBid()

                if self._profile is not None:
                    util = float(self._profile.getUtility(self._received_bid))
                    if util > self._negotiation_data["max_received_util"]:
                        self._negotiation_data["max_received_util"] = util

                self._opponent_history.append(self._received_bid)

                # Update opponent model
                if self._opponent_model is not None:
                    self._time = (
                        self._progress.get(int(time.time() * 1000))
                        if self._progress
                        else 0
                    )
                    self._opponent_model.update(self._time, self._opponent_history)

    def _handle_your_turn(self) -> None:
        """Handle our turn to make an action."""
        if isinstance(self._progress, ProgressRounds):
            self._progress = self._progress.advance()

        self._time = (
            self._progress.get(int(time.time() * 1000)) if self._progress else 0
        )

        action: Action
        if self._received_bid is None:
            # First move: make opening bid
            bid = self._determine_opening_bid()
            action = Offer(self._me, bid)
        elif self._is_acceptable(self._received_bid):
            action = Accept(self._me, self._received_bid)
        else:
            # Generate counter-offer
            bid = (
                self._bidding_strategy.generate_bid(self._time, self._opponent_history)
                if self._bidding_strategy
                else self._determine_opening_bid()
            )
            action = Offer(self._me, bid)

        self.getConnection().send(action)

    def _determine_opening_bid(self) -> Bid:
        """Determine the opening bid."""
        if self._all_bids is None or self._profile is None:
            raise ValueError("Agent not properly initialized")

        num_bids = self._all_bids.size()
        count = num_bids.intValue() if hasattr(num_bids, "intValue") else int(num_bids)

        # Try to find a random bid above fixed utility
        rng = random.Random()
        for _ in range(100):
            idx = rng.randint(0, count - 1)
            bid = self._all_bids.get(idx)
            if float(self._profile.getUtility(bid)) >= self.FIXED_UTILITY:
                return bid

        # Fallback: find maximum utility bid
        best_bid = None
        best_util = 0.0
        for i in range(count):
            bid = self._all_bids.get(i)
            util = float(self._profile.getUtility(bid))
            if util > best_util:
                best_util = util
                best_bid = bid

        return best_bid if best_bid else self._all_bids.get(0)

    def _is_acceptable(self, bid: Bid) -> bool:
        """Determine if a bid is acceptable."""
        if self._profile is None or self._bidding_strategy is None:
            return False

        t = self._time
        bid_util = float(self._profile.getUtility(bid))

        # Get utility of our next potential bid
        next_bid = self._bidding_strategy.generate_bid(t, self._opponent_history)
        next_bid_util = float(self._profile.getUtility(next_bid))

        # Calculate percentile threshold
        q = abs(-1.67 * (t - 0.1) + 1.0)
        q_threshold = self._best_of_quantile(q)

        # Dynamic target utility
        dynamic_util = -0.27 * (t - 0.4) + 0.95 if t >= 0.4 else 0.9

        # Multi-phase acceptance
        if t < 0.1:
            return bid_util >= self.FIXED_UTILITY
        elif t < 0.4:
            return bid_util >= next_bid_util and bid_util > q_threshold
        elif t < 0.95:
            return bid_util >= dynamic_util and bid_util > q_threshold
        else:
            # Near deadline
            return bid_util >= self.RESERVATION_THRESHOLD

    def _best_of_quantile(self, q: float) -> float:
        """Get utility of best bid in bottom q quantile of opponent history."""
        if not self._opponent_history or self._profile is None:
            return 0.5

        # Sort by utility
        sorted_bids = sorted(
            self._opponent_history, key=lambda b: float(self._profile.getUtility(b))
        )

        # Get k-th percentile index
        k = int(q * len(sorted_bids)) - 1
        k = max(0, min(k, len(sorted_bids) - 1))

        return float(self._profile.getUtility(sorted_bids[k]))

    def _handle_finished(self, info: Finished) -> None:
        """Handle negotiation end."""
        agreements = info.getAgreements()

        if agreements and not agreements.getMap().isEmpty():
            agreement = list(agreements.getMap().values())[0]
            if self._profile is not None:
                util = float(self._profile.getUtility(agreement))
                self._negotiation_data["agreement_util"] = util

        self.getReporter().log(logging.INFO, f"Final outcome: {info}")
        self.terminate()

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SAOP", "Learn"},
            {"geniusweb.profile.utilityspace.LinearAdditive"},
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return (
            "TheDiceHaggler2021: Multi-phase negotiation agent using Pareto "
            "estimation and TOPSIS for bid selection. Features frequency-based "
            "opponent modeling. (AI-translated from Java, ANAC 2021)"
        )

    def terminate(self) -> None:
        """Clean up resources."""
        super().terminate()
        if self._profile_interface is not None:
            self._profile_interface.close()
            self._profile_interface = None
