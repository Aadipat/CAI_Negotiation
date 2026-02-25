"""
TripleAgent - A learning-based negotiation agent with weighted bidding policy.

This agent was translated from the original Java implementation from ANAC 2021.
Translation was performed using AI assistance.

Original strategy:
- Two-policy weighted bidding: time-dependent + opponent-based
- Frequency-based opponent modeling
- Dynamic threshold adjustment based on domain history
- Accepts in final round or when estimated end is near

Authors: Paolo Janssen & Hugo Brouwer

Translation Notes:
-----------------
Complexity: Simple (straightforward 1:1 translation)

Simplifications made:
- Learning/persistent state removed. Original tracked domain-specific parameters
  across sessions to adapt bidding weights and thresholds.
- `_process_agreements()` is a no-op (original updated persistent learned data)

Known differences from original:
- No cross-session learning - parameters reset each negotiation
- Default parameter values used (w1=0.85, w2=0.15, e=0.05, etc.) instead of
  learned/adapted values
- Original had more sophisticated time estimation for deadline detection

Library replacements:
- None required - uses standard Python libraries only
- Uses GeniusWeb's BidsWithUtility for efficient bid space operations

Type handling:
- Uses `.intValue()` directly on size objects (works with GeniusWeb's BigInteger)
- Decimal used for utility intervals (matching GeniusWeb's API)
"""

from __future__ import annotations

import logging
import random
import time
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
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.Progress import Progress
from geniusweb.progress.ProgressRounds import ProgressRounds

if TYPE_CHECKING:
    from geniusweb.profileconnection.ProfileInterface import ProfileInterface
    from tudelft_utilities_logging.Reporter import Reporter


class TripleAgent(DefaultParty):
    """
    A learning-based negotiation agent with weighted bidding policy.

    Uses two policies weighted together:
    - Policy 1: Time-dependent concession
    - Policy 2: Opponent-based adjustment using best bids received
    """

    def __init__(self, reporter: "Reporter | None" = None):
        super().__init__(reporter)
        self._last_received_bid: Bid | None = None
        self._me: PartyId | None = None
        self._profile_interface: "ProfileInterface | None" = None
        self._progress: Progress | None = None
        self._profile: LinearAdditive | None = None
        self._bid_list: BidsWithUtility | None = None
        self._opponent_name: str | None = None
        self._round: int = 0

        # Parameters (defaults from Java)
        self._p_min: float = 0.5  # Minimum utility to concede to
        self._p_max: float = 0.99  # Maximum utility for bids
        self._e: float = 0.05  # Concession factor
        self._k: float = 0.0  # Concession offset
        self._w1: float = 0.85  # Weight of policy 1
        self._w2: float = 0.15  # Weight of policy 2
        self._opp_penalty: float = 0.35  # Opponent penalty
        self._considered_bids: int = 3  # Top bids to consider

        # Track best opponent bids
        self._bid_arr: list[float] = [0.0, 0.0, 0.0, 0.0]
        self._turn_timers: list[float] = []
        self._longest_round_timer: float = 0.0
        self._last_bid_accepted: bool = False

    def notifyChange(self, info: Inform) -> None:
        """Handle incoming information from the negotiation protocol."""
        try:
            if isinstance(info, Settings):
                self._handle_settings(info)
            elif isinstance(info, ActionDone):
                self._handle_action_done(info)
            elif isinstance(info, YourTurn):
                self._round += 1
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
            self._bid_list = BidsWithUtility(self._profile)

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

            # Process opponent's offer
            if isinstance(action, Offer):
                self._last_received_bid = action.getBid()

    def _process_agreements(self, info: Finished) -> None:
        """Process final agreements."""
        pass  # Learning handled in Java version

    def _utility_goal(self) -> float:
        """Policy 1: Time-dependent target utility."""
        if self._progress is None:
            return self._p_max

        t = self._progress.get(int(time.time() * 1000))
        return self._p_min + (self._p_max - self._p_min) * (1 - self._f(t))

    def _f(self, t: float) -> float:
        """Support function for time-dependent policy."""
        if self._e == 0:
            return self._k
        return self._k + (1 - self._k) * (t ** (1.0 / self._e))

    def _best_bid_op(self) -> float:
        """Policy 2: Opponent-based utility adjustment."""
        if self._last_received_bid is None or self._profile is None:
            return 1.0

        try:
            bid_util = float(self._profile.getUtility(self._last_received_bid))
        except Exception:
            return 1.0

        # Update best bids array
        self._bid_arr.sort()
        if self._bid_arr[0] < bid_util:
            self._bid_arr[0] = bid_util

        average = sum(self._bid_arr) / len(self._bid_arr)
        result = 1 - average + self._opp_penalty

        return min(1.0, result)

    def _bid_threshold(self) -> float:
        """Calculate minimum threshold for bid utility."""
        return self._utility_goal() * self._w1 + self._best_bid_op() * self._w2

    def _is_good(self, bid: Bid | None) -> bool:
        """Check if a bid should be accepted."""
        if bid is None or self._profile is None:
            return False

        # Accept in final round
        if isinstance(self._progress, ProgressRounds):
            rounds = self._progress
            if rounds.getCurrentRound() + 1 >= rounds.getTotalRounds():
                self._last_bid_accepted = True
                return True

        # Time-based acceptance near deadline
        else:
            t = self._progress.get(int(time.time() * 1000)) if self._progress else 0
            self._turn_timers.append(t)

            if len(self._turn_timers) > 2:
                if (
                    self._turn_timers[1] - self._turn_timers[0]
                    > self._longest_round_timer
                ):
                    self._longest_round_timer = (
                        self._turn_timers[1] - self._turn_timers[0]
                    )
                self._turn_timers.pop(0)

                # Accept if near end
                if (
                    t / self._round > (1.0 - t) * 2
                    or self._longest_round_timer * 1.05 > 1.0 - t
                ):
                    self._last_bid_accepted = True
                    return True

        # Accept if utility above threshold
        return float(self._profile.getUtility(bid)) >= self._bid_threshold()

    def _create_bid(self) -> Offer:
        """Generate a bid offer."""
        if self._profile is None or self._bid_list is None:
            raise ValueError("Profile not initialized")

        threshold = self._bid_threshold()

        # Get bids above threshold
        interval = Interval(Decimal(threshold), Decimal(1.0))
        bids_above = self._bid_list.getBids(interval)

        if bids_above.size().intValue() == 0:
            # Use best available bid
            bid = self._bid_list.getExtremeBid(True)
        else:
            # Select from top bids based on random choice
            n_bids = min(self._considered_bids, bids_above.size().intValue())
            idx = random.randint(0, n_bids - 1)
            bid = bids_above.get(idx)

        return Offer(self._me, bid)

    def _my_turn(self) -> None:
        """Execute agent's turn."""
        if isinstance(self._progress, ProgressRounds):
            self._progress = self._progress.advance()

        if self._is_good(self._last_received_bid):
            action: Action = Accept(self._me, self._last_received_bid)
        else:
            action = self._create_bid()

        self.getConnection().send(action)

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SAOP"},
            {"geniusweb.profile.utilityspace.LinearAdditive"},
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return (
            "TripleAgent: Weighted two-policy bidding with opponent modeling "
            "(AI-translated from Java, ANAC 2021)"
        )
