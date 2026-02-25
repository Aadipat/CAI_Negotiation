"""
ShineAgent - A Hamming distance-based negotiation agent.

This agent was translated from the original Java implementation from ANAC 2020.
Translation was performed using AI assistance.

Original strategy:
- Uses Hamming distance for bid similarity calculations
- Maintains opponent estimated profile
- Time-dependent acceptance threshold (decays from 0.85 to 0.55)
- Generates offers weighted by both self quality and opponent profile similarity
"""

from __future__ import annotations

import logging
import random
from decimal import Decimal
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
from geniusweb.issuevalue.NumberValue import NumberValue
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

from ..utils import SimpleLinearOrdering


class ShineAgent(DefaultParty):
    """
    Shine Agent - uses Hamming distance for bid evaluation.

    This agent maintains both self and opponent preference estimates,
    using Hamming distance to find bids that are good for both parties.
    """

    ACCEPT_QUALITY_THRESHOLD = 0.85
    ACCEPT_QUALITY_THRESHOLD_MIN = 0.55
    ACCEPT_DISTANCE_THRESHOLD = 0.15
    NEW_OFFER_DISTANCE_THRESHOLD = 0.15

    def __init__(self, reporter: Reporter = None):
        super().__init__(reporter)
        self._last_received_bid: Bid | None = None
        self._me: PartyId | None = None
        self._profile_interface: ProfileInterface | None = None
        self._progress: Progress | None = None
        self._my_estimated_profile: SimpleLinearOrdering | None = None
        self._opponent_estimated_profile: SimpleLinearOrdering | None = None
        self._reservation_bid: Bid | None = None
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
            self._reservation_bid = profile.getReservationBid()

    def _handle_action_done(self, info: ActionDone) -> None:
        """Handle opponent's action."""
        other_action = info.getAction()
        if isinstance(other_action, Offer):
            self._last_received_bid = other_action.getBid()

    def _init_my_profile(self) -> None:
        """Initialize my estimated profile from utility space."""
        if self._profile is None:
            return

        domain = self._profile.getDomain()
        all_bids = AllBidsList(domain)

        # Sort bids by utility
        bids_with_utility = []
        for i in range(min(all_bids.size().intValue(), 5000)):
            bid = all_bids.get(i)
            utility = float(self._profile.getUtility(bid))
            bids_with_utility.append((bid, utility))

        bids_with_utility.sort(key=lambda x: x[1])
        sorted_bids = [b for b, _ in bids_with_utility]

        self._my_estimated_profile = SimpleLinearOrdering(domain, sorted_bids)

    def _process_opponent_bid(self, bid: Bid) -> None:
        """Process opponent's bid and update opponent model."""
        if self._profile is None:
            return

        domain = self._profile.getDomain()

        if self._opponent_estimated_profile is None:
            self._opponent_estimated_profile = SimpleLinearOrdering(domain, [bid])
        else:
            # Assume new bid is better than all previous (opponent learning)
            self._opponent_estimated_profile = (
                self._opponent_estimated_profile.with_bid(
                    bid, self._opponent_estimated_profile.get_bids()
                )
            )

    def _my_turn(self) -> None:
        """Execute agent's turn."""
        if self._my_estimated_profile is None:
            self._init_my_profile()

        action: Action | None = None

        if self._last_received_bid is not None:
            self._process_opponent_bid(self._last_received_bid)
            last_bid_quality = self._get_bid_quality(
                self._last_received_bid, self._my_estimated_profile
            )

            if (
                self._my_estimated_profile is not None
                and self._my_estimated_profile.contains(self._last_received_bid)
            ):
                reservation_quality = self._get_bid_quality(
                    self._reservation_bid, self._my_estimated_profile
                )
                threshold = self._get_current_threshold(
                    self.ACCEPT_QUALITY_THRESHOLD, self.ACCEPT_QUALITY_THRESHOLD_MIN
                )
                if (
                    last_bid_quality >= reservation_quality
                    and last_bid_quality >= threshold
                ):
                    action = Accept(self._me, self._last_received_bid)
            else:
                # We did not yet assess the received bid
                closest_bid = self._get_closest_bid(
                    self._my_estimated_profile, self._last_received_bid
                )
                if closest_bid is not None:
                    distance = self._hamming_distance(
                        closest_bid, self._last_received_bid
                    )
                    if distance < self.ACCEPT_DISTANCE_THRESHOLD:
                        quality = self._get_bid_quality(
                            closest_bid, self._my_estimated_profile
                        )
                        threshold = self._get_current_threshold(
                            self.ACCEPT_QUALITY_THRESHOLD,
                            self.ACCEPT_QUALITY_THRESHOLD_MIN,
                        )
                        if quality >= threshold:
                            action = Accept(self._me, self._last_received_bid)

        if action is None:
            action = self._new_offer()

        if isinstance(self._progress, ProgressRounds):
            self._progress = self._progress.advance()

        self.getConnection().send(action)

    def _get_closest_bid(
        self, profile: SimpleLinearOrdering | None, input_bid: Bid
    ) -> Bid | None:
        """Find the closest bid in the profile to the input bid."""
        if profile is None:
            return None

        closest_bid = None
        closest_dist = 1.1

        for bid in profile.get_bids():
            dist = self._hamming_distance(bid, input_bid)
            if dist < closest_dist:
                closest_bid = bid
                closest_dist = dist

        return closest_bid

    def _hamming_distance(self, bid1: Bid, bid2: Bid) -> float:
        """
        Calculate Hamming distance between two bids.

        Returns a value between 0 (identical) and 1 (totally different).
        """
        if bid1 is None or bid2 is None:
            return 1.0

        similarity_index = 0.0
        issues = bid1.getIssues()

        for issue in issues:
            value1 = bid1.getValue(issue)
            value2 = bid2.getValue(issue)

            if value1 is None or value2 is None:
                similarity_index += 1
            elif isinstance(value1, NumberValue) and isinstance(value2, NumberValue):
                # For numeric values, calculate relative difference
                v1 = float(value1.getValue())
                v2 = float(value2.getValue())
                # Simplified: assume normalized values
                similarity_index += abs(v1 - v2)
            else:
                if value1 != value2:
                    similarity_index += 1

        n_issues = len(issues)
        return similarity_index / n_issues if n_issues > 0 else 0.0

    def _new_offer(self) -> Offer:
        """Generate a new offer."""
        if self._my_estimated_profile is None or self._profile is None:
            return self._random_bid()

        weighted_bids: list[tuple[float, Bid]] = []
        reservation_quality = self._get_bid_quality(
            self._reservation_bid, self._my_estimated_profile
        )
        threshold = self._get_current_threshold(
            self.ACCEPT_QUALITY_THRESHOLD, self.ACCEPT_QUALITY_THRESHOLD_MIN
        )

        for bid in self._my_estimated_profile.get_bids():
            my_bid_quality = self._get_bid_quality(bid, self._my_estimated_profile)

            # Drop bad offers
            if my_bid_quality < reservation_quality or my_bid_quality < threshold:
                continue

            my_bid_score = 0.0

            if self._opponent_estimated_profile is not None:
                for opp_bid in self._opponent_estimated_profile.get_bids():
                    distance = self._hamming_distance(bid, opp_bid)
                    opp_quality = self._get_bid_quality(
                        opp_bid, self._opponent_estimated_profile
                    )

                    if distance > self.NEW_OFFER_DISTANCE_THRESHOLD:
                        continue

                    my_bid_score += (1 - distance) * opp_quality

            if my_bid_score <= 0.0:
                my_bid_score = 0.1

            my_bid_score *= my_bid_quality
            weighted_bids.append((my_bid_score, bid))

        if not weighted_bids:
            bids = self._my_estimated_profile.get_bids()
            if bids:
                return Offer(self._me, bids[-1])  # Best bid
            return self._random_bid()

        # Select weighted random bid
        total_weight = sum(w for w, _ in weighted_bids)
        if total_weight <= 0:
            return Offer(self._me, weighted_bids[0][1])

        r = random.random() * total_weight
        cumulative = 0.0
        selected_bid = weighted_bids[0][1]

        for weight, bid in weighted_bids:
            cumulative += weight
            if cumulative >= r:
                selected_bid = bid
                break

        # Find similar bids for exploration
        domain = self._profile.getDomain()
        all_bids = AllBidsList(domain)
        similar_bids = []

        for i in range(min(all_bids.size().intValue(), 1000)):
            bid = all_bids.get(i)
            if self._hamming_distance(bid, selected_bid) < 0.1:
                similar_bids.append(bid)

        if similar_bids:
            return Offer(self._me, random.choice(similar_bids))

        return Offer(self._me, selected_bid)

    def _random_bid(self) -> Offer:
        """Generate a random bid."""
        if self._profile is None:
            raise ValueError("Profile not initialized")

        domain = self._profile.getDomain()
        all_bids = AllBidsList(domain)
        idx = random.randint(0, all_bids.size().intValue() - 1)
        return Offer(self._me, all_bids.get(idx))

    def _get_bid_quality(
        self, bid: Bid | None, profile: SimpleLinearOrdering | None
    ) -> float:
        """Get the quality of a bid (0 to 1)."""
        if bid is None or profile is None:
            return 0.0
        return float(profile.get_utility(bid))

    def _get_current_threshold(self, threshold: float, min_value: float) -> float:
        """Calculate time-dependent threshold."""
        if not isinstance(self._progress, ProgressRounds):
            return threshold

        current_round = self._progress.getCurrentRound()
        total_rounds = self._progress.getTotalRounds()
        if total_rounds == 0:
            total_rounds = 1

        progress_ratio = current_round / total_rounds
        return (1 - progress_ratio) * (threshold - min_value) + min_value

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SAOP", "SHAOP"},
            {"geniusweb.profile.utilityspace.LinearAdditive"},
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return (
            "ShineAgent: Hamming distance-based negotiation (AI-translated from Java)"
        )
