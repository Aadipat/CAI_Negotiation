"""
BlingBling Agent - A SHAOP/SAOP negotiation agent using RankNet for preference learning.

This agent was translated from the original Java implementation from ANAC 2020.
Translation was performed using AI assistance.

Original author: TU Delft
Description: A stage-based negotiation agent that uses neural network-based ranking
(RankNet) to learn utilities from pairwise comparisons. The agent can be optimized
via AutoML for hyperparameter tuning.

Strategy overview:
- Uses a multi-layer perceptron (RankNet) to learn utilities from partial orderings
- Stage-based negotiation: exploration stage -> agreement search stage
- Opponent modeling using frequency-based estimation (SFM - Statistical Frequency Model)
- Elicitation support for SHAOP protocol with cost-aware decisions
- Time-dependent threshold for bid generation and acceptance
- Pareto frontier estimation using both agent's and opponent's utility estimates

Key components:
- RankNet: Neural network that learns pairwise preferences to estimate utilities
- MyProfile: Manages own preference model using RankNet for utility estimation
- OpponentProfile: Frequency-based opponent model for predicting opponent utilities
- IssueTracker/ValueTracker: Track issue and value importance for opponent modeling
- Distribution: Statistics tracking (mean, variance) for opponent analysis
"""

from __future__ import annotations

import logging
import math
import random
from typing import TYPE_CHECKING

import numpy as np

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Comparison import Comparison
from geniusweb.actions.ElicitComparison import ElicitComparison
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
    from geniusweb.profile.Profile import Profile


# =============================================================================
# Helper Classes
# =============================================================================


class Distribution:
    """
    Track distribution statistics for samples.

    Records mean, variance, min, and max values incrementally.
    Not actively used but kept for potential analysis.
    """

    def __init__(self) -> None:
        """Initialize empty distribution."""
        self._mu: float = 0.0
        self._var: float = 0.0
        self._n: int = 0
        self._min: float | None = None
        self._max: float | None = None

    def add_sample(self, sample: float) -> None:
        """
        Add a sample to the distribution.

        Uses Welford's online algorithm for variance calculation.

        Args:
            sample: The sample value to add.
        """
        n = self._n
        mu_new = (n * self._mu + sample) / (n + 1.0)
        self._var = (
            n * self._var + n * (self._mu - mu_new) ** 2 + (sample - mu_new) ** 2
        ) / (n + 1.0)
        self._mu = mu_new
        self._n += 1

        if self._min is None or sample < self._min:
            self._min = sample
        if self._max is None or sample > self._max:
            self._max = sample

    def get_std_dev(self) -> float:
        """Get the standard deviation."""
        return math.sqrt(self._var)

    def get_mean(self) -> float:
        """Get the mean."""
        return self._mu


class ValueTracker:
    """
    Track value frequency and evaluation for opponent modeling.

    Uses the SFM (Statistical Frequency Model) approach to estimate
    value importance based on how often the opponent offers each value.
    """

    def __init__(self) -> None:
        """Initialize value tracker."""
        self._value_count: int = 0
        self._evaluation: float = 0.0

    def increment_get(self) -> int:
        """Increment count and return new value."""
        self._value_count += 1
        return self._value_count

    def update_evaluation(self, max_value_count: int, weight: float) -> None:
        """
        Update the evaluation based on frequency and issue weight.

        Uses a non-linear transformation based on weight to estimate
        the value's importance to the opponent.

        Args:
            max_value_count: Maximum count among all values for this issue.
            weight: Current estimated weight of the issue.
        """
        if weight < 1.0:
            mod_value_count = (self._value_count + 1.0) ** (1.0 - weight) - 1.0
            mod_max_value_count = (max_value_count + 1.0) ** (1.0 - weight) - 1.0
            if mod_max_value_count > 0:
                self._evaluation = mod_value_count / mod_max_value_count
            else:
                self._evaluation = 0.0
        else:
            self._evaluation = 1.0

    def get_evaluation(self) -> float:
        """Get the current evaluation."""
        return self._evaluation

    def get_count(self) -> int:
        """Get the count."""
        return self._value_count


class IssueTracker:
    """
    Track issue importance for opponent modeling.

    Monitors how often different values are offered by the opponent
    to estimate issue weights using the SFM approach.
    """

    def __init__(self, issue: str, valueset: list[Value]) -> None:
        """
        Initialize issue tracker.

        Args:
            issue: The issue name.
            valueset: List of possible values for this issue.
        """
        self._issue = issue
        self._num_values = len(valueset)
        self._seen_values = 0
        self._value_trackers: dict[Value, ValueTracker] = {}
        self._max_value: Value | None = None
        self._max_value_count = 0
        self._weight = 0.0

    def register_value(self, value: Value, bids_received: int) -> None:
        """
        Register a value offered by the opponent.

        Args:
            value: The value offered.
            bids_received: Total number of bids received so far.
        """
        # Create value tracker if needed
        if value not in self._value_trackers:
            self._value_trackers[value] = ValueTracker()
            self._seen_values += 1

        # Register max offered value with count
        value_count = self._value_trackers[value].increment_get()
        if value_count > self._max_value_count:
            self._max_value_count = value_count
            self._max_value = value

        # Update issue weight
        if self._num_values > 1:
            equal_shares = bids_received / self._num_values
            if bids_received != equal_shares:
                self._weight = (self._max_value_count - equal_shares) / (
                    bids_received - equal_shares
                )
            else:
                self._weight = 0.0

        # Update all value evaluations
        for value_tracker in self._value_trackers.values():
            value_tracker.update_evaluation(self._max_value_count, self._weight)

    def get_evaluation_old(self, value: Value) -> float:
        """Get evaluation using original SFM method."""
        if value not in self._value_trackers or self._max_value_count == 0:
            return 0.0
        return self._value_trackers[value].get_count() / self._max_value_count

    def get_evaluation(self, value: Value) -> float:
        """Get evaluation using improved SFM method."""
        if value not in self._value_trackers:
            return 0.0
        return self._value_trackers[value].get_evaluation()

    def get_weight(self) -> float:
        """Get the issue weight."""
        return self._weight

    def get_old_weight(self, bids_received: int) -> float:
        """Get weight using original SFM method."""
        if bids_received == 0:
            return 0.0
        return self._max_value_count / bids_received

    def get_max_value(self) -> Value | None:
        """Get the most frequently offered value."""
        return self._max_value


