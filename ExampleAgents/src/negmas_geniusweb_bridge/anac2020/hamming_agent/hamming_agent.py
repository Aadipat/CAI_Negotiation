"""
HammingAgent - A simple negotiation agent without elicitation.

This agent was translated from the original Java implementation from ANAC 2020.
Translation was performed using AI assistance.

Original strategy:
- Uses Hamming distance to best/worst bids for acceptance decisions
- Time-dependent threshold for bid generation
- Accepts in final round regardless of bid quality
"""

from __future__ import annotations

import logging
import random
from typing import cast

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
from geniusweb.issuevalue.Value import Value
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.profileconnection.ProfileInterface import ProfileInterface
from geniusweb.progress.Progress import Progress
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class HammingAgent(DefaultParty):
    """
    A simple agent that uses Hamming distance for bid evaluation.

    This agent does not use elicitation. It accepts based on how similar
    the received bid is to the best bid vs the worst bid, using a
    time-dependent threshold.
    """

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self._last_received_bid: Bid | None = None
        self._issues: set[str] = set()
        self._n_issues: int = 0
        self._max_bid: dict[str, Value] = {}
        self._min_bid: dict[str, Value] = {}
        self._values: dict[str, list[Value]] = {}
        self._me: PartyId | None = None
        self._profile_interface: ProfileInterface | None = None
        self._progress: Progress | None = None
        self._profile: LinearAdditive | None = None

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
                self.getReporter().log(logging.INFO, f"Final outcome: {info}")
                self.terminate()
        except Exception as e:
            self.getReporter().log(logging.WARNING, f"Failed to handle info: {e}")

    def _handle_settings(self, settings: Settings) -> None:
        """Initialize agent with settings."""
        self._profile_interface = ProfileConnectionFactory.create(
            settings.getProfile().getURI(), self.getReporter()
        )
        self._me = settings.getID()
        self._progress = settings.getProgress()

        profile = self._profile_interface.getProfile()
        if isinstance(profile, LinearAdditive):
            self._profile = profile
            self._init_profile()

    def _handle_action_done(self, info: ActionDone) -> None:
        """Handle opponent's action."""
        other_action = info.getAction()
        if isinstance(other_action, Offer) and other_action.getActor() != self._me:
            self._last_received_bid = other_action.getBid()

    def _init_profile(self) -> None:
        """Initialize profile-related data structures."""
        if self._profile is None:
            return

        domain = self._profile.getDomain()
        self._issues = domain.getIssues()
        self._n_issues = len(self._issues)

        # For LinearAdditive, we compute max/min bids based on utility
        all_bids = AllBidsList(domain)

        # Find max and min utility bids
        max_utility = float("-inf")
        min_utility = float("inf")
        max_bid = None
        min_bid = None

        for i in range(min(all_bids.size().intValue(), 10000)):
            bid = all_bids.get(i)
            utility = float(self._profile.getUtility(bid))
            if utility > max_utility:
                max_utility = utility
                max_bid = bid
            if utility < min_utility:
                min_utility = utility
                min_bid = bid

        if max_bid is not None and min_bid is not None:
            for issue in self._issues:
                self._max_bid[issue] = max_bid.getValue(issue)
                self._min_bid[issue] = min_bid.getValue(issue)
                # Store all possible values for each issue
                value_set = domain.getValues(issue)
                self._values[issue] = [v for v in value_set]

    def _my_turn(self) -> None:
        """Execute agent's turn."""
        if self._profile is None:
            action = self._random_bid()
        elif self._is_acceptable():
            action = Accept(self._me, self._last_received_bid)
        else:
            action = self._make_bid()

        if isinstance(self._progress, ProgressRounds):
            self._progress = self._progress.advance()

        self.getConnection().send(action)

    def _is_acceptable(self) -> bool:
        """Check if the last received bid is acceptable."""
        if self._last_received_bid is None:
            return False

        # Accept in final round
        if isinstance(self._progress, ProgressRounds):
            if self._progress.getCurrentRound() + 1 >= self._progress.getTotalRounds():
                return True

        # Count how many issues match max bid vs min bid
        max_count = 0
        min_count = 0

        for issue in self._issues:
            value = self._last_received_bid.getValue(issue)
            if value is not None and issue in self._max_bid:
                if value == self._max_bid.get(issue):
                    max_count += 1
                elif value == self._min_bid.get(issue):
                    min_count += 1
                    if min_count >= self._threshold():
                        max_count -= 1
                        min_count = 0

        return max_count > self._n_issues - self._threshold()

    def _threshold(self) -> int:
        """Calculate time-dependent threshold."""
        if self._progress is None:
            return 1

        time = self._progress.get(int(1000 * __import__("time").time()))

        if time <= 0.3:
            n = 1
        elif time <= 0.5:
            n = min(2, int((self._n_issues / 3) + 0.999))
        elif time <= 0.7:
            n = min(3, int((self._n_issues / 3) + 0.999))
        elif time <= 0.9:
            n = min(4, int((self._n_issues / 3) + 0.999))
        else:
            n = min(4, int((self._n_issues / 2) + 0.999))

        return n

    def _make_bid(self) -> Offer:
        """Generate a new bid offer."""
        threshold = self._threshold()

        # Select random issues to modify
        issue_list = list(self._issues)
        indices_to_modify = set()
        for _ in range(threshold):
            indices_to_modify.add(random.randint(0, self._n_issues - 1))

        bid_values: dict[str, Value] = {}
        for i, issue in enumerate(issue_list):
            if i in indices_to_modify:
                # Pick a random non-minimum value
                issue_values = self._values.get(issue, [])
                min_value = self._min_bid.get(issue)
                non_min_values = [v for v in issue_values if v != min_value]
                if non_min_values:
                    bid_values[issue] = random.choice(non_min_values)
                elif issue_values:
                    bid_values[issue] = random.choice(issue_values)
                else:
                    bid_values[issue] = self._max_bid.get(issue)
            else:
                bid_values[issue] = self._max_bid.get(issue)

        return Offer(self._me, Bid(bid_values))

    def _random_bid(self) -> Offer:
        """Generate a random bid."""
        if self._profile is None:
            raise ValueError("Profile not initialized")

        domain = self._profile.getDomain()
        all_bids = AllBidsList(domain)
        random_index = random.randint(0, all_bids.size().intValue() - 1)
        bid = all_bids.get(random_index)
        return Offer(self._me, bid)

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SAOP", "SHAOP"},
            {"geniusweb.profile.utilityspace.LinearAdditive"},
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return "HammingAgent: Uses Hamming distance for bid evaluation (AI-translated from Java)"
