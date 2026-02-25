"""
MatrixAlienAgent - Adaptive boulware-style negotiation agent.

This agent was translated from the original Java implementation from ANAC 2021.
Translation was performed using AI assistance.

Original strategy:
- Uses a boulware concession curve with adaptive e and min parameters
- Learns from previous negotiations to adjust boulware constant (e) and min utility
- Multi-factor bid scoring: goal utility, self utility, opponent utility, exploration, random
- Tracks best offer from opponent and considers it for acceptance/offers
- Supports persistent state across negotiation sessions

University of Tulsa MASTERS submission for ANAC 2021.

Translation Notes:
-----------------
Complexity: Medium (multiple helper classes, learning logic)

Simplifications made:
- Persistent state stored in memory only (PersistentState class simplified).
  Original used file-based JSON storage to persist e_vals, mins, and opponent
  encounter data across JVM sessions.
- Opponent model (opp_model parameter in get_action) always passed as None in
  current implementation - opponent utility scoring disabled

Known differences from original:
- No file I/O for persistence - e and min learning only works within a session
- First negotiation with any opponent uses INITIAL_E (0.00033) and INITIAL_MIN (0.5)
- The adaptive e/min adjustment logic works but resets on process restart
- Gaussian noise parameters (sm, em, ss, es) use defaults, not learned values

Library replacements:
- None required - uses standard Python libraries and Decimal for precision

Type handling:
- Uses `size.intValue() if hasattr(size, "intValue") else int(size)` pattern
  for BigInteger vs int compatibility in BidChooser class
"""

from __future__ import annotations

import logging
import math
import random
import time
from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.bidspace.BidsWithUtility import BidsWithUtility
from geniusweb.bidspace.Interval import Interval
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
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
    from geniusweb.profile.Profile import Profile
    from geniusweb.profileconnection.ProfileInterface import ProfileInterface
    from tudelft_utilities_logging.Reporter import Reporter