class OpponentProfile:
    """
    Opponent model using frequency-based estimation.

    Uses the SFM (Statistical Frequency Model) approach to estimate
    opponent preferences by tracking bid patterns.
    """

    def __init__(self, domain: Domain) -> None:
        """
        Initialize opponent profile.

        Args:
            domain: The negotiation domain.
        """
        self._domain = domain
        self._issue_weights: dict[str, float] = {}
        self._issue_trackers: dict[str, IssueTracker] = {}
        self._offers: list[Bid] = []
        self._best_offer: Bid | None = None
        self._best_offer_util = 0.0
        self._old_weights = False
        self._old_evaluation = False

        # Initialize issue trackers
        for issue in domain.getIssues():
            values = list(domain.getValues(issue))
            self._issue_trackers[issue] = IssueTracker(issue, values)

    def register_offer(self, bid: Bid) -> None:
        """
        Register a bid offered by the opponent.

        Updates issue weights and value evaluations based on the offer.

        Args:
            bid: The bid to register.
        """
        self._offers.append(bid)

        total_weight = 0.0
        for issue, tracker in self._issue_trackers.items():
            value = bid.getValue(issue)
            if value is not None:
                tracker.register_value(value, len(self._offers))
            weight = tracker.get_weight()
            total_weight += weight
            self._issue_weights[issue] = weight

        # Normalize weights
        for issue in self._issue_weights:
            if total_weight == 0.0:
                self._issue_weights[issue] = 1.0 / len(self._issue_weights)
            else:
                self._issue_weights[issue] = self._issue_weights[issue] / total_weight

    def get_pred_opp_utility(self, bid: Bid | None) -> float:
        """
        Predict opponent's utility for a bid.

        Args:
            bid: The bid to evaluate.

        Returns:
            Predicted opponent utility between 0 and 1.
        """
        if not self._offers or bid is None:
            return 0.0

        used_issue_weights = (
            self._get_old_issue_weights() if self._old_weights else self._issue_weights
        )

        predict = 0.0
        for issue, tracker in self._issue_trackers.items():
            value = bid.getValue(issue)
            if value is None:
                continue

            value_evaluation = (
                tracker.get_evaluation_old(value)
                if self._old_evaluation
                else tracker.get_evaluation(value)
            )
            predict += used_issue_weights.get(issue, 0.0) * value_evaluation

        return predict

    def set_method(self, old_weights: bool, old_evaluation: bool) -> None:
        """Set whether to use old or new SFM method."""
        self._old_weights = old_weights
        self._old_evaluation = old_evaluation

    def _get_old_issue_weights(self) -> dict[str, float]:
        """Get weights using original SFM method."""
        old_issue_weights: dict[str, float] = {}
        total_weight = 0.0

        for issue, tracker in self._issue_trackers.items():
            weight = tracker.get_old_weight(len(self._offers))
            total_weight += weight
            old_issue_weights[issue] = weight

        for issue in old_issue_weights:
            if total_weight > 0:
                old_issue_weights[issue] /= total_weight

        return old_issue_weights

    def get_pred_opp_max_bid(self) -> Bid | None:
        """
        Get predicted best bid for opponent.

        Returns:
            Bid with maximum value for each issue according to opponent model.
        """
        if not self._offers:
            return None

        values: dict[str, Value] = {}
        for issue, tracker in self._issue_trackers.items():
            max_value = tracker.get_max_value()
            if max_value is not None:
                values[issue] = max_value

        return Bid(values) if values else None

    def get_opp_offers(self) -> list[Bid]:
        """Get list of opponent offers."""
        return list(self._offers)


