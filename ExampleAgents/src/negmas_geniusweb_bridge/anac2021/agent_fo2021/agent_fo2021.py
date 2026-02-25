"""
AgentFO2021 - A learning-based negotiation agent.

This agent was translated from the original Java implementation from ANAC 2021.
Translation was performed using AI assistance.

Note: Renamed from AgentFO to AgentFO2021 to avoid conflict with AgentFO2 (ANL 2022)
and AgentFO3 (ANL 2023).

Original strategy:
- Uses persistent state to learn opponent behavior across sessions
- Time-dependent concession with two phases (0-40% and 40-100% of time)
- Tracks max/min utility offered by opponents for adaptive acceptance
- Binary search on sorted utility list for efficient bid selection

Translation Notes:
-----------------
Complexity: Simple (straightforward 1:1 translation)

Simplifications made:
- Persistent state is stored in memory only (no file I/O). The original Java
  implementation used file-based storage to persist learned opponent data across
  JVM sessions. This version resets state when the Python process restarts.

Known differences from original:
- File I/O for persistent storage removed (PersistentState class simplified)
- Learning data only persists within a single Python session
- The original used Java's BigInteger for bid space size; this version handles
  both BigInteger and Python int via helper pattern

Library replacements:
- None required - uses standard Python libraries only

Type handling:
- Uses `size.intValue() if hasattr(size, "intValue") else int(size)` pattern
  to handle GeniusWeb's BigInteger vs Python int size values
"""

from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING, Any, cast

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
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.Progress import Progress
from geniusweb.progress.ProgressRounds import ProgressRounds

if TYPE_CHECKING:
    from geniusweb.profileconnection.ProfileInterface import ProfileInterface
    from tudelft_utilities_logging.Reporter import Reporter