class BidChooser:
    """
    Chooses bids based on multiple weighted factors.

    Factors:
    - Goal utility: prefer bids close to target utility
    - Self utility: prefer higher utility for self
    - Opponent utility: prefer higher estimated opponent utility
    - Exploration: prefer less frequently offered bids
    - Random: add randomness to bid selection
    """

    def __init__(self, util_space: LinearAdditive, random_seed: int | None = None):
        self._util_space = util_space
        self._bid_utils = BidsWithUtility.create(util_space)
        self._bid_counts: dict[Bid, Decimal] = defaultdict(lambda: Decimal(0))
        self._random = random.Random(random_seed)

        # Compute min/max utilities
        range_interval = self._bid_utils.getRange()
        self._min_util = range_interval.getMin()
        self._max_util = range_interval.getMax()

        # Check reservation bid
        rv_bid = util_space.getReservationBid()
        if rv_bid is not None:
            rv_util = util_space.getUtility(rv_bid)
            if rv_util > self._min_util:
                self._min_util = rv_util

        # Compute tolerance for bid range
        self._tolerance_guess = self._compute_tolerance_guess()

    def _compute_tolerance_guess(self) -> Decimal:
        """Compute minimum tolerance for bid utility range."""
        tolerance = Decimal(1)
        for iss_info in self._bid_utils.getInfo():
            values = iss_info.getValues()
            values_size = values.size()
            num_values = (
                values_size.intValue()
                if hasattr(values_size, "intValue")
                else int(values_size)
            )
            if num_values > 1:
                # Get weighted utilities for all values
                weighted_utils = []
                for i in range(num_values):
                    val = values.get(i)
                    weighted_utils.append(iss_info.getWeightedUtil(val))

                weighted_utils.sort(reverse=True)

                # Find max difference between consecutive utilities
                issue_tolerance = Decimal(0)
                for i in range(1, len(weighted_utils)):
                    diff = weighted_utils[0] - weighted_utils[i]
                    issue_tolerance = max(issue_tolerance, diff)

                tolerance = min(tolerance, issue_tolerance)

        return tolerance

    @property
    def min_util(self) -> Decimal:
        return self._min_util

    @property
    def max_util(self) -> Decimal:
        return self._max_util

    def count_bid(self, bid: Bid) -> Decimal:
        """Record that a bid was seen and return its count."""
        self._bid_counts[bid] += Decimal(1)
        return self._bid_counts[bid]

    def get_bid_count(self, bid: Bid) -> Decimal:
        """Get how many times a bid was seen."""
        return self._bid_counts.get(bid, Decimal(0))

    def get_bids(self, min_utility: Decimal, max_utility: Decimal) -> Any:
        """Get bids within utility range [min_utility, max(max_utility, min_utility+tolerance)]."""
        min_u = min(min_utility, Decimal(1))
        max_u = min(max(max_utility, min_utility + self._tolerance_guess), Decimal(1))
        return self._bid_utils.getBids(Interval(min_u, max_u))

    def choose_bid(
        self,
        min_utility: Decimal,
        max_utility: Decimal,
        goal_utility: Decimal,
        goal_weight: Decimal = Decimal(1),
        self_weight: Decimal = Decimal(0),
        opp_weight: Decimal = Decimal(0),
        opp_model: UtilitySpace | None = None,
        explore_weight: Decimal = Decimal(0),
        random_weight: Decimal = Decimal(0),
    ) -> Bid:
        """Choose a bid using multiple weighted factors."""
        bids = self.get_bids(min_utility, max_utility)

        bid_size = bids.size()
        num_bids = (
            bid_size.intValue() if hasattr(bid_size, "intValue") else int(bid_size)
        )

        if num_bids == 0:
            # Fallback to max utility bids
            return self.get_bids(self._max_util, self._max_util).get(0)

        best_bid: Bid | None = None
        best_score: Decimal | None = None

        for i in range(num_bids):
            bid = bids.get(i)
            score = self._score_bid(
                bid,
                goal_utility,
                goal_weight,
                self_weight,
                opp_weight,
                opp_model,
                explore_weight,
                random_weight,
            )
            if best_score is None or score > best_score:
                best_bid = bid
                best_score = score

        # Fallback if no bid found (shouldn't happen)
        if best_bid is None:
            fallback_bids = self.get_bids(self._max_util, self._max_util)
            return fallback_bids.get(0)

        return best_bid

    def _score_bid(
        self,
        bid: Bid,
        goal_utility: Decimal,
        goal_weight: Decimal,
        self_weight: Decimal,
        opp_weight: Decimal,
        opp_model: UtilitySpace | None,
        explore_weight: Decimal,
        random_weight: Decimal,
    ) -> Decimal:
        """Score a bid based on multiple weighted factors."""
        score = Decimal(0)
        self_util = self._util_space.getUtility(bid)

        # Goal factor: penalize distance from goal
        if goal_weight != Decimal(0):
            goal_base = abs(self_util - goal_utility)
            score -= goal_base * goal_weight

        # Self factor: prefer higher self utility
        if self_weight != Decimal(0):
            score += self_util * self_weight

        # Opponent factor: prefer higher opponent utility
        if opp_model is not None and opp_weight != Decimal(0):
            opp_util = opp_model.getUtility(bid)
            score += opp_util * opp_weight

        # Exploration factor: penalize frequently seen bids
        if explore_weight != Decimal(0):
            explore_base = self.get_bid_count(bid)
            score -= explore_base * explore_weight

        # Random factor
        if random_weight != Decimal(0):
            random_base = Decimal(str(self._random.random()))
            score += random_base * random_weight

        return score