class RankNet:
    """
    Simple Multi-Layer Perceptron for learning to rank bids.

    Implements a neural network that learns pairwise preferences
    by comparing bids and outputting which is better.

    Architecture: input -> hidden -> output (sigmoid activation)
    Uses backpropagation for training.
    """

    def __init__(
        self,
        input_count: int,
        hidden_count: int,
        output_count: int = 1,
        learning_rate: float = 0.003,
    ) -> None:
        """
        Initialize the neural network.

        Args:
            input_count: Number of input neurons (2x for pairwise comparison).
            hidden_count: Number of hidden neurons.
            output_count: Number of output neurons (1 for ranking).
            learning_rate: Learning rate for backpropagation.
        """
        self._learning_rate = learning_rate
        self._input_count = input_count
        self._hidden_count = hidden_count
        self._output_count = output_count

        # Initialize weights with small random values
        self._weights_ih = np.random.randn(input_count, hidden_count) * 0.5
        self._bias_h = np.zeros(hidden_count)
        self._weights_ho = np.random.randn(hidden_count, output_count) * 0.5
        self._bias_o = np.zeros(output_count)

    def _sigmoid(self, x: np.ndarray) -> np.ndarray:
        """Sigmoid activation function."""
        # Clip to prevent overflow
        x = np.clip(x, -500, 500)
        return 1.0 / (1.0 + np.exp(-x))

    def _sigmoid_derivative(self, x: np.ndarray) -> np.ndarray:
        """Derivative of sigmoid function."""
        s = self._sigmoid(x)
        return s * (1 - s)

    def forward(self, x: np.ndarray) -> np.ndarray:
        """
        Forward pass through the network.

        Args:
            x: Input vector.

        Returns:
            Output vector.
        """
        self._hidden_input = np.dot(x, self._weights_ih) + self._bias_h
        self._hidden_output = self._sigmoid(self._hidden_input)
        self._output_input = (
            np.dot(self._hidden_output, self._weights_ho) + self._bias_o
        )
        output = self._sigmoid(self._output_input)
        return output

    def set_input(self, x: np.ndarray) -> None:
        """Set input for later calculation."""
        self._input = x

    def calculate(self) -> None:
        """Calculate output from stored input."""
        self._output = self.forward(self._input)

    def get_output(self) -> np.ndarray:
        """Get the output."""
        return self._output

    def train_step(
        self, x: np.ndarray, target: np.ndarray, learning_rate: float | None = None
    ) -> None:
        """
        Perform one training step with backpropagation.

        Args:
            x: Input vector.
            target: Target output.
            learning_rate: Optional learning rate override.
        """
        lr = learning_rate if learning_rate is not None else self._learning_rate

        # Forward pass
        output = self.forward(x)

        # Calculate output layer error
        output_error = target - output
        output_delta = output_error * self._sigmoid_derivative(self._output_input)

        # Calculate hidden layer error
        hidden_error = np.dot(output_delta, self._weights_ho.T)
        hidden_delta = hidden_error * self._sigmoid_derivative(self._hidden_input)

        # Update weights and biases
        self._weights_ho += lr * np.outer(self._hidden_output, output_delta)
        self._bias_o += lr * output_delta.flatten()
        self._weights_ih += lr * np.outer(x, hidden_delta)
        self._bias_h += lr * hidden_delta.flatten()


