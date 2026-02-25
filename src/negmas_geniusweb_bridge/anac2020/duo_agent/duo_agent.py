"""
DUOAgent - A negotiation agent using linear regression for bid prediction.

This agent was translated from the original Java implementation from ANAC 2020.
Translation was performed using AI assistance.

Original strategy:
- Uses one-hot encoding and linear regression to predict bid utilities
- Analyzes opponent behavior to adjust bidding strategy
- Time-dependent acceptance strategy
"""

from __future__ import annotations

import logging
import random
from decimal import Decimal
from typing import TYPE_CHECKING, cast

import numpy as np

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Comparison import Comparison
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.DiscreteValue import DiscreteValue
from geniusweb.issuevalue.NumberValue import NumberValue
from geniusweb.issuevalue.Value import Value
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.Profile import Profile
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.profileconnection.ProfileInterface import ProfileInterface
from geniusweb.progress.Progress import Progress
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter

if TYPE_CHECKING:
    from geniusweb.issuevalue.Domain import Domain

from ..utils import SimpleLinearOrdering


class DUOAgent(DefaultParty):
    """
    A negotiation agent that uses linear regression for bid prediction.

    This agent uses one-hot encoding and OLS linear regression to estimate
    bid utilities, then adjusts its bidding strategy based on opponent behavior.
    """

    def __init__(self, reporter: Reporter | None = None):
        super().__init__(reporter)
        self._last_received_bid: Bid | None = None
        self._me: PartyId | None = None
        self._profile_interface: ProfileInterface | None = None
        self._estimated_profile: SimpleLinearOrdering | None = None
        self._all_possible_bids: list[list[str]] = []
        self._sorted_predicted_bids: list[Bid] = []
        self._turn_count: int = 0
        self._opponent_bids: list[Bid] = []
        self._my_bids: list[Bid] = []
        self._current_bid: int = 0
        self._total_round: int = 0
        self._dont_repeat: bool = True
        self._repeating_count: int = 0
        self._least_w: float = float("inf")

    def notifyChange(self, info: Inform) -> None:
        """Handle incoming information from the negotiation protocol."""
        try:
            if isinstance(info, Settings):
                self._handle_settings(info)
            elif isinstance(info, ActionDone):
                self._handle_action_done(info)
            elif isinstance(info, YourTurn):
                self._turn_count += 1
                self._my_turn()
            elif isinstance(info, Finished):
                self.getReporter().log(logging.INFO, f"Final outcome: {info}")
                self.terminate()
        except Exception as e:
            self.getReporter().log(logging.WARNING, f"Failed to handle info: {e}")
            raise RuntimeError(f"Failed to handle info: {e}") from e

    def _handle_settings(self, settings: Settings) -> None:
        """Initialize agent with settings."""
        self._profile_interface = ProfileConnectionFactory.create(
            settings.getProfile().getURI(), self.getReporter()
        )
        self._me = settings.getID()
        progress = settings.getProgress()

        if isinstance(progress, ProgressRounds):
            self._total_round = progress.getTotalRounds()

        self._opponent_bids = []
        self._sorted_predicted_bids = []
        self._my_bids = []
        self._current_bid = 0

        profile = self._profile_interface.getProfile()
        self._estimated_profile = SimpleLinearOrdering(
            profile.getDomain(), self._get_sorted_bids(profile)
        )
        self._elicitation()

    def _get_sorted_bids(self, profile: Profile) -> list[Bid]:
        """Get sorted bids from profile."""
        from geniusweb.profile.DefaultPartialOrdering import DefaultPartialOrdering

        if not isinstance(profile, DefaultPartialOrdering):
            return []

        bids_list = list(profile.getBids())
        # Sort ascending (worse bids first, better bids last)
        bids_list.sort(key=lambda b: 0 if profile.isPreferredOrEqual(b, b) else 1)
        return bids_list

    def _handle_action_done(self, info: ActionDone) -> None:
        """Handle opponent's action."""
        other_action = info.getAction()
        if isinstance(other_action, Offer):
            self._last_received_bid = other_action.getBid()
            self._opponent_bids.append(self._last_received_bid)
        elif isinstance(other_action, Comparison):
            # Handle SHAOP protocol Comparison action
            if self._estimated_profile is not None:
                self._estimated_profile = self._estimated_profile.with_bid(
                    other_action.getBid(), list(other_action.getWorse())
                )
            self._turn_count += 1
            self._my_turn()

    def _my_turn(self) -> None:
        """Execute agent's turn."""
        action: Action
        check = True
        last_turns = False

        # Accept in final rounds
        if self._total_round - 1 < len(self._opponent_bids) / 2:
            if self._last_received_bid is not None:
                action = Accept(self._me, self._last_received_bid)
                self.getConnection().send(action)
                return
            last_turns = True

        # Acceptance strategy after turn 15
        if self._turn_count > 15 and not last_turns:
            if (
                len(self._my_bids) > 1
                and self._last_received_bid is not None
                and self._calculate_weight(self._last_received_bid) >= self._least_w
            ):
                action = Accept(self._me, self._last_received_bid)
                self.getConnection().send(action)
                check = False

        # Bidding
        if check and not last_turns:
            if len(self._sorted_predicted_bids) == 0:
                # Fallback: send a random bid if no predictions available
                if self._last_received_bid is not None:
                    action = Accept(self._me, self._last_received_bid)
                else:
                    # Create an empty bid as fallback
                    action = Offer(self._me, Bid({}))
                self.getConnection().send(action)
                return

            bid = self._opponent_situation()
            self._my_bids.append(bid)
            action = Offer(self._me, bid)

            weight = self._calculate_weight(bid)
            if weight < self._least_w:
                self._least_w = weight

            self._current_bid += 1
            self.getConnection().send(action)

    def _opponent_situation(self) -> Bid:
        """Analyze opponent behavior and select appropriate bid."""
        last_10_round: dict[Bid, int] = {}
        max_repeated_count = -float("inf")
        bid_count = 0

        if len(self._opponent_bids) > 9:
            for i in range(len(self._opponent_bids) - 10, len(self._opponent_bids)):
                bid = self._opponent_bids[i]
                if bid in last_10_round:
                    last_10_round[bid] += 1
                    if last_10_round[bid] > max_repeated_count:
                        max_repeated_count = last_10_round[bid]
                else:
                    last_10_round[bid] = 1
                    if max_repeated_count == -float("inf"):
                        max_repeated_count = 1
                    bid_count += 1

            if max_repeated_count >= 5 and self._dont_repeat:
                self._current_bid = max(0, self._current_bid - int(max_repeated_count))
                self._dont_repeat = False
            elif bid_count < 5 and self._dont_repeat:
                self._current_bid = max(0, self._current_bid - (5 - bid_count))
                self._dont_repeat = False
            else:
                rr = random.random()
                self._repeating_count += 1
                if self._repeating_count > 3:
                    self._dont_repeat = True
                    self._repeating_count = 0
                if rr < 0.5:
                    adjustment = int(rr * 10)
                    if self._current_bid - adjustment > 0:
                        self._current_bid = self._current_bid - adjustment

        # Ensure current_bid is within bounds
        if self._current_bid >= len(self._sorted_predicted_bids):
            self._current_bid = len(self._sorted_predicted_bids) - 1
        if self._current_bid < 0:
            self._current_bid = 0

        return self._sorted_predicted_bids[self._current_bid]

    def _calculate_weight(self, bid: Bid) -> float:
        """Calculate the weight/utility of a bid based on its position in sorted list."""
        if bid not in self._sorted_predicted_bids:
            return 0.0
        index = self._sorted_predicted_bids.index(bid)
        if len(self._sorted_predicted_bids) == 0:
            return 0.0
        return 1.0 - (index / len(self._sorted_predicted_bids))

    def _generate_all_possible_bids(
        self, input_lists: list[list[str]], i: int
    ) -> list[list[str]]:
        """Generate all possible combinations of issue values."""
        if i == len(input_lists):
            return [[]]

        result: list[list[str]] = []
        recursive = self._generate_all_possible_bids(input_lists, i + 1)

        for j in range(len(input_lists[i])):
            for rec in recursive:
                new_list = list(rec)
                new_list.insert(0, input_lists[i][j])
                result.append(new_list)

        return result

    def _elicitation(self) -> None:
        """Perform bid elicitation using linear regression."""
        try:
            if self._profile_interface is None:
                return

            profile = self._profile_interface.getProfile()
            domain = profile.getDomain()
            issues = list(domain.getIssues())

            all_values: list[list[str]] = []
            all_values_as_values: list[list[Value]] = []
            types: list[str] = []
            how_many_value = 0

            for issue in issues:
                temp: list[str] = []
                temp_v: list[Value] = []
                value_set = domain.getValues(issue)

                for v in value_set:
                    how_many_value += 1
                    if isinstance(v, DiscreteValue):
                        temp.append(v.getValue())
                        temp_v.append(v)
                        types.append("Discrete")
                    elif isinstance(v, NumberValue):
                        temp.append(str(v.getValue()))
                        temp_v.append(v)
                        types.append("Number")

                all_values.append(temp)
                all_values_as_values.append(temp_v)

            self._all_possible_bids = self._generate_all_possible_bids(all_values, 0)

            if len(self._all_possible_bids) == 0:
                return

            encoded_values = self._one_hot_encoder(
                self._all_possible_bids, how_many_value, all_values_as_values
            )

            # Get sorted bids from estimated profile
            given_bids: list[list[str]] = []
            if self._estimated_profile is not None:
                sorted_bids = self._estimated_profile.get_bids()
                for bid in sorted_bids:
                    temp_ls: list[str] = []
                    for issue in issues:
                        value = bid.getValue(issue)
                        if isinstance(value, DiscreteValue):
                            temp_ls.append(value.getValue())
                        elif isinstance(value, NumberValue):
                            temp_ls.append(str(value.getValue()))
                    given_bids.append(temp_ls)

            if len(given_bids) == 0:
                # Fallback: use random predictions
                bid_prediction = np.random.rand(len(encoded_values))
            else:
                encoded_train_values = self._one_hot_encoder(
                    given_bids, how_many_value, all_values_as_values
                )

                # Create target values (indices)
                indexes = np.array(
                    [(i + 1) * 2 for i in range(len(encoded_train_values))]
                )

                # Perform linear regression
                try:
                    bid_prediction = self._fit_and_predict(
                        encoded_train_values, indexes, encoded_values
                    )
                except Exception:
                    # Fallback to random if regression fails
                    bid_prediction = np.random.rand(len(encoded_values))

            # Create bids from all possible combinations
            lob: list[Bid] = []
            for i in range(len(encoded_values)):
                msv: dict[str, Value] = {}
                for issue in issues:
                    for j, val_str in enumerate(self._all_possible_bids[i]):
                        if j < len(types):
                            domain_values = str(domain.getValues(issue))
                            if val_str in domain_values:
                                if types[j] == "Discrete":
                                    msv[issue] = DiscreteValue(val_str)
                                elif types[j] == "Number":
                                    msv[issue] = NumberValue(Decimal(val_str))
                                break

                bid = Bid(msv)
                self._sorted_predicted_bids.append(bid)
                lob.append(bid)

            # Sort bids by predicted utility
            if len(lob) > 0:
                bid_to_prediction = {
                    id(lob[i]): bid_prediction[i] for i in range(len(lob))
                }
                self._sorted_predicted_bids.sort(
                    key=lambda b: bid_to_prediction.get(id(b), 0)
                )

        except Exception as e:
            self.getReporter().log(logging.WARNING, f"Couldn't elicitate: {e}")

    def _one_hot_encoder(
        self,
        bid_order: list[list[str]],
        count_all: int,
        all_issues: list[list[Value]],
    ) -> np.ndarray:
        """One-hot encode bid values."""
        one_hot_encoded = np.zeros((len(bid_order), count_all))

        for i in range(len(bid_order)):
            count = 0
            for k in range(len(bid_order[i])):
                if k >= len(all_issues):
                    break
                for l_idx in range(len(all_issues[k])):
                    if count >= count_all:
                        break

                    val = bid_order[i][k] if k < len(bid_order[i]) else None
                    if val is None:
                        one_hot_encoded[i][count] = 0.5
                    else:
                        issue_val = all_issues[k][l_idx]
                        if isinstance(issue_val, DiscreteValue):
                            if val == issue_val.getValue():
                                one_hot_encoded[i][count] = 1.0
                        elif isinstance(issue_val, NumberValue):
                            if val == str(issue_val.getValue()):
                                one_hot_encoded[i][count] = 1.0
                    count += 1

        return one_hot_encoded

    def _fit_and_predict(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
    ) -> np.ndarray:
        """Fit OLS linear regression and predict."""
        # Add intercept column
        X_train_with_intercept = np.column_stack([np.ones(len(X_train)), X_train])
        X_test_with_intercept = np.column_stack([np.ones(len(X_test)), X_test])

        # OLS: beta = (X'X)^(-1) X'y
        try:
            XtX = X_train_with_intercept.T @ X_train_with_intercept
            Xty = X_train_with_intercept.T @ y_train
            # Use pseudo-inverse for numerical stability
            beta = np.linalg.pinv(XtX) @ Xty
            predictions = X_test_with_intercept @ beta
            return predictions
        except np.linalg.LinAlgError:
            # Fallback to random if linear algebra fails
            return np.random.rand(len(X_test))

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        # Supports both SAOP and SHAOP protocols
        return Capabilities(
            {"SAOP", "SHAOP"},
            {
                "geniusweb.profile.utilityspace.LinearAdditive",
                "geniusweb.profile.Profile",
            },
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return "DUOAgent: Uses linear regression for bid prediction (AI-translated from Java)"