class ExpandedStrategy:
    """
    Boulware-style concession strategy with adaptive parameters.

    Uses a boulware curve: target_util = min + (max - min) * (1 - f(t))
    where f(t) = k + (1-k) * t^(1/e)

    Parameters:
    - e: boulware constant (smaller = more conceding)
    - k: offset parameter
    - min/max: utility bounds
    - Random noise added via Gaussian with time-varying mean/std
    """

    # Default parameter values
    INITIAL_E = 0.00033
    INITIAL_MIN = 0.5

    def __init__(
        self,
        me: PartyId,
        profile: LinearAdditive,
        parameters: dict[str, Any] | None = None,
    ):
        self._me = me
        self._profile = profile
        self._random = random.Random()

        # Initialize bid chooser
        self._bid_chooser = BidChooser(profile)

        # Initialize parameters (with defaults)
        params = parameters or {}
        self._e = params.get("e", self.INITIAL_E)
        self._k = params.get("k", 0.0)
        self._min = params.get("min", self.INITIAL_MIN)

        # Try to get min from reservation bid if not specified
        if "min" not in params:
            rv_bid = profile.getReservationBid()
            if rv_bid is not None:
                self._min = float(profile.getUtility(rv_bid))
            else:
                self._min = float(self._bid_chooser.min_util)

        self._max = params.get("max", float(self._bid_chooser.max_util))

        # Bid selection weights
        self._goal_weight = Decimal(str(params.get("gw", 1.0)))
        self._self_weight = Decimal(str(params.get("sw", 0.0)))
        self._opp_weight = Decimal(str(params.get("ow", 0.0)))
        self._explore_weight = Decimal(str(params.get("ew", 0.0)))
        self._random_weight = Decimal(str(params.get("rw", 0.0)))

        # Random noise parameters
        self._start_mean = params.get("sm", 0.0)
        self._end_mean = params.get("em", 0.0)
        self._start_sigma = params.get("ss", 0.01)
        self._end_sigma = params.get("es", 0.025)

        # Track best bid from opponent
        self._best_bid_from_opp: Bid | None = None
        self._best_util_from_opp = Decimal(0)

    def init_learned_e(self, learned_e: float | None) -> None:
        """Initialize e parameter from learned value."""
        if learned_e is not None:
            self._e = learned_e

    def init_learned_min(self, learned_min: float | None) -> None:
        """Initialize min parameter from learned value."""
        if learned_min is not None:
            self._min = learned_min

    def count_bid(self, bid: Bid, from_opponent: bool) -> None:
        """Record a bid and track best opponent bid."""
        self._bid_chooser.count_bid(bid)

        if from_opponent:
            util = self._profile.getUtility(bid)
            if util > self._best_util_from_opp:
                self._best_bid_from_opp = bid
                self._best_util_from_opp = util

    def get_action(
        self, progress: Progress, opp_model: UtilitySpace | None = None
    ) -> Action:
        """Generate an action (offer) based on current progress."""
        t = progress.get(int(time.time() * 1000))
        utility_goal = Decimal(str(self._p(t, do_random=True)))

        # If best opponent offer exceeds our target, offer it back
        if utility_goal < self._best_util_from_opp:
            return Offer(self._me, self._best_bid_from_opp)

        # Choose bid based on weights
        picked_bid = self._bid_chooser.choose_bid(
            utility_goal,
            Decimal(str(self._max)),
            utility_goal,
            self._goal_weight,
            self._self_weight,
            self._opp_weight,
            opp_model,
            self._explore_weight,
            self._random_weight,
        )

        return Offer(self._me, picked_bid)

    def is_acceptable(self, bid: Bid, progress: Progress) -> bool:
        """Check if a bid is acceptable at current progress."""
        t = progress.get(int(time.time() * 1000))
        target_util = self._p(t, do_random=False)
        bid_util = float(self._profile.getUtility(bid))
        return bid_util >= target_util - 0.0000001

    def _p(self, t: float, do_random: bool) -> float:
        """Calculate target utility at time t."""
        boulware_curve = self._min + (self._max - self._min) * (1.0 - self._f(t))

        if not do_random:
            return boulware_curve

        # Add Gaussian noise
        random_curve = (
            boulware_curve + self._random.gauss(0, 1) * self._std(t) + self._mean(t)
        )

        # Clamp to [min, max]
        return max(self._min, min(self._max, random_curve))

    def _f(self, t: float) -> float:
        """Boulware function f(t) = k + (1-k) * t^(1/e)."""
        if self._e == 0:
            return 1.0
        return self._k + (1.0 - self._k) * (t ** (1.0 / self._e))

    def _std(self, t: float) -> float:
        """Time-varying standard deviation for noise."""
        delta = self._end_sigma - self._start_sigma
        return self._start_sigma + delta * t

    def _mean(self, t: float) -> float:
        """Time-varying mean for noise."""
        delta = self._end_mean - self._start_mean
        return self._start_mean + delta * t