class MyProfile:
    """
    Own preference model using RankNet.

    Uses a neural network to learn utilities from pairwise preference
    comparisons provided through the SHAOP elicitation mechanism.
    """

    def __init__(
        self, profile: Profile, epoch: int = 40, learning_rate: float = 0.01
    ) -> None:
        """
        Initialize preference model.

        Args:
            profile: The partial ordering profile.
            epoch: Number of training epochs.
            learning_rate: Learning rate for neural network.
        """
        if not isinstance(profile, DefaultPartialOrdering):
            raise ValueError("Only DefaultPartialOrdering is supported")

        self._learning_rate = learning_rate
        self._epoch = epoch
        self._domain = profile.getDomain()
        self._bidlist = list(profile.getBids())
        self._reservation_bid = profile.getReservationBid()
        self._all_bids = AllBidsList(self._domain)

        # Calculate input size (one-hot encoding of all values)
        self._input_count = 0
        for issue in self._domain.getIssues():
            self._input_count += len(list(self._domain.getValues(issue)))

        self._hidden_count = self._input_count * 2

        # Initialize neural network
        self._ann = RankNet(
            self._input_count, self._hidden_count, 1, self._learning_rate
        )

        # Training data
        self._dataset: list[tuple[np.ndarray, np.ndarray]] = []

        # Utility map for all bids
        self._all_utility_map: dict[Bid, float] = {}

        # Value position mapping for one-hot encoding
        self._value_position: dict[str, dict[Value, int]] = {}

        # Value frequency tracking for elicitation
        self._value_frequency: dict[str, dict[Value, int]] = {}

        # Initialize
        self._set_value_frequency(self._bidlist)
        self._get_value_ind()
        self._construct_data(profile)
        self._train(self._epoch, self._learning_rate)

    def _construct_data(self, profile: Profile) -> None:
        """
        Construct training data from pairwise preferences.

        Args:
            profile: The partial ordering profile.
        """
        prof = profile
        if not isinstance(prof, DefaultPartialOrdering):
            return

        output = np.array([1.0])

        for i in range(len(self._bidlist)):
            for j in range(i + 1, len(self._bidlist)):
                bid1 = self._bidlist[i]
                bid2 = self._bidlist[j]

                if prof.isPreferredOrEqual(bid1, bid2):
                    # bid1 >= bid2
                    data = np.concatenate(
                        [self._bid_to_vector(bid1), self._bid_to_vector(bid2)]
                    )
                    self._dataset.append((data, output.copy()))

                if prof.isPreferredOrEqual(bid2, bid1):
                    # bid2 >= bid1
                    data = np.concatenate(
                        [self._bid_to_vector(bid2), self._bid_to_vector(bid1)]
                    )
                    self._dataset.append((data, output.copy()))

    def _get_value_ind(self) -> None:
        """Build mapping from values to input positions."""
        value_ind = 0
        for issue in self._domain.getIssues():
            temp: dict[Value, int] = {}
            for value in self._domain.getValues(issue):
                temp[value] = value_ind
                value_ind += 1
            self._value_position[issue] = temp

    def _bid_to_vector(self, bid: Bid) -> np.ndarray:
        """
        Convert bid to one-hot encoded vector.

        Args:
            bid: The bid to convert.

        Returns:
            One-hot encoded numpy array.
        """
        features = np.zeros(self._input_count)
        for issue in self._domain.getIssues():
            value = bid.getValue(issue)
            if value is not None and issue in self._value_position:
                if value in self._value_position[issue]:
                    value_pos = self._value_position[issue][value]
                    features[value_pos] = 1.0
        return features

    def _train(self, epoch: int, lr: float) -> None:
        """
        Train the neural network.

        Args:
            epoch: Number of training epochs.
            lr: Learning rate.
        """
        for _ in range(epoch):
            # Shuffle dataset
            random.shuffle(self._dataset)
            for data, output in self._dataset:
                self._ann.train_step(data, output, lr)

        # Update utility map after training
        self._get_sorted(self._all_bids)

    def subtrain(self, epoch: int, lr: float) -> None:
        """Additional training rounds."""
        self._train(epoch, lr)

    def get_utility(self, bid: Bid) -> float:
        """
        Get raw utility from neural network.

        Args:
            bid: The bid to evaluate.

        Returns:
            Utility value.
        """
        bid_vec = self._bid_to_vector(bid)
        self._ann.set_input(bid_vec)
        self._ann.calculate()
        return float(self._ann.get_output()[0])

    def get_rank_utility(self, bid: Bid) -> float:
        """
        Get normalized rank-based utility.

        Args:
            bid: The bid to evaluate.

        Returns:
            Utility between 0 and 1 based on rank.
        """
        return self._all_utility_map.get(bid, 0.0)

    def _get_sorted(self, all_bids: AllBidsList) -> None:
        """
        Sort all bids by utility and create rank-based utility map.

        Args:
            all_bids: List of all possible bids.
        """
        space_size = int(all_bids.size())
        all_bid_list: list[Bid] = []
        for n in range(space_size):
            bid = all_bids.get(n)
            all_bid_list.append(bid)

        # Sort by utility (descending)
        all_bid_list.sort(key=lambda b: self.get_utility(b), reverse=True)

        # Create rank-based utility map
        for n, bid in enumerate(all_bid_list):
            utility = (len(all_bid_list) - n) / len(all_bid_list)
            self._all_utility_map[bid] = utility

    def _set_value_frequency(self, bidlist: list[Bid]) -> None:
        """
        Initialize and update value frequency map.

        Args:
            bidlist: List of bids to process.
        """
        # Initialize if empty
        if not self._value_frequency:
            for issue in self._domain.getIssues():
                temp: dict[Value, int] = {}
                for value in self._domain.getValues(issue):
                    temp[value] = 0
                self._value_frequency[issue] = temp

        # Count frequencies
        for bid in bidlist:
            for issue in bid.getIssues():
                value = bid.getValue(issue)
                if value is not None and issue in self._value_frequency:
                    if value in self._value_frequency[issue]:
                        self._value_frequency[issue][value] += 1

    def get_most_informative(self) -> dict[str, list[Value]]:
        """
        Get the most informative values for elicitation.

        Returns values with lowest frequency (least information).

        Returns:
            Dict mapping issues to list of least frequent values.
        """
        info_value: dict[str, list[Value]] = {}

        for issue in self._domain.getIssues():
            elicit_value_set: list[Value] = []
            min_freq = float("inf")

            for value in self._domain.getValues(issue):
                freq = self._value_frequency.get(issue, {}).get(value, 0)
                if not elicit_value_set:
                    elicit_value_set.append(value)
                    min_freq = freq
                elif freq < min_freq:
                    elicit_value_set.clear()
                    elicit_value_set.append(value)
                    min_freq = freq
                elif freq == min_freq:
                    elicit_value_set.append(value)

            info_value[issue] = elicit_value_set

        return info_value

    def get_elicit_bid(self) -> list[Bid]:
        """
        Generate bids for elicitation using least frequent values.

        Returns:
            List of bids constructed from least frequent values.
        """
        info_map = self.get_most_informative()
        bid_map: dict[str, Value] = {}
        bid_result: list[Bid] = []
        issues = list(info_map.keys())
        self._bid_dfs(issues, bid_map, info_map, bid_result)
        return bid_result

    def _bid_dfs(
        self,
        issues: list[str],
        bid_map: dict[str, Value],
        info_map: dict[str, list[Value]],
        bid_result_list: list[Bid],
    ) -> None:
        """
        DFS to generate all combinations of informative values.

        Args:
            issues: List of issue names.
            bid_map: Current partial bid being built.
            info_map: Map of informative values per issue.
            bid_result_list: Output list of generated bids.
        """
        if len(bid_map) == len(issues):
            bid_result_list.append(Bid(dict(bid_map)))
            return

        current_issue = issues[len(bid_map)]
        for value in info_map.get(current_issue, []):
            bid_map[current_issue] = value
            self._bid_dfs(issues, bid_map, info_map, bid_result_list)
            del bid_map[current_issue]

    def update(self, bid: Bid, better_bids: list[Bid], worse_bids: list[Bid]) -> None:
        """
        Update model with new comparison data from elicitation.

        Args:
            bid: The elicited bid.
            better_bids: Bids better than the elicited bid.
            worse_bids: Bids worse than the elicited bid.
        """
        self._update_dataset(bid, better_bids, worse_bids)
        self._update_bid_and_value_frequency(bid)
        self._train(self._epoch, self._learning_rate)

    def _update_dataset(
        self, bid: Bid, better_bids: list[Bid], worse_bids: list[Bid]
    ) -> None:
        """
        Add new comparison data to training dataset.

        Args:
            bid: The elicited bid.
            better_bids: Bids better than the elicited bid.
            worse_bids: Bids worse than the elicited bid.
        """
        output = np.array([1.0])

        for better_bid in better_bids:
            data = np.concatenate(
                [self._bid_to_vector(better_bid), self._bid_to_vector(bid)]
            )
            self._dataset.append((data, output.copy()))

        for worse_bid in worse_bids:
            data = np.concatenate(
                [self._bid_to_vector(bid), self._bid_to_vector(worse_bid)]
            )
            self._dataset.append((data, output.copy()))

    def _update_bid_and_value_frequency(self, bid: Bid) -> None:
        """Update bid list and value frequencies."""
        self._bidlist.append(bid)
        self._set_value_frequency([bid])

    def get_domain(self) -> Domain:
        """Get the domain."""
        return self._domain

    def get_reservation_bid(self) -> Bid | None:
        """Get the reservation bid."""
        return self._reservation_bid

    def get_bidlist(self) -> list[Bid]:
        """Get the list of known bids."""
        return list(self._bidlist)

    def get_all_bidlist(self) -> list[Bid]:
        """Get list of all possible bids."""
        space_size = int(self._all_bids.size())
        return [self._all_bids.get(n) for n in range(space_size)]