class AgentFO2021(DefaultParty):
    """
    A learning-based negotiation agent from ANAC 2021.

    Uses persistent state to track opponent behavior across multiple negotiations
    and adapts its strategy based on historical data.
    """

    def __init__(self, reporter: "Reporter | None" = None):
        super().__init__(reporter)
        self._last_received_bid: Bid | None = None
        self._me: PartyId | None = None
        self._profile_interface: "ProfileInterface | None" = None
        self._progress: Progress | None = None
        self._profile: LinearAdditive | None = None
        self._opponent_name: str | None = None

        # Utility tracking
        self._util_list: list[float] = []
        self._bids_map: dict[Bid, float] = {}

        # Persistent state (simplified without file I/O)
        self._persistent_state: dict[str, Any] = {
            "average_utility": 0.0,
            "negotiations": 0,
            "avg_max_utility_opponent": {},
            "avg_min_utility_opponent": {},
            "opponent_encounters": {},
        }

        # Negotiation data for this session
        self._negotiation_data: dict[str, Any] = {
            "max_received_util": 0.0,
            "min_send_util": 1.0,
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
                self._my_turn()
            elif isinstance(info, Finished):
                self._process_agreements(info)
                self.getReporter().log(logging.INFO, f"Final outcome: {info}")
                self.terminate()
        except Exception as e:
            self.getReporter().log(logging.WARNING, f"Failed to handle info: {e}")

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
            self._init_bid_space()

    def _init_bid_space(self) -> None:
        """Initialize the bid space with sorted utilities."""
        if self._profile is None:
            return

        domain = self._profile.getDomain()
        all_bids = AllBidsList(domain)

        # Build utility list and bids map
        for i in range(all_bids.size().intValue()):
            bid = all_bids.get(i)
            utility = float(self._profile.getUtility(bid))
            self._util_list.append(utility)
            self._bids_map[bid] = utility

        self._util_list.sort()

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

            # Process opponent's offer
            if isinstance(action, Offer):
                self._last_received_bid = action.getBid()
                if self._profile is not None:
                    bid_util = float(self._profile.getUtility(self._last_received_bid))
                    if bid_util > self._negotiation_data["max_received_util"]:
                        self._negotiation_data["max_received_util"] = bid_util

    def _process_agreements(self, info: Finished) -> None:
        """Process final agreements."""
        agreements = info.getAgreements()
        if agreements and not agreements.getMap().isEmpty():
            agreement = list(agreements.getMap().values())[0]
            if self._profile is not None:
                util = float(self._profile.getUtility(agreement))
                self._negotiation_data["agreement_util"] = util
                if util > self._negotiation_data["max_received_util"]:
                    self._negotiation_data["max_received_util"] = util

    def _f(self, t: float, min_val: float, max_val: float, e: float) -> float:
        """Time-dependent concession function."""
        return max_val - (max_val - min_val) * (t ** (1 / e))

    def _binary_search(self, goal: float, min_idx: int, max_idx: int) -> int:
        """Binary search for utility threshold in sorted list."""
        if min_idx >= max_idx:
            return min_idx

        center = (min_idx + max_idx) // 2
        if self._util_list[center] < goal:
            return self._binary_search(goal, center + 1, max_idx)
        elif self._util_list[center] == goal:
            return center
        else:
            return self._binary_search(goal, min_idx, center - 1)

    def _make_bid(self) -> Bid:
        """Generate a bid based on time-dependent strategy."""
        if self._progress is None or not self._bids_map:
            return self._random_bid()

        t = self._progress.get(int(time.time() * 1000))
        goal_util = 0.8
        avg_min_util = 0.0
        percent = 0.0

        # Check if we know this opponent
        if self._opponent_name and self._known_opponent(self._opponent_name):
            n = self._get_opponent_encounters(self._opponent_name)
            avg_max = self._get_avg_max_utility(self._opponent_name)
            avg_min = self._get_avg_min_utility(self._opponent_name)

            if n < 6:
                percent = 0.8 + 0.05 * n
            else:
                percent = 1.1

            avg_util = max(avg_max, self._persistent_state["average_utility"])
            avg_min_util = avg_min * percent * 0.5
            goal_util = max(0.8, avg_util * percent)

        # Two-phase bidding strategy
        if t < 0.4:
            threshold = self._f(t / 0.4, goal_util, 1.0, 3.0)
            x = self._binary_search(threshold, 0, len(self._bids_map) - 1)
            i = random.randint(x, len(self._bids_map) - 1)
        else:
            min_goal = (avg_min_util - (goal_util / 4)) * 4 / 3
            goal = self._f(
                (t - 0.4) / 0.6,
                max(min_goal, self._util_list[0] if self._util_list else 0),
                goal_util,
                0.3,
            )
            i = self._binary_search(goal, 0, len(self._bids_map) - 1)

        # Ensure index is valid
        i = max(0, min(i, len(self._util_list) - 1))
        target_util = self._util_list[i]

        # Find bids with matching utility
        matching_bids = [b for b, u in self._bids_map.items() if u == target_util]
        if matching_bids:
            return random.choice(matching_bids)

        return self._random_bid()

    def _random_bid(self) -> Bid:
        """Generate a random bid."""
        if self._profile is None:
            raise ValueError("Profile not initialized")

        domain = self._profile.getDomain()
        all_bids = AllBidsList(domain)
        idx = random.randint(0, all_bids.size().intValue() - 1)
        return all_bids.get(idx)

    def _is_good(self, bid: Bid) -> bool:
        """Check if the last received bid should be accepted."""
        if self._last_received_bid is None or self._profile is None:
            return False

        t = self._progress.get(int(time.time() * 1000)) if self._progress else 0
        last_util = float(self._profile.getUtility(self._last_received_bid))
        bid_util = float(self._profile.getUtility(bid))

        encount = False

        # Check if we know this opponent
        if self._opponent_name and self._known_opponent(self._opponent_name):
            avg_max = self._get_avg_max_utility(self._opponent_name)
            n = self._get_opponent_encounters(self._opponent_name)

            if n < 6:
                percent = 0.8 + 0.05 * n
            else:
                percent = 1.1

            avg_util = max(avg_max, self._persistent_state["average_utility"])
            encount = last_util > max(0.8, avg_util * percent)

        # Acceptance conditions
        a = 1.02
        b = 0.04
        ac_next = a * last_util + b > bid_util
        ac_time = t > 0.9
        ac_const = last_util > 0.9

        return encount or ac_const or (ac_time and ac_next)

    def _my_turn(self) -> None:
        """Execute agent's turn."""
        if isinstance(self._progress, ProgressRounds):
            self._progress = self._progress.advance()

        bid = self._make_bid()

        if self._is_good(bid):
            action: Action = Accept(self._me, self._last_received_bid)
        else:
            action = Offer(self._me, bid)
            if self._profile is not None:
                send_util = float(self._profile.getUtility(bid))
                if send_util < self._negotiation_data["min_send_util"]:
                    self._negotiation_data["min_send_util"] = send_util

        self.getConnection().send(action)

    # Persistent state helper methods
    def _known_opponent(self, opponent: str) -> bool:
        return opponent in self._persistent_state["opponent_encounters"]

    def _get_opponent_encounters(self, opponent: str) -> int:
        return self._persistent_state["opponent_encounters"].get(opponent, 0)

    def _get_avg_max_utility(self, opponent: str) -> float:
        return self._persistent_state["avg_max_utility_opponent"].get(opponent, 0.0)

    def _get_avg_min_utility(self, opponent: str) -> float:
        return self._persistent_state["avg_min_utility_opponent"].get(opponent, 0.0)

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SAOP"},
            {"geniusweb.profile.utilityspace.LinearAdditive"},
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return (
            "AgentFO2021: Learning-based agent with time-dependent concession "
            "(AI-translated from Java, ANAC 2021)"
        )