class NegotiationData:
    """Stores data collected during a single negotiation session."""

    # Constants for learning adjustments
    GOOD_AGREEMENT_UTIL = 0.850
    NO_AGREEMENT_UTIL = 0.001
    UTIL_NEAR_MIN_DISTANCE = 0.05
    EARLY_ROUND_E_INCREASE_COUNT = 5

    INCREASE_E_FACTOR = 10.0
    PI_INCREASE_E_FACTOR = 3.141592653589793
    DECREASE_E_FACTOR = 0.631
    INCREASE_MIN_DELTA = 0.025
    DECREASE_MIN_DELTA = -0.05

    E_MINIMUM = 1e-12
    E_MAXIMUM = 0.1
    MIN_MINIMUM = 0.4
    MIN_MAXIMUM = 0.7

    def __init__(self):
        self.max_received_util = 0.0
        self.agreement_util = 0.0
        self.opponent_name: str | None = None
        self.e_val = ExpandedStrategy.INITIAL_E
        self.min_val = ExpandedStrategy.INITIAL_MIN
        self.time_taken = 0.0
        self.num_encounters = 0

    def add_bid_util(self, bid_util: float) -> None:
        """Track maximum utility received from opponent."""
        if bid_util > self.max_received_util:
            self.max_received_util = bid_util

    def add_agreement_util(self, agreement_util: float) -> None:
        """Record agreement utility."""
        self.agreement_util = agreement_util
        if agreement_util > self.max_received_util:
            self.max_received_util = agreement_util

    def change_e_and_min(self) -> None:
        """Adjust e and min based on negotiation outcome."""
        if self.agreement_util > self.GOOD_AGREEMENT_UTIL:
            # Good agreement, no change needed
            pass
        elif self.agreement_util > self.NO_AGREEMENT_UTIL:
            # Mediocre agreement, decrease e (more conceding)
            self.e_val *= self.DECREASE_E_FACTOR

            # If agreement was near min, increase min
            if (self.agreement_util - self.min_val) < self.UTIL_NEAR_MIN_DISTANCE:
                self.min_val += self.INCREASE_MIN_DELTA
        else:
            # No agreement, increase e (less conceding) and decrease min
            self.e_val *= self.INCREASE_E_FACTOR
            self.min_val += self.DECREASE_MIN_DELTA

        # After several encounters, bump up e
        if self.num_encounters == self.EARLY_ROUND_E_INCREASE_COUNT:
            self.e_val *= self.PI_INCREASE_E_FACTOR

        # Clamp values
        self.min_val = max(self.MIN_MINIMUM, min(self.MIN_MAXIMUM, self.min_val))
        self.e_val = max(self.E_MINIMUM, min(self.E_MAXIMUM, self.e_val))