# =============================================================================
# Main Agent Class
# =============================================================================


class MyProfileSAOP:
    """
    Own preference model for SAOP mode using LinearAdditive utility space.

    Provides the same interface as MyProfile but uses the actual utilities
    from the linear additive profile instead of learning them with RankNet.
    """

    def __init__(self, profile: LinearAdditive) -> None:
        """
        Initialize preference model from LinearAdditive profile.

        Args:
            profile: The LinearAdditive utility space profile.
        """
        self._profile = profile
        self._domain = profile.getDomain()
        self._reservation_bid = profile.getReservationBid()
        self._all_bids = AllBidsList(self._domain)

        # Build utility map for all bids
        self._all_utility_map: dict[Bid, float] = {}
        space_size = int(self._all_bids.size())
        for n in range(space_size):
            bid = self._all_bids.get(n)
            self._all_utility_map[bid] = float(self._profile.getUtility(bid))

    def subtrain(self, epoch: int, lr: float) -> None:
        """No-op for SAOP mode - utilities are already known."""
        pass

    def get_utility(self, bid: Bid) -> float:
        """
        Get utility from the linear additive profile.

        Args:
            bid: The bid to evaluate.

        Returns:
            Utility value.
        """
        return float(self._profile.getUtility(bid))

    def get_rank_utility(self, bid: Bid) -> float:
        """
        Get utility (same as get_utility for SAOP mode).

        Args:
            bid: The bid to evaluate.

        Returns:
            Utility between 0 and 1.
        """
        return self._all_utility_map.get(bid, float(self._profile.getUtility(bid)))

    def get_most_informative(self) -> dict[str, list[Value]]:
        """
        Not used in SAOP mode.

        Returns:
            Empty dict - no elicitation in SAOP mode.
        """
        return {}

    def get_elicit_bid(self) -> list[Bid]:
        """
        Not used in SAOP mode.

        Returns:
            Empty list - no elicitation in SAOP mode.
        """
        return []

    def update(self, bid: Bid, better_bids: list[Bid], worse_bids: list[Bid]) -> None:
        """No-op for SAOP mode - preferences are already known."""
        pass

    def get_domain(self) -> Domain:
        """Get the domain."""
        return self._domain

    def get_reservation_bid(self) -> Bid | None:
        """Get the reservation bid."""
        return self._reservation_bid

    def get_bidlist(self) -> list[Bid]:
        """Get list of all possible bids (all bids are known in SAOP)."""
        space_size = int(self._all_bids.size())
        return [self._all_bids.get(n) for n in range(space_size)]

    def get_all_bidlist(self) -> list[Bid]:
        """Get list of all possible bids."""
        space_size = int(self._all_bids.size())
        return [self._all_bids.get(n) for n in range(space_size)]


