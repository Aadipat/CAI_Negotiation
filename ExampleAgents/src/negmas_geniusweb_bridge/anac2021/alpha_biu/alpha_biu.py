"""
AlphaBIU - A frequency-based opponent modeling negotiation agent.

This agent was translated from the original Java implementation from ANAC 2021.
Translation was performed using AI assistance.

Original strategy:
- Uses frequency-based opponent modeling to estimate opponent preferences
- Two-phase strategy: learning phase (0-20%) and offering phase (20-100%)
- Time-dependent concession with exponential decay function
- Considers opponent utility when making offers after learning phase
- Supports persistent state to track opponent behavior across sessions

Translation Notes:
-----------------
Complexity: Simple (straightforward 1:1 translation)

Simplifications made:
- Persistent state stored in memory only (no file I/O). Original used JSON file
  storage to track opponent behavior (avg_max_utility, opponent_alpha, etc.)
  across multiple negotiation sessions.
- Smooth threshold calculation simplified (original computed smoothed time
  series of opponent acceptance thresholds)

Known differences from original:
- No file-based persistence - learned opponent data resets each session
- The `_get_smooth_threshold_over_time()` returns None without persistent data,
  causing the agent to use default opponent threshold (0.6 in `_is_op_good`)
- Alpha learning (`_get_opponent_alpha`) returns 0.0 without persistence, so
  DEFAULT_ALPHA (10.7) is always used

Library replacements:
- None required - uses standard Python libraries only

Type handling:
- Uses `_get_size_int()` helper function to handle GeniusWeb's BigInteger
  vs Python int for `.size()` calls on bid lists and value sets
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass, field
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
from geniusweb.issuevalue.NumberValue import NumberValue
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.Progress import Progress
from geniusweb.progress.ProgressRounds import ProgressRounds

if TYPE_CHECKING:
    from geniusweb.issuevalue.Domain import Domain
    from geniusweb.profileconnection.ProfileInterface import ProfileInterface
    from tudelft_utilities_logging.Reporter import Reporter


@dataclass
class Pair:
    """Stores value frequencies and type for an issue."""

    vList: dict[str, int] = field(default_factory=dict)
    type: int = -1  # -1: invalid, 0: discrete, 1: number


def _get_size_int(size: Any) -> int:
    """Convert size to int, handling both BigInteger and int types."""
    return size.intValue() if hasattr(size, "intValue") else int(size)


class AlphaBIU(DefaultParty):
    """
    A frequency-based opponent modeling negotiation agent from ANAC 2021.

    Uses frequency analysis of opponent offers to estimate opponent preferences
    and adapts bidding strategy accordingly.
    """

    # Constants
    T_SPLIT = 40
    T_PHASE = 0.2
    DEFAULT_ALPHA = 10.7
    MAX_SEARCHABLE_BIDSPACE = 50000
    MIN_UTILITY = 0.6

    def __init__(self, reporter: "Reporter | None" = None):
        super().__init__(reporter)
        self._last_received_bid: Bid | None = None
        self._me: PartyId | None = None
        self._profile_interface: "ProfileInterface | None" = None
        self._progress: Progress | None = None
        self._utility_space: UtilitySpace | None = None
        self._domain: "Domain | None" = None
        self._opponent_name: str | None = None
        self._all_bid_list: AllBidsList | None = None

        # Frequency map: issue name -> Pair(value frequencies, type)
        self._freq_map: dict[str, Pair] = {}

        # Average and standard deviation for utility threshold
        self._avg_util = 0.95
        self._std_util = 0.15
        self._util_threshold = 0.95

        # Alpha for threshold decay
        self._alpha = self.DEFAULT_ALPHA

        # Opponent threshold estimation
        self._op_counter = [0] * self.T_SPLIT
        self._op_sum = [0.0] * self.T_SPLIT
        self._op_threshold: list[float] | None = None

        # Best bids
        self._optimal_bid: Bid | None = None
        self._best_offer_bid: Bid | None = None

        # Persistent state (simplified without file I/O)
        self._persistent_state: dict[str, Any] = {
            "avg_utility": 0.0,
            "std_utility": 0.0,
            "negotiations": 0,
            "avg_max_utility_opponent": {},
            "opponent_encounters": {},
            "avg_opponent_utility": {},
            "opponent_alpha": {},
            "opponent_util_by_time": {},
        }

        # Negotiation data for this session
        self._negotiation_data: dict[str, Any] = {
            "max_received_util": 0.0,
            "agreement_util": 0.0,
            "opponent_name": None,
            "opponent_util": 0.0,
            "opponent_util_by_time": [0.0] * self.T_SPLIT,
        }

    def notifyChange(self, info: Inform) -> None:
        """Handle incoming information from the negotiation protocol."""
        try:
            if isinstance(info, Settings):
                self._handle_settings(info)
            elif isinstance(info, ActionDone):
                self._handle_action_done(info)
            elif isinstance(info, YourTurn):
                self._my_turn()
            elif isinstance(info, Finished):
                self._process_agreements(info)
                self.getReporter().log(logging.INFO, f"Final outcome: {info}")
                self.terminate()
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
        if isinstance(profile, UtilitySpace):
            self._utility_space = profile
            self._domain = profile.getDomain()
            self._init_frequency_map()
            self._find_optimal_bid()

    def _init_frequency_map(self) -> None:
        """Initialize the frequency map for opponent modeling."""
        if self._domain is None:
            return

        self._freq_map.clear()
        issues = self._domain.getIssuesValues()

        for issue_name in issues.keys():
            pair = Pair()
            values = self._domain.getValues(issue_name)

            # Determine type from first value
            if _get_size_int(values.size()) > 0:
                first_val = values.get(0)
                if isinstance(first_val, DiscreteValue):
                    pair.type = 0
                elif isinstance(first_val, NumberValue):
                    pair.type = 1

            # Initialize frequency counts for all values
            for i in range(_get_size_int(values.size())):
                v = values.get(i)
                v_str = self._value_to_str(v, pair)
                pair.vList[v_str] = 0

            self._freq_map[issue_name] = pair

    def _find_optimal_bid(self) -> None:
        """Find the optimal bid in the bid space."""
        if self._domain is None or self._utility_space is None:
            return

        self._all_bid_list = AllBidsList(self._domain)
        bid_space_size = _get_size_int(self._all_bid_list.size())

        max_util = 0.0
        if bid_space_size <= self.MAX_SEARCHABLE_BIDSPACE:
            # Exhaustive search
            for i in range(bid_space_size):
                bid = self._all_bid_list.get(i)
                util = float(self._utility_space.getUtility(bid))
                if util > max_util:
                    max_util = util
                    self._optimal_bid = bid
        else:
            # Random sampling
            for _ in range(self.MAX_SEARCHABLE_BIDSPACE):
                i = random.randint(0, bid_space_size - 1)
                bid = self._all_bid_list.get(i)
                util = float(self._utility_space.getUtility(bid))
                if util > max_util:
                    max_util = util
                    self._optimal_bid = bid

    def _handle_action_done(self, info: ActionDone) -> None:
        """Handle opponent's action."""
        action = info.getAction()

        if self._me is not None and action.getActor() != self._me:
            # Extract opponent name
            if self._opponent_name is None:
                full_name = action.getActor().getName()
                index = full_name.rfind("_")
                if index > 0:
                    self._opponent_name = full_name[:index]
                else:
                    self._opponent_name = full_name
                self._negotiation_data["opponent_name"] = self._opponent_name

                # Load opponent-specific data from persistent state
                self._op_threshold = self._get_smooth_threshold_over_time(
                    self._opponent_name
                )
                if self._op_threshold is not None:
                    for i in range(1, self.T_SPLIT):
                        if self._op_threshold[i] <= 0:
                            self._op_threshold[i] = self._op_threshold[i - 1]

                alpha = self._get_opponent_alpha(self._opponent_name)
                self._alpha = alpha if alpha > 0.0 else self.DEFAULT_ALPHA

            # Process opponent's offer
            self._process_action(action)

    def _process_action(self, action: Action) -> None:
        """Process an action performed by the opponent."""
        if isinstance(action, Offer):
            self._last_received_bid = action.getBid()
            self._update_freq_map(self._last_received_bid)

            if self._utility_space is not None:
                util_val = float(
                    self._utility_space.getUtility(self._last_received_bid)
                )
                if util_val > self._negotiation_data["max_received_util"]:
                    self._negotiation_data["max_received_util"] = util_val

    def _process_agreements(self, info: Finished) -> None:
        """Process final agreements."""
        agreements = info.getAgreements()
        if agreements and not agreements.getMap().isEmpty():
            agreement = list(agreements.getMap().values())[0]
            if self._utility_space is not None:
                util = float(self._utility_space.getUtility(agreement))
                self._negotiation_data["agreement_util"] = util
                self._negotiation_data["opponent_util"] = self._calc_op_value(agreement)
        else:
            if self._best_offer_bid is not None and self._utility_space is not None:
                self._negotiation_data["agreement_util"] = float(
                    self._utility_space.getUtility(self._best_offer_bid)
                )

        # Update opponent offers over time
        for i in range(self.T_SPLIT):
            if self._op_counter[i] > 0:
                self._negotiation_data["opponent_util_by_time"][i] = (
                    self._op_sum[i] / self._op_counter[i]
                )

    def _is_near_negotiation_end(self) -> int:
        """Determine negotiation phase: 0 for learning, 1 for offering."""
        if self._progress is None:
            return 0
        t = self._progress.get(int(time.time() * 1000))
        return 0 if t < self.T_PHASE else 1

    def _my_turn(self) -> None:
        """Execute agent's turn."""
        if isinstance(self._progress, ProgressRounds):
            self._progress = self._progress.advance()

        # Track opponent utility over time
        if self._is_near_negotiation_end() > 0 and self._last_received_bid is not None:
            t = self._progress.get(int(time.time() * 1000)) if self._progress else 0
            index = int((self.T_SPLIT - 1) / (1 - self.T_PHASE) * (t - self.T_PHASE))
            index = max(0, min(index, self.T_SPLIT - 1))
            self._op_sum[index] += self._calc_op_value(self._last_received_bid)
            self._op_counter[index] += 1

        # Evaluate offer and decide action
        if self._is_good(self._last_received_bid):
            action: Action = Accept(self._me, self._last_received_bid)
        else:
            # Update best offer bid
            if self._last_received_bid is not None:
                if self._best_offer_bid is None:
                    self._best_offer_bid = self._last_received_bid
                elif self._utility_space is not None:
                    if float(
                        self._utility_space.getUtility(self._last_received_bid)
                    ) > float(self._utility_space.getUtility(self._best_offer_bid)):
                        self._best_offer_bid = self._last_received_bid

            bid = self._make_bid()
            action = Offer(self._me, bid)

        self.getConnection().send(action)

    def _make_bid(self) -> Bid:
        """Generate a bid based on the current phase."""
        if self._all_bid_list is None or self._utility_space is None:
            return self._optimal_bid or self._random_bid()

        bid: Bid | None = None
        phase = self._is_near_negotiation_end()
        t = self._progress.get(int(time.time() * 1000)) if self._progress else 0

        if phase == 0:
            # Phase 1: Random good bids for us
            for _ in range(1000):
                i = random.randint(0, _get_size_int(self._all_bid_list.size()) - 1)
                bid = self._all_bid_list.get(i)
                if self._is_good(bid):
                    break
            if not self._is_good(bid):
                bid = self._optimal_bid
        else:
            # Phase 2: Bids good for both parties
            for _ in range(1000):
                i = random.randint(0, _get_size_int(self._all_bid_list.size()) - 1)
                bid = self._all_bid_list.get(i)
                if bid == self._optimal_bid or (
                    self._is_good(bid) and self._is_op_good(bid)
                ):
                    break

            # Near deadline, consider best offer from opponent
            if (
                t > 0.99
                and self._best_offer_bid is not None
                and self._is_good(self._best_offer_bid)
            ):
                bid = self._best_offer_bid

            if not self._is_good(bid):
                bid = self._optimal_bid

        return bid if bid is not None else self._optimal_bid or self._random_bid()

    def _random_bid(self) -> Bid:
        """Generate a random bid."""
        if self._all_bid_list is None:
            raise ValueError("Bid list not initialized")
        idx = random.randint(0, _get_size_int(self._all_bid_list.size()) - 1)
        return self._all_bid_list.get(idx)

    def _is_good(self, bid: Bid | None) -> bool:
        """Check if a bid is good for us."""
        if bid is None or self._utility_space is None:
            return False

        t = self._progress.get(int(time.time() * 1000)) if self._progress else 0

        max_value = (
            0.95 * float(self._utility_space.getUtility(self._optimal_bid))
            if self._optimal_bid
            else 0.95
        )

        avg_max_utility = (
            self._get_avg_max_utility(self._opponent_name)
            if self._opponent_name and self._known_opponent(self._opponent_name)
            else self._avg_util
        )

        # Calculate threshold with exponential decay
        self._util_threshold = max_value - (
            max_value
            - 0.55 * self._avg_util
            - 0.4 * avg_max_utility
            + 0.5 * self._std_util**2
        ) * (math.exp(self._alpha * t) - 1) / (math.exp(self._alpha) - 1)

        if self._util_threshold < self.MIN_UTILITY:
            self._util_threshold = self.MIN_UTILITY

        return float(self._utility_space.getUtility(bid)) >= self._util_threshold

    def _is_op_good(self, bid: Bid | None) -> bool:
        """Check if a bid is good for the opponent."""
        if bid is None:
            return False

        value = self._calc_op_value(bid)
        t = self._progress.get(int(time.time() * 1000)) if self._progress else 0
        index = int((self.T_SPLIT - 1) / (1 - self.T_PHASE) * (t - self.T_PHASE))
        index = max(0, min(index, self.T_SPLIT - 1))

        if self._op_threshold is not None:
            op_threshold = max(1 - 2 * self._op_threshold[index], 0.2)
        else:
            op_threshold = 0.6

        return value > op_threshold

    def _update_freq_map(self, bid: Bid | None) -> None:
        """Update frequency map with bid values."""
        if bid is None:
            return

        for issue in bid.getIssues():
            if issue in self._freq_map:
                pair = self._freq_map[issue]
                value = bid.getValue(issue)
                v_str = self._value_to_str(value, pair)
                if v_str in pair.vList:
                    pair.vList[v_str] += 1

    def _calc_op_value(self, bid: Bid) -> float:
        """Calculate estimated opponent utility for a bid."""
        issues = list(bid.getIssues())
        if not issues:
            return 0.0

        val_util = []
        iss_weight = []

        for issue in issues:
            if issue not in self._freq_map:
                continue

            pair = self._freq_map[issue]
            value = bid.getValue(issue)
            v_str = self._value_to_str(value, pair)

            # Calculate utility of value
            sum_of_values = sum(pair.vList.values())
            max_value = max(pair.vList.values()) if pair.vList else 1
            max_value = max(max_value, 1)

            # Estimated utility of the issue value
            freq = pair.vList.get(v_str, 0)
            val_util.append(freq / max_value)

            # Calculate inverse std deviation for issue weight
            if pair.vList:
                mean = sum_of_values / len(pair.vList)
                variance = sum((v - mean) ** 2 for v in pair.vList.values())
                iss_weight.append(1.0 / math.sqrt((variance + 0.1) / len(pair.vList)))
            else:
                iss_weight.append(1.0)

        if not val_util:
            return 0.0

        # Weighted average
        total_value = sum(u * w for u, w in zip(val_util, iss_weight))
        sum_weight = sum(iss_weight)

        return total_value / sum_weight if sum_weight > 0 else 0.0

    def _value_to_str(self, value: Any, pair: Pair) -> str:
        """Convert a value to string representation."""
        if pair.type == 0 and isinstance(value, DiscreteValue):
            return value.getValue()
        elif pair.type == 1 and isinstance(value, NumberValue):
            return str(value.getValue())
        return str(value)

    # Persistent state helper methods
    def _known_opponent(self, opponent: str | None) -> bool:
        if opponent is None:
            return False
        return opponent in self._persistent_state["opponent_encounters"]

    def _get_avg_max_utility(self, opponent: str | None) -> float:
        if opponent is None:
            return self._avg_util
        return self._persistent_state["avg_max_utility_opponent"].get(
            opponent, self._avg_util
        )

    def _get_opponent_alpha(self, opponent: str | None) -> float:
        if opponent is None:
            return 0.0
        return self._persistent_state["opponent_alpha"].get(opponent, 0.0)

    def _get_smooth_threshold_over_time(
        self, opponent: str | None
    ) -> list[float] | None:
        if opponent is None or not self._known_opponent(opponent):
            return None
        return self._persistent_state.get("smooth_threshold", {}).get(opponent)

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SAOP"},
            {"geniusweb.profile.utilityspace.LinearAdditive"},
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return (
            "AlphaBIU: Frequency-based opponent modeling agent with two-phase strategy "
            "(AI-translated from Java, ANAC 2021)"
        )

    def terminate(self) -> None:
        """Clean up resources."""
        super().terminate()
        if self._profile_interface is not None:
            self._profile_interface.close()
            self._profile_interface = None