class PersistentState:
    """Stores persistent state across negotiation sessions (simplified, no file I/O)."""

    def __init__(self):
        self.average_utility = 0.0
        self.negotiations = 0
        self.avg_max_utility_opponent: dict[str, float] = {}
        self.opponent_encounters: dict[str, int] = {}
        self.e_vals: dict[str, float] = {}
        self.mins: dict[str, float] = {}

    def update(self, data: NegotiationData) -> None:
        """Update persistent state with negotiation data."""
        # Update average utility
        self.average_utility = (
            self.average_utility * self.negotiations + data.agreement_util
        ) / (self.negotiations + 1)
        self.negotiations += 1

        opponent = data.opponent_name
        if opponent is not None:
            # Update encounter count
            encounters = self.opponent_encounters.get(opponent, 0)
            self.opponent_encounters[opponent] = encounters + 1

            # Update average max utility from opponent
            avg_util = self.avg_max_utility_opponent.get(opponent, 0.0)
            self.avg_max_utility_opponent[opponent] = (
                avg_util * encounters + data.max_received_util
            ) / (encounters + 1)

            # Store learned parameters
            self.e_vals[opponent] = data.e_val
            self.mins[opponent] = data.min_val

    def get_opponent_e_val(self, opponent: str | None) -> float | None:
        """Get learned e value for opponent."""
        if opponent is None:
            return None
        return self.e_vals.get(opponent)

    def get_opponent_min_val(self, opponent: str | None) -> float | None:
        """Get learned min value for opponent."""
        if opponent is None:
            return None
        return self.mins.get(opponent)

    def get_opponent_encounters(self, opponent: str | None) -> int | None:
        """Get number of encounters with opponent."""
        if opponent is None:
            return None
        return self.opponent_encounters.get(opponent)

    def known_opponent(self, opponent: str | None) -> bool:
        """Check if we have data for this opponent."""
        if opponent is None:
            return False
        return opponent in self.opponent_encounters