class BlingBling(DefaultParty):
    """
    BlingBling Agent from ANAC 2020 (TU Delft).

    A stage-based negotiation agent using neural network-based ranking
    (RankNet) for preference learning. Features:

    Strategy:
    - Exploration stage: Learn opponent preferences and gather information
    - Agreement search stage: Find mutually beneficial agreements
    - Uses RankNet to learn utilities from pairwise comparisons
    - Frequency-based opponent modeling (SFM)
    - Cost-aware elicitation decisions in SHAOP mode
    - Time-dependent threshold for bid generation/acceptance

    The agent can be tuned via AutoML for hyperparameter optimization.
    """

    def __init__(self, reporter: Reporter | None = None) -> None:
        """
        Initialize the BlingBling agent.

        Args:
            reporter: Optional reporter for logging.
        """
        super().__init__(reporter)
        self._random = random.Random()

        # Bid tracking
        self._now_received_bid: Bid | None = None
        self._last_received_bid: Bid | None = None
        self._me: PartyId | None = None
        self._profile_int: ProfileInterface | None = None
        self._progress: ProgressRounds | None = None
        self._my_profile: MyProfile | MyProfileSAOP | None = None
        self._opp_profile: OpponentProfile | None = None
        self._start_record = False
        self._is_saop_mode = False

        self._fixed_zone_value: dict[str, Value] = {}
        self._nego_zone: list[str] = []
        self._all_bids: AllBidsList | None = None
        self._acceptable_bids: list[Bid] = []
        self._elicit_list: list[Bid] = []
        self._pareto_bids: list[Bid] = []

        self._elicit_bid: Bid | None = None

        # Training params
        self._learning_rate = 0.01
        self._epoch = 40

        # Elicitation params
        self._elicit_threshold = 0.7
        self._elicit_cost = 0.01
        self._elicit_flag = 0
        self._elicit_cnt = 0

        # Strategy thresholds
        self._threshold = 1.0
        self._accept_threshold = 1.0
        self._estimate_nash_threshold = 0.7
        self._reservation_threshold = 0.0
        self._re_threshold = 0  # Round when first acceptable bid found

        # Opponent modeling params
        self._max_utility_opp_for_me = 0.0
        self._nash_ratio = 1.7

        # Stage params
        self._explore_rounds = 150
        self._explore_stage_threshold = 0.95
        self._agreement_search_rounds = 195
        self._generate_range_size = 0.01
        self._random_level = 0.5
        self._use_all_flag = 0

    def notifyChange(self, info: Inform) -> None:
        """
        Handle incoming information from the negotiation protocol.

        Args:
            info: The information received.
        """
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
            raise RuntimeError(f"Failed to handle info: {e}") from e

    def _handle_settings(self, settings: Settings) -> None:
        """
        Initialize agent with settings.

        Args:
            settings: The negotiation settings.
        """
        params = settings.getParameters()

        # Get configurable parameters
        if params.get("lr") is not None:
            self._learning_rate = float(params.get("lr"))
        if params.get("epoch") is not None:
            self._epoch = int(params.get("epoch"))
        if params.get("explorernd") is not None:
            self._explore_rounds = int(params.get("explorernd"))
        if params.get("explorethreshold") is not None:
            self._explore_stage_threshold = float(params.get("explorethreshold"))
        if params.get("agreementrnd") is not None:
            self._agreement_search_rounds = int(params.get("agreementrnd"))
        if params.get("generaterange") is not None:
            self._generate_range_size = float(params.get("generaterange"))
        if params.get("elicitthreshold") is not None:
            self._elicit_threshold = float(params.get("elicitthreshold"))
        if params.get("elicitationcost") is not None:
            self._elicit_cost = float(params.get("elicitationcost"))
        if params.get("nashutility") is not None:
            self._estimate_nash_threshold = float(params.get("nashutility"))
        if params.get("useall") is not None:
            self._use_all_flag = int(params.get("useall"))
        if params.get("randomlevel") is not None:
            self._random_level = float(params.get("randomlevel"))

        self._profile_int = ProfileConnectionFactory.create(
            settings.getProfile().getURI(), self.getReporter()
        )
        self._me = settings.getID()
        self._progress = settings.getProgress()

        if not isinstance(self._progress, ProgressRounds):
            raise ValueError("Only ProgressRounds is supported")

        profile = self._profile_int.getProfile()
        self._opp_profile = OpponentProfile(profile.getDomain())

        # Detect profile type and create appropriate profile model
        if isinstance(profile, LinearAdditive):
            # SAOP mode with full utility information
            self._is_saop_mode = True
            self._my_profile = MyProfileSAOP(profile)
        elif isinstance(profile, DefaultPartialOrdering):
            # SHAOP mode with partial ordering
            self._is_saop_mode = False
            self._my_profile = MyProfile(profile, self._epoch, self._learning_rate)
        else:
            raise ValueError(
                f"Unsupported profile type: {type(profile).__name__}. "
                "Only LinearAdditive (SAOP) and DefaultPartialOrdering (SHAOP) are supported."
            )

        self._all_bids = AllBidsList(self._my_profile.get_domain())

    def _handle_action_done(self, info: ActionDone) -> None:
        """
        Handle opponent's action or elicitation response.

        Args:
            info: The action done information.
        """
        other_act = info.getAction()
        if isinstance(other_act, Offer):
            actor = other_act.getActor()
            if actor != self._me:
                self._now_received_bid = other_act.getBid()
        elif isinstance(other_act, Comparison):
            # Handle elicitation response
            if self._my_profile is not None:
                self._my_profile.update(
                    other_act.getBid(),
                    list(other_act.getBetter()),
                    list(other_act.getWorse()),
                )
            self._my_turn()

    def _my_turn(self) -> None:
        """Execute agent's turn."""
        if (
            self._progress is None
            or self._my_profile is None
            or self._opp_profile is None
        ):
            return

        round_num = self._progress.getCurrentRound()
        total_rounds = self._progress.getTotalRounds()
        action: Action | None = None

        # Early round training
        if round_num <= 7:
            self._my_profile.subtrain(self._epoch, self._learning_rate)

        # Register early opponent offers
        if self._now_received_bid is not None and round_num <= 2:
            self._opp_profile.register_offer(self._now_received_bid)

        # Start recording when opponent changes bids
        if (
            self._last_received_bid is not None
            and self._last_received_bid != self._now_received_bid
        ):
            self._start_record = True

        if self._start_record and round_num <= self._explore_rounds:
            if self._now_received_bid is not None:
                self._opp_profile.register_offer(self._now_received_bid)

        # Update threshold
        self._set_threshold(round_num, total_rounds)

        # Check acceptance
        if self._now_received_bid is not None:
            if self._is_acceptable(self._now_received_bid, round_num):
                action = Accept(self._me, self._now_received_bid)

        # Elicitation decision (only in SHAOP mode)
        if not self._is_saop_mode:
            elicit_rnd = (
                1
                if 0.05 <= self._elicit_cost <= 0.07
                else int(0.05 / self._elicit_cost)
            )

            if (
                action is None
                and round_num > self._explore_rounds
                and self._elicit_cnt < elicit_rnd
                and self._elicit_flag == 0
            ):
                elicit_bid_list = self._my_profile.get_elicit_bid()
                if self._if_elicit_comparison(elicit_bid_list):
                    if self._use_all_flag == 1:
                        action = ElicitComparison(
                            self._me,
                            self._elicit_bid,
                            self._my_profile.get_all_bidlist(),
                        )
                    else:
                        action = ElicitComparison(
                            self._me, self._elicit_bid, self._my_profile.get_bidlist()
                        )
                    self._elicit_cnt += 1
                    self._elicit_flag = 1

            if self._elicit_flag == 1:
                self._my_profile.subtrain(self._epoch, self._learning_rate)

            if self._elicit_cnt == elicit_rnd:
                self._get_nash()
                self._elicit_cnt += 1

        # Generate bid if no action yet
        if action is None and round_num <= total_rounds - 1:
            action = self._generate_next_bid(self._threshold)

        # Final round logic
        if action is None and round_num == total_rounds:
            reservation_bid = self._my_profile.get_reservation_bid()
            if self._now_received_bid is not None and reservation_bid is not None:
                if self._my_profile.get_rank_utility(
                    self._now_received_bid
                ) > self._my_profile.get_rank_utility(reservation_bid):
                    action = Accept(self._me, self._now_received_bid)

            opp_bids = self._get_sorted_acceptable(self._opp_profile.get_opp_offers())
            if opp_bids and reservation_bid is not None:
                if self._my_profile.get_rank_utility(
                    opp_bids[0]
                ) > self._my_profile.get_rank_utility(reservation_bid):
                    action = Offer(self._me, opp_bids[0])
                else:
                    action = self._generate_next_bid(self._threshold)

        self._last_received_bid = self._now_received_bid
        if isinstance(action, Offer):
            self._elicit_flag = 0

        if action is not None:
            self.getConnection().send(action)

        self._progress = self._progress.advance()

    def _is_acceptable(self, bid: Bid, round_num: int) -> bool:
        """
        Check if a bid is acceptable.

        Args:
            bid: The bid to check.
            round_num: Current round number.

        Returns:
            True if the bid should be accepted.
        """
        if self._my_profile is None:
            return False

        if round_num > self._agreement_search_rounds:
            return self._my_profile.get_rank_utility(bid) >= self._threshold

        if not self._acceptable_bids:
            if self._my_profile.get_rank_utility(bid) >= self._threshold:
                self._accept_threshold = self._threshold
                self._re_threshold = round_num
                self._acceptable_bids.append(bid)
                self._threshold = 1.0  # Restart from 1.0
            return False
        else:
            if self._my_profile.get_rank_utility(bid) >= self._threshold:
                return True
            if self._my_profile.get_rank_utility(bid) >= self._accept_threshold:
                if bid not in self._acceptable_bids:
                    self._acceptable_bids.append(bid)
            return False

    def _if_elicit_comparison(self, inbidlist: list[Bid]) -> bool:
        """
        Decide whether to elicit a comparison.

        Args:
            inbidlist: List of candidate bids for elicitation.

        Returns:
            True if elicitation should be performed.
        """
        if not inbidlist or self._opp_profile is None:
            return False

        # Sort by opponent utility (descending)
        inbidlist.sort(
            key=lambda b: self._opp_profile.get_pred_opp_utility(b), reverse=True
        )

        for bid in inbidlist:
            if bid not in self._elicit_list:
                if (
                    self._opp_profile.get_pred_opp_utility(bid)
                    >= self._elicit_threshold
                ):
                    self._elicit_bid = bid
                    self._elicit_list.append(bid)
                    return True

        return False

    def _set_threshold(self, round_num: int, total_round: int) -> None:
        """
        Update bidding threshold based on current round.

        Implements a stage-based concession strategy.

        Args:
            round_num: Current round number.
            total_round: Total number of rounds.
        """
        if not self._acceptable_bids:
            if round_num < 10:
                self._threshold = 0.95
            elif round_num < self._explore_rounds:
                self._threshold = (self._explore_rounds - round_num) * (
                    1.0 - self._explore_stage_threshold
                ) / (self._explore_rounds - 10) + self._explore_stage_threshold
            elif round_num <= total_round - 1:
                self._threshold = (total_round - 1 - round_num) * (
                    self._explore_stage_threshold - self._estimate_nash_threshold
                ) / (
                    total_round - 1 - self._explore_rounds
                ) + self._estimate_nash_threshold
        else:
            self._threshold = min(
                (total_round - 1 - round_num)
                * (1 - self._accept_threshold)
                / (total_round - 1 - self._re_threshold)
                + self._accept_threshold,
                1.0,
            )

    def _get_sorted_acceptable(self, accbidlist: list[Bid]) -> list[Bid]:
        """
        Sort bids by our utility (descending).

        Args:
            accbidlist: List of bids to sort.

        Returns:
            Sorted list of bids.
        """
        if self._my_profile is None:
            return accbidlist
        return sorted(
            accbidlist, key=lambda b: self._my_profile.get_rank_utility(b), reverse=True
        )

    def _generate_next_bid(self, generate_threshold: float) -> Offer:
        """
        Generate the next bid offer.

        Selects bids within threshold range, then picks the one
        with highest predicted opponent utility.

        Args:
            generate_threshold: Minimum utility threshold.

        Returns:
            An Offer action.
        """
        if (
            self._all_bids is None
            or self._my_profile is None
            or self._opp_profile is None
        ):
            raise ValueError("Agent not properly initialized")

        space_size = int(self._all_bids.size())
        candidate: list[Bid] = []
        candidate_backup: list[Bid] = []

        for n in range(space_size):
            bid = self._all_bids.get(n)
            utility = self._my_profile.get_rank_utility(bid)

            if (
                generate_threshold
                <= utility
                < generate_threshold + self._generate_range_size
            ):
                candidate.append(bid)

            if utility >= generate_threshold:
                candidate_backup.append(bid)

        # Select random subset for exploration
        if candidate:
            candidate_num = int(math.floor(len(candidate) * self._random_level) + 1)
            rand: list[Bid] = []
            attempts = 0
            while len(rand) < candidate_num and attempts < candidate_num * 3:
                temp_idx = self._random.randint(0, len(candidate) - 1)
                if candidate[temp_idx] not in rand:
                    rand.append(candidate[temp_idx])
                attempts += 1
        else:
            candidate_num = int(
                math.floor(len(candidate_backup) * self._random_level) + 1
            )
            rand = []
            attempts = 0
            while len(rand) < candidate_num and attempts < candidate_num * 3:
                if candidate_backup:
                    temp_idx = self._random.randint(0, len(candidate_backup) - 1)
                    if candidate_backup[temp_idx] not in rand:
                        rand.append(candidate_backup[temp_idx])
                attempts += 1

        if not rand:
            # Fallback: use any bid from backup
            if candidate_backup:
                rand = [candidate_backup[0]]
            else:
                # Last resort: any bid
                rand = [self._all_bids.get(0)]

        # Sort by opponent utility (descending) and pick best
        rand.sort(key=lambda b: self._opp_profile.get_pred_opp_utility(b), reverse=True)

        bid = rand[0]

        # Consider acceptable bids
        if self._acceptable_bids:
            self._acceptable_bids = self._get_sorted_acceptable(self._acceptable_bids)
            best_acceptable = self._acceptable_bids[0]
            utility = self._my_profile.get_rank_utility(best_acceptable)
            if (
                generate_threshold
                <= utility
                < generate_threshold + self._generate_range_size
            ):
                bid = best_acceptable

        return Offer(self._me, bid)

    def _get_nash(self) -> None:
        """
        Estimate Nash bargaining solution and update threshold.

        Uses Pareto frontier to find the Nash point.
        """
        if (
            not self._pareto_bids
            or self._my_profile is None
            or self._opp_profile is None
        ):
            return

        nash_bid = None
        max_nash_product = 0.0

        for bid in self._pareto_bids:
            nash_product = self._my_profile.get_rank_utility(
                bid
            ) * self._opp_profile.get_pred_opp_utility(bid)
            if nash_product > max_nash_product:
                nash_bid = bid
                max_nash_product = nash_product

        if nash_bid is not None:
            nash_utility = self._my_profile.get_rank_utility(nash_bid)
            if nash_utility > self._estimate_nash_threshold:
                reservation_bid = self._my_profile.get_reservation_bid()
                reservation_utility = (
                    self._my_profile.get_rank_utility(reservation_bid)
                    if reservation_bid
                    else 0.0
                )
                self._estimate_nash_threshold = max(nash_utility, reservation_utility)

    def _get_pareto_frontier(self) -> None:
        """
        Compute Pareto frontier of bids.

        Updates self._pareto_bids with non-dominated bids.
        """
        if self._my_profile is None:
            return

        for bid in self._my_profile.get_all_bidlist():
            if not self._pareto_bids:
                self._pareto_bids.append(bid)
                continue

            # Check against existing Pareto bids
            dominated = False
            to_remove = []

            for pbid in self._pareto_bids:
                if self._is_dominated(bid, pbid):
                    dominated = True
                    break
                elif self._is_dominated(pbid, bid):
                    to_remove.append(pbid)

            for pbid in to_remove:
                self._pareto_bids.remove(pbid)

            if not dominated:
                self._pareto_bids.append(bid)

    def _is_dominated(self, bid1: Bid, bid2: Bid) -> bool:
        """
        Check if bid1 is dominated by bid2.

        Args:
            bid1: First bid.
            bid2: Second bid.

        Returns:
            True if bid2 dominates bid1 (better in both dimensions).
        """
        if self._my_profile is None or self._opp_profile is None:
            return False

        bid1_my = self._my_profile.get_rank_utility(bid1)
        bid1_opp = self._opp_profile.get_pred_opp_utility(bid1)
        bid2_my = self._my_profile.get_rank_utility(bid2)
        bid2_opp = self._opp_profile.get_pred_opp_utility(bid2)

        return bid2_my >= bid1_my and bid2_opp >= bid1_opp

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SAOP", "SHAOP"},
            {"geniusweb.profile.DefaultPartialOrdering"},
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return "BlingBling Agent (TU Delft, ANAC 2020): Stage-based RankNet learning agent (AI-translated from Java)"