class MatrixAlienAgent(DefaultParty):
    """
    Adaptive boulware-style negotiation agent from ANAC 2021.

    Uses a boulware concession curve with parameters that adapt based on
    negotiation outcomes across sessions. Features multi-factor bid scoring
    and opponent tracking.

    University of Tulsa MASTERS submission for ANAC 2021.
    """

    def __init__(self, reporter: "Reporter | None" = None):
        super().__init__(reporter)
        self._me: PartyId | None = None
        self._them: PartyId | None = None
        self._profile_interface: "ProfileInterface | None" = None
        self._progress: Progress | None = None
        self._utility_space: UtilitySpace | None = None
        self._profile: "Profile | None" = None
        self._opponent_name: str | None = None

        # Strategy components
        self._expanded_strategy: ExpandedStrategy | None = None
        self._action_history: list[Action] = []

        # Persistent state (simplified, no file I/O)
        self._persistent_state = PersistentState()
        self._negotiation_data: NegotiationData | None = None

        # Learning settings
        self._do_learn_e = True
        self._do_learn_min = True

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

        # Initialize negotiation data
        self._negotiation_data = NegotiationData()

        # Get profile
        self._profile_interface = ProfileConnectionFactory.create(
            settings.getProfile().getURI(), self.getReporter()
        )
        self._profile = self._profile_interface.getProfile()

        if isinstance(self._profile, UtilitySpace):
            self._utility_space = self._profile

        if isinstance(self._profile, LinearAdditive):
            # Initialize strategy with parameters
            params = {}
            settings_params = settings.getParameters()
            if settings_params is not None:
                # Extract parameters if available
                for key in [
                    "e",
                    "k",
                    "min",
                    "max",
                    "gw",
                    "sw",
                    "ow",
                    "ew",
                    "rw",
                    "sm",
                    "em",
                    "ss",
                    "es",
                ]:
                    if settings_params.containsKey(key):
                        params[key] = settings_params.get(key)

            self._expanded_strategy = ExpandedStrategy(self._me, self._profile, params)

    def _handle_action_done(self, info: ActionDone) -> None:
        """Handle an action performed by any party."""
        action = info.getAction()
        self._action_history.append(action)

        # Count bid in strategy
        if isinstance(action, Offer) and self._expanded_strategy is not None:
            is_opponent = self._me is not None and action.getActor() != self._me
            self._expanded_strategy.count_bid(action.getBid(), is_opponent)

        # Handle opponent's action
        if self._me is not None and action.getActor() != self._me:
            # Extract opponent name on first action
            if self._opponent_name is None:
                full_name = action.getActor().getName()
                index = full_name.rfind("_")
                if index > 0:
                    self._opponent_name = full_name[:index]
                else:
                    self._opponent_name = full_name
                self._them = action.getActor()

                if self._negotiation_data is not None:
                    self._negotiation_data.opponent_name = self._opponent_name

                # Load learned parameters for this opponent
                if self._expanded_strategy is not None:
                    if self._do_learn_e:
                        learned_e = self._persistent_state.get_opponent_e_val(
                            self._opponent_name
                        )
                        self._expanded_strategy.init_learned_e(learned_e)

                    if self._do_learn_min:
                        learned_min = self._persistent_state.get_opponent_min_val(
                            self._opponent_name
                        )
                        self._expanded_strategy.init_learned_min(learned_min)

            # Process opponent's offer
            self._process_action(action)

    def _process_action(self, action: Action) -> None:
        """Process an action from the opponent."""
        if isinstance(action, Offer):
            bid = action.getBid()
            if self._utility_space is not None and self._negotiation_data is not None:
                util = float(self._utility_space.getUtility(bid))
                self._negotiation_data.add_bid_util(util)

    def _handle_your_turn(self) -> None:
        """Handle our turn to make an action."""
        # Advance round counter if round-based
        if isinstance(self._progress, ProgressRounds):
            self._progress = self._progress.advance()

        # Get action from strategy
        action = self._get_action()
        self.getConnection().send(action)

    def _get_action(self) -> Action:
        """Determine and return our action."""
        last_bid = self._get_last_bid()

        # Check if we should accept
        if (
            last_bid is not None
            and self._expanded_strategy is not None
            and self._progress is not None
            and self._expanded_strategy.is_acceptable(last_bid, self._progress)
        ):
            return Accept(self._me, last_bid)

        # Generate offer
        if self._expanded_strategy is not None and self._progress is not None:
            return self._expanded_strategy.get_action(self._progress, None)

        # Fallback: should not happen
        raise ValueError("Strategy or progress not initialized")

    def _get_last_bid(self) -> Bid | None:
        """Get the last bid from action history."""
        for i in range(len(self._action_history) - 1, -1, -1):
            action = self._action_history[i]
            if isinstance(action, Offer):
                return action.getBid()
        return None

    def _handle_finished(self, info: Finished) -> None:
        """Handle negotiation end."""
        agreements = info.getAgreements()

        # Process agreements
        self._process_agreements(agreements)

        self.getReporter().log(logging.INFO, f"Final outcome: {info}")
        self.terminate()

    def _process_agreements(self, agreements: Any) -> None:
        """Process final agreements and update learning data."""
        if self._negotiation_data is None:
            return

        # Get learned parameters from persistent state
        e_val = self._persistent_state.get_opponent_e_val(self._opponent_name)
        self._negotiation_data.e_val = (
            e_val if e_val is not None else ExpandedStrategy.INITIAL_E
        )

        min_val = self._persistent_state.get_opponent_min_val(self._opponent_name)
        self._negotiation_data.min_val = (
            min_val if min_val is not None else ExpandedStrategy.INITIAL_MIN
        )

        encounters = self._persistent_state.get_opponent_encounters(self._opponent_name)
        self._negotiation_data.num_encounters = (
            encounters if encounters is not None else 0
        )

        # Check if we reached an agreement
        if agreements is not None and not agreements.getMap().isEmpty():
            agreement = list(agreements.getMap().values())[0]
            if self._utility_space is not None:
                util = float(self._utility_space.getUtility(agreement))
                self._negotiation_data.add_agreement_util(util)

        # Record time taken
        if self._progress is not None:
            self._negotiation_data.time_taken = self._progress.get(
                int(time.time() * 1000)
            )

        # Update e and min based on outcome
        self._negotiation_data.change_e_and_min()

        # Update persistent state
        self._persistent_state.update(self._negotiation_data)

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SAOP", "Learn"},
            {"geniusweb.profile.utilityspace.LinearAdditive"},
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return (
            "MatrixAlienAgent: Adaptive boulware-style agent that learns e and min "
            "parameters from negotiation outcomes. University of Tulsa MASTERS "
            "submission for ANAC 2021. (AI-translated from Java)"
        )

    def terminate(self) -> None:
        """Clean up resources."""
        super().terminate()
        if self._profile_interface is not None:
            self._profile_interface.close()
            self._profile_interface = None
