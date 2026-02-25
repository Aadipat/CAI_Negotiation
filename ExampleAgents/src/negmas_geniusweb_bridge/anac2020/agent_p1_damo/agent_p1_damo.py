"""
AgentP1DAMO - A negotiation agent using hill climbing optimization.

AI-translated from Java.

Original: ANAC 2020 competition agent.

The agent uses:
- Hill climbing search to find optimal bids
- Importance maps to estimate bid values
- Time-dependent concession strategy
- Opponent modeling via frequency analysis
"""

from __future__ import annotations

import logging
import math
import random
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any

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
from geniusweb.issuevalue.DiscreteValue import DiscreteValue
from geniusweb.issuevalue.Value import Value
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.DefaultPartialOrdering import DefaultPartialOrdering
from geniusweb.profile.PartialOrdering import PartialOrdering
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


class ImpUnit:
    """
    Importance unit for tracking value weights.

    Attributes:
        value_of_issue: The value this unit represents.
        weight_sum: Sum of weights from bid ordering.
        count: Number of occurrences.
        mean_weight_sum: Average weight (used for importance calculation).
    """

    def __init__(self, value: Value):
        """
        Initialize an importance unit.

        Args:
            value: The issue value this unit represents.
        """
        self.value_of_issue: Value = value
        self.weight_sum: int = 0
        self.count: int = 0
        self.mean_weight_sum: float = 0.0

    def __repr__(self) -> str:
        return f"{self.value_of_issue} {self.mean_weight_sum}"


class ImpMap(dict[str, list[ImpUnit]]):
    """
    Importance map for tracking value importance per issue.

    Maps issue names to lists of ImpUnit objects, sorted by importance.
    """

    def __init__(self, profile: PartialOrdering):
        """
        Initialize the importance map from a partial ordering profile.

        Args:
            profile: The partial ordering profile to initialize from.
        """
        super().__init__()
        self._allbids = AllBidsList(profile.getDomain())
        self._domain = profile.getDomain()

        # Create empty importance map
        for issue in self._domain.getIssues():
            values = self._domain.getValues(issue)
            issue_imp_units: list[ImpUnit] = []
            for value in values:
                issue_imp_units.append(ImpUnit(value))
            self[issue] = issue_imp_units

    def opponent_update(self, received_offer_bid: Bid) -> None:
        """
        Update opponent importance map with received bid.

        Increases the mean_weight_sum of values in the received bid.

        Args:
            received_offer_bid: The bid received from the opponent.
        """
        for issue in received_offer_bid.getIssues():
            current_issue_list = self.get(issue)
            if current_issue_list is None:
                continue
            for current_unit in current_issue_list:
                if current_unit.value_of_issue == received_offer_bid.getValue(issue):
                    current_unit.mean_weight_sum += 1
                    break

        # Sort by mean_weight_sum descending
        for imp_unit_list in self.values():
            imp_unit_list.sort(key=lambda x: x.mean_weight_sum, reverse=True)

    def self_update(self, bid_ordering: list[Bid]) -> None:
        """
        Update self importance map based on bid ordering.

        Args:
            bid_ordering: List of bids ordered from worst to best.
        """
        current_weight = 0
        for bid in bid_ordering:
            current_weight += 1
            for issue in bid.getIssues():
                current_issue_list = self.get(issue)
                if current_issue_list is None:
                    continue
                for current_unit in current_issue_list:
                    if str(current_unit.value_of_issue) == str(bid.getValue(issue)):
                        current_unit.weight_sum += current_weight
                        current_unit.count += 1
                        break

        # Calculate weights
        for imp_unit_list in self.values():
            for current_unit in imp_unit_list:
                if current_unit.count == 0:
                    current_unit.mean_weight_sum = 0.0
                else:
                    current_unit.mean_weight_sum = (
                        current_unit.weight_sum / current_unit.count
                    )

        # Sort by mean_weight_sum descending
        for imp_unit_list in self.values():
            imp_unit_list.sort(key=lambda x: x.mean_weight_sum, reverse=True)

        # Find the minimum
        min_mean_weight_sum = float("inf")
        for issue, imp_unit_list in self.items():
            if imp_unit_list:
                temp_mean_weight_sum = imp_unit_list[-1].mean_weight_sum
                if temp_mean_weight_sum < min_mean_weight_sum:
                    min_mean_weight_sum = temp_mean_weight_sum

        # Subtract minimum from all values
        if min_mean_weight_sum != float("inf"):
            for imp_unit_list in self.values():
                for current_unit in imp_unit_list:
                    current_unit.mean_weight_sum -= min_mean_weight_sum

    def get_importance(self, bid: Bid) -> float:
        """
        Calculate the importance of a bid.

        Args:
            bid: The bid to evaluate.

        Returns:
            The total importance value of the bid.
        """
        bid_importance = 0.0
        for issue in bid.getIssues():
            value = bid.getValue(issue)
            value_importance = 0.0
            issue_units = self.get(issue)
            if issue_units is not None:
                for imp_unit in issue_units:
                    if imp_unit.value_of_issue == value:
                        value_importance = imp_unit.mean_weight_sum
                        break
            bid_importance += value_importance
        return bid_importance


class SimpleLinearOrdering:
    """
    A simple list of bids with linear utility ordering.

    Bids are ordered from worst (index 0) to best (last index).
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
            profile: The profile to create ordering from (LinearAdditive or DefaultPartialOrdering).

        Returns:
            A new SimpleLinearOrdering instance.

        Raises:
            ValueError: If profile type is not supported.
        """
        domain = profile.getDomain()

        if isinstance(profile, LinearAdditive):
            # For LinearAdditive, get all bids and sort by utility
            all_bids = AllBidsList(domain)
            bids_list = list(all_bids)
            bids_list.sort(key=lambda b: float(profile.getUtility(b)))
            return cls(domain, bids_list)
        elif isinstance(profile, DefaultPartialOrdering):
            bids_list = list(profile.getBids())
            # Sort ascending (worse bids first)
            bids_list.sort(
                key=lambda b1: 1 if profile.isPreferredOrEqual(b1, b1) else -1
            )
            # More accurate sorting using pairwise comparison
            for i in range(len(bids_list)):
                for j in range(i + 1, len(bids_list)):
                    if profile.isPreferredOrEqual(bids_list[i], bids_list[j]):
                        bids_list[i], bids_list[j] = bids_list[j], bids_list[i]
            return cls(domain, bids_list)
        else:
            raise ValueError(f"Unsupported profile type: {type(profile)}")

    def getDomain(self) -> Domain:
        """Get the domain."""
        return self._domain

    def getBids(self) -> list[Bid]:
        """Get the list of bids (immutable view)."""
        return list(self._bids)

    def getUtility(self, bid: Bid) -> Decimal:
        """
        Get the utility of a bid.

        Args:
            bid: The bid to evaluate.

        Returns:
            Utility value between 0 and 1.
        """
        if len(self._bids) < 2 or bid not in self._bids:
            # For unknown bids, estimate from neighbors
            neighbors = SearchSpaceBid(self._bids, 2).get_neighbors(bid)
            if neighbors:
                avg_score = sum(self._score(n) for n in neighbors) / len(neighbors)
                return Decimal(str(avg_score))
            return Decimal(0)
        return Decimal(str(self._score(bid)))

    def _score(self, bid: Bid) -> float:
        """Calculate score for a bid based on its position."""
        if bid not in self._bids or len(self._bids) <= 1:
            return 0.0
        index = self._bids.index(bid)
        return round(index / (len(self._bids) - 1), 8)

    def contains(self, bid: Bid) -> bool:
        """Check if bid is in the ordering."""
        return bid in self._bids

    def with_bid(self, bid: Bid, worse_bids: list[Bid]) -> SimpleLinearOrdering:
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


class FitnessBid:
    """Fitness function for evaluating bids."""

    def __init__(self, simple_linear_ordering: SimpleLinearOrdering):
        """
        Initialize fitness function.

        Args:
            simple_linear_ordering: The ordering to use for fitness calculation.
        """
        self._simple_linear_ordering = simple_linear_ordering

    def calc_fitness(self, bid: Bid) -> float:
        """
        Calculate fitness of a bid.

        Args:
            bid: The bid to evaluate.

        Returns:
            Fitness value (utility).
        """
        return float(self._simple_linear_ordering.getUtility(bid))


class SearchSpaceBid:
    """Search space for bids using k-nearest neighbors."""

    DEFAULT_VALUE = 1

    def __init__(self, bids: list[Bid], number_closest_neighbors: int):
        """
        Initialize search space.

        Args:
            bids: List of bids in the search space.
            number_closest_neighbors: Number of neighbors to return.
        """
        self._bids = bids
        self._k = number_closest_neighbors

    def get_neighbors(self, bid: Bid) -> set[Bid]:
        """
        Get the k nearest neighbors of a bid.

        Args:
            bid: The bid to find neighbors for.

        Returns:
            Set of neighboring bids.
        """
        return set(self._get_nearest_neighbors(self._bids, bid, self._k))

    def _get_nearest_neighbors(
        self, neighbors: list[Bid], bid: Bid, num_neighbors: int
    ) -> list[Bid]:
        """Get the nearest neighbors sorted by distance."""
        filtered = [n for n in neighbors if n != bid]
        filtered.sort(key=lambda n: self._calc_distance(bid, n))
        return filtered[:num_neighbors]

    def _calc_distance(self, bid1: Bid, bid2: Bid) -> float:
        """Calculate distance between two bids."""
        total = 0.0
        for issue in bid1.getIssues():
            v1 = bid1.getValue(issue)
            v2 = bid2.getValue(issue)
            if v1 is not None and v2 is not None:
                total += self._calc_value_distance(v1, v2)
        return total

    def _calc_value_distance(self, value1: Value, value2: Value) -> float:
        """Calculate distance between two values."""
        # Try numeric comparison
        if self._is_number(value1) and self._is_number(value2):
            v1 = self._get_numeric_value(value1)
            v2 = self._get_numeric_value(value2)
            max_val = max(abs(v1), abs(v2))
            if max_val > 0:
                return abs(v1 - v2) / max_val
            return 0.0

        # Discrete comparison
        if isinstance(value1, DiscreteValue) and isinstance(value2, DiscreteValue):
            return 0.0 if value1.getValue() == value2.getValue() else 1.0

        return self.DEFAULT_VALUE

    def _is_number(self, value: Value) -> bool:
        """Check if a value is numeric."""
        try:
            if isinstance(value, DiscreteValue):
                float(value.getValue())
                return True
        except (ValueError, TypeError):
            pass
        return False

    def _get_numeric_value(self, value: Value) -> float:
        """Get numeric value from a Value object."""
        if isinstance(value, DiscreteValue):
            return float(value.getValue())
        return 0.0

    def create_random_state(
        self, simple_linear_ordering: SimpleLinearOrdering, all_bids: AllBidsList
    ) -> Bid:
        """
        Create a random initial state.

        Args:
            simple_linear_ordering: Ordering for utility check.
            all_bids: All possible bids.

        Returns:
            A random bid with non-negative utility.
        """
        max_attempts = 1000
        for _ in range(max_attempts):
            bid = self._generate_random_bid(all_bids)
            if float(simple_linear_ordering.getUtility(bid)) >= 0:
                return bid
        # Fallback to first bid
        return self._generate_random_bid(all_bids)

    def _generate_random_bid(self, all_bids: AllBidsList) -> Bid:
        """Generate a random bid from the bid space."""
        size = all_bids.size()
        if size == 0:
            return Bid({})
        index = random.randint(0, int(size) - 1)
        return all_bids.get(index)


class FitnessAnalyzedState:
    """A state with its fitness value."""

    def __init__(self, state: Bid, fitness: float):
        """
        Initialize analyzed state.

        Args:
            state: The bid state.
            fitness: The fitness value.
        """
        self._state = state
        self._fitness = fitness

    def get_state(self) -> Bid:
        """Get the state."""
        return self._state

    def get_fitness(self) -> float:
        """Get the fitness value."""
        return self._fitness


class HillClimbing:
    """Hill climbing search algorithm for bid optimization."""

    def __init__(
        self,
        max_num_iterations: int,
        max_iterations_without_change: int,
        seed: int,
    ):
        """
        Initialize hill climbing algorithm.

        Args:
            max_num_iterations: Maximum number of iterations.
            max_iterations_without_change: Max iterations without improvement before random restart.
            seed: Random seed.

        Raises:
            RuntimeError: If parameters are invalid.
        """
        self._validate(
            max_num_iterations > 0, "Max num of iterations must be positive!"
        )
        self._validate(
            max_iterations_without_change > 0,
            "Max num of iterations without change must be positive!",
        )
        self._validate(
            max_num_iterations >= max_iterations_without_change,
            "Max iterations must be >= iterations without change!",
        )

        self._max_num_iterations = max_num_iterations
        self._max_iterations_without_change = max_iterations_without_change
        self._rand = random.Random(seed)
        self._iterations_without_change = 0

    def _validate(self, condition: bool, message: str) -> None:
        """Validate a condition."""
        if not condition:
            raise RuntimeError(message)

    def search(
        self,
        fitness_function: FitnessBid,
        local_search_space: SearchSpaceBid,
        simple_linear_ordering: SimpleLinearOrdering,
        all_bids: AllBidsList,
    ) -> Bid:
        """
        Perform hill climbing search.

        Args:
            fitness_function: Function to evaluate bid fitness.
            local_search_space: Search space for neighbors.
            simple_linear_ordering: Current bid ordering.
            all_bids: All possible bids.

        Returns:
            The best bid found.
        """
        random_state = local_search_space.create_random_state(
            simple_linear_ordering, all_bids
        )
        current_state = FitnessAnalyzedState(
            random_state, fitness_function.calc_fitness(random_state)
        )
        self._iterations_without_change = 0

        for _ in range(self._max_num_iterations):
            neighbors = local_search_space.get_neighbors(current_state.get_state())
            neighbor = self._get_random_neighbor(neighbors, fitness_function)
            if neighbor is None:
                break
            current_state = self._get_updated_state(
                all_bids,
                simple_linear_ordering,
                fitness_function,
                local_search_space,
                current_state,
                neighbor,
            )

        return current_state.get_state()

    def _get_random_neighbor(
        self, neighbors: set[Bid], fitness_analyzer: FitnessBid
    ) -> FitnessAnalyzedState | None:
        """Get a random neighbor with its fitness."""
        if not neighbors:
            return None
        neighbor = self._rand.choice(list(neighbors))
        return FitnessAnalyzedState(neighbor, fitness_analyzer.calc_fitness(neighbor))

    def _get_updated_state(
        self,
        all_bids: AllBidsList,
        simple_linear_ordering: SimpleLinearOrdering,
        fitness_function: FitnessBid,
        local_search_space: SearchSpaceBid,
        current_state: FitnessAnalyzedState,
        neighbor_state: FitnessAnalyzedState,
    ) -> FitnessAnalyzedState:
        """Get the next state based on comparison."""
        if neighbor_state.get_fitness() > current_state.get_fitness():
            self._iterations_without_change = 0
            return neighbor_state
        elif (
            self._iterations_without_change > self._max_iterations_without_change
            and current_state.get_fitness() == 0
        ):
            random_state = local_search_space.create_random_state(
                simple_linear_ordering, all_bids
            )
            self._iterations_without_change = 0
            return FitnessAnalyzedState(
                random_state, fitness_function.calc_fitness(random_state)
            )

        self._iterations_without_change += 1
        return current_state


class AgentP1DAMO(DefaultParty):
    """
    AgentP1DAMO - ANAC 2020 negotiation agent.

    AI-translated from Java.

    Uses hill climbing optimization with importance maps for bid selection
    and a time-dependent concession strategy.
    """

    def __init__(self, reporter: Reporter | None = None):
        """
        Initialize the agent.

        Args:
            reporter: Optional reporter for logging.
        """
        super().__init__(reporter)

        # Estimated profile and search components
        self._estimated_profile: SimpleLinearOrdering | None = None
        self._hill_climbing: HillClimbing | None = None
        self._imp_map: ImpMap | None = None
        self._opponent_imp_map: ImpMap | None = None

        # Threshold parameters
        self._offer_lower_ratio: float = 1.0
        self._offer_higher_ratio: float = 1.1
        self._max_importance: float = 0.0
        self._min_importance: float = 0.0
        self._median_importance: float = 0.0
        self._max_importance_bid: Bid | None = None
        self._min_importance_bid: Bid | None = None
        self._received_bid: Bid | None = None
        self._reservation_importance_ratio: float = 0.0
        self._offer_randomly: bool = True

        # Timing and opponent modeling
        self._start_time: float = 0.0
        self._max_oppo_bid_imp_for_me_got: bool = False
        self._max_oppo_bid_imp_for_me: float = 0.0
        self._estimated_nash_point: float = 0.0
        self._last_received_bid: Bid | None = None
        self._initial_time_pass: bool = False

        # GeniusWeb specific
        self._profile_interface: ProfileInterface | None = None
        self._me: PartyId | None = None
        self._progress: Progress | None = None
        self._last_received_action: Action | None = None
        self._rand = random.Random()
        self._allbids: AllBidsList | None = None
        self._settings: Settings | None = None
        self._fitness_function: FitnessBid | None = None
        self._local_search_space: SearchSpaceBid | None = None
        self._elicitation_cost: float = 0.01
        self._should_call: bool = True
        self._num_of_calling: float = 0
        self._is_linear_additive: bool = False

    def notifyChange(self, info: Inform) -> None:
        """
        Handle incoming information from the protocol.

        Args:
            info: The information received.
        """
        try:
            if isinstance(info, Settings):
                self._init(info)
            elif isinstance(info, ActionDone):
                self._last_received_action = info.getAction()
                if isinstance(self._last_received_action, Comparison):
                    comparison = self._last_received_action
                    if self._estimated_profile is not None:
                        self._estimated_profile = self._estimated_profile.with_bid(
                            comparison.getBid(), list(comparison.getWorse())
                        )
                        if self._imp_map is not None:
                            self._imp_map.self_update(self._estimated_profile.getBids())
                        self._allbids = AllBidsList(self._estimated_profile.getDomain())
                        action = self._choose_action()
                        self.getConnection().send(action)
                        if isinstance(self._progress, ProgressRounds):
                            self._progress = self._progress.advance()
                if isinstance(self._last_received_action, Offer):
                    self._received_bid = self._last_received_action.getBid()
            elif isinstance(info, YourTurn):
                action = self._choose_action()
                self.getConnection().send(action)
                if isinstance(self._progress, ProgressRounds):
                    self._progress = self._progress.advance()
            elif isinstance(info, Finished):
                self.getReporter().log(logging.INFO, f"Final outcome: {info}")
        except Exception as e:
            raise RuntimeError(f"Failed to handle info: {e}") from e

    def getCapabilities(self) -> Capabilities:
        """
        Return agent capabilities.

        Returns:
            Capabilities indicating SHAOP protocol support.
        """
        return Capabilities(
            {"SAOP", "SHAOP"},
            {
                "geniusweb.profile.Profile",
                "geniusweb.profile.utilityspace.LinearAdditive",
            },
        )

    def getDescription(self) -> str:
        """
        Return agent description.

        Returns:
            Description string.
        """
        return "ANAC 2020 - AgentP1DAMO (AI-translated from Java)"

    def _init(self, info: Settings) -> None:
        """
        Initialize the agent with settings.

        Args:
            info: The settings information.
        """
        self._should_call = True
        self._num_of_calling = 0
        self._settings = info
        self._me = info.getID()
        self._progress = info.getProgress()

        self._profile_interface = ProfileConnectionFactory.create(
            info.getProfile().getURI(), self.getReporter()
        )

        # Get elicitation cost
        cost = info.getParameters().get("elicitationcost")
        if isinstance(cost, float):
            self._elicitation_cost = cost
        else:
            self._elicitation_cost = 0.01

        partial_profile = self._profile_interface.getProfile()
        # Accept both LinearAdditive and PartialOrdering profiles
        if not isinstance(partial_profile, (PartialOrdering, LinearAdditive)):
            raise ValueError("Profile must be a PartialOrdering or LinearAdditive")

        # Flag to track if we're using LinearAdditive (no elicitation support)
        self._is_linear_additive = isinstance(partial_profile, LinearAdditive)

        self._allbids = AllBidsList(partial_profile.getDomain())

        if self._estimated_profile is None:
            try:
                self._estimated_profile = SimpleLinearOrdering.from_profile(
                    self._profile_interface.getProfile()
                )
            except Exception as e:
                self.getReporter().log(logging.WARNING, f"Error creating profile: {e}")
                self._estimated_profile = SimpleLinearOrdering(
                    partial_profile.getDomain(), []
                )

        self._hill_climbing = HillClimbing(2, 1, self._rand.randint(0, 2**31))
        self._fitness_function = FitnessBid(self._estimated_profile)
        self._local_search_space = SearchSpaceBid(self._get_bids(), 2)

        self._imp_map = ImpMap(partial_profile)
        self._opponent_imp_map = ImpMap(partial_profile)

        # Get sorted bids from profile
        try:
            ordered_bids = SimpleLinearOrdering.from_profile(
                self._profile_interface.getProfile()
            ).getBids()
        except Exception:
            ordered_bids = []

        # Update importance map
        if ordered_bids:
            self._imp_map.self_update(ordered_bids)

        # Get max, min, and median bids
        self._get_max_and_min_bid()
        self._get_median_bid(ordered_bids)

        # Get reservation ratio
        self._reservation_importance_ratio = self._get_reservation_ratio()

        self.getReporter().log(
            logging.INFO, f"reservation ratio: {self._reservation_importance_ratio}"
        )
        self.getReporter().log(
            logging.INFO, f"my max importance bid: {self._max_importance_bid}"
        )
        self.getReporter().log(
            logging.INFO, f"my max importance: {self._max_importance}"
        )
        self.getReporter().log(
            logging.INFO, f"my min importance bid: {self._min_importance_bid}"
        )
        self.getReporter().log(
            logging.INFO, f"my min importance: {self._min_importance}"
        )
        self.getReporter().log(
            logging.INFO, f"my median importance: {self._median_importance}"
        )
        self.getReporter().log(
            logging.INFO, f"Party {self._me} has finished initialization"
        )

    def _choose_action(self) -> Action:
        """
        Choose the next action.

        Returns:
            The action to perform.
        """
        if self._progress is None or self._me is None:
            raise RuntimeError("Agent not initialized")

        time = self._progress.get(int(round(self._get_current_time_ms())))

        # Start competition
        if not isinstance(self._last_received_action, Offer):
            return Offer(self._me, self._max_importance_bid)

        if self._received_bid is None or self._imp_map is None:
            return Offer(self._me, self._max_importance_bid)

        # Calculate importance ratio for received bid
        importance_range = self._max_importance - self._min_importance
        if importance_range > 0:
            imp_ratio_for_me = (
                self._imp_map.get_importance(self._received_bid) - self._min_importance
            ) / importance_range
        else:
            imp_ratio_for_me = 0.0

        # Accept if above threshold
        if imp_ratio_for_me >= self._offer_lower_ratio:
            self.getReporter().log(logging.INFO, f"\n\naccepted agent: Agent{self._me}")
            self.getReporter().log(logging.INFO, f"last bid: {self._received_bid}")
            self.getReporter().log(
                logging.INFO, f"\ncurrent threshold: {self._offer_lower_ratio}"
            )
            self.getReporter().log(logging.INFO, "\n\n")
            return Accept(self._me, self._received_bid)

        # Get max opponent bid importance for me
        if not self._max_oppo_bid_imp_for_me_got:
            self._get_max_oppo_bid_imp_for_me(time, 3.0 / 1000.0)

        # Update opponent importance table
        if time < 0.3 and self._opponent_imp_map is not None:
            self._opponent_imp_map.opponent_update(self._received_bid)

        # Strategy
        self._get_threshold(time)

        # Last round
        if time >= 0.9989 and importance_range > 0:
            ratio = (
                self._imp_map.get_importance(self._received_bid) - self._min_importance
            ) / importance_range
            if ratio > self._reservation_importance_ratio + 0.2:
                return Accept(self._me, self._received_bid)

        self.getReporter().log(
            logging.INFO, f"high threshold: {self._offer_higher_ratio}"
        )
        self.getReporter().log(
            logging.INFO, f"low threshold: {self._offer_lower_ratio}"
        )
        self.getReporter().log(
            logging.INFO, f"estimated nash: {self._estimated_nash_point}"
        )
        self.getReporter().log(
            logging.INFO, f"reservation: {self._reservation_importance_ratio}"
        )

        if self._should_call_elicitation(time):
            if (
                self._last_received_bid is not None
                and self._estimated_profile is not None
            ):
                return ElicitComparison(
                    self._me,
                    self._last_received_bid,
                    self._estimated_profile.getBids(),
                )

        bid = self._get_optimize_bid()
        self._last_received_bid = self._received_bid
        return Offer(self._me, bid)

    def _should_call_elicitation(self, time: float) -> bool:
        """
        Determine if elicitation should be called.

        Args:
            time: Current negotiation time (0-1).

        Returns:
            True if elicitation should be called.
        """
        # Don't call elicitation for LinearAdditive profiles (no partial ordering)
        if self._is_linear_additive:
            return False

        if self._num_of_calling < 10 or self._rand.random() < math.exp(
            -self._elicitation_cost
        ):
            self._num_of_calling += 1
            return self._rand.random() < math.exp(-time)
        return False

    def _get_max_oppo_bid_imp_for_me(self, time: float, time_last: float) -> None:
        """
        Get the maximum opponent bid importance for me.

        Used to estimate the Pareto frontier.

        Args:
            time: Current time.
            time_last: Duration to consider.
        """
        if self._received_bid is None or self._imp_map is None:
            return

        this_bid_imp = self._imp_map.get_importance(self._received_bid)
        if this_bid_imp > self._max_oppo_bid_imp_for_me:
            self._max_oppo_bid_imp_for_me = this_bid_imp

        if self._initial_time_pass:
            if time - self._start_time > time_last:
                importance_range = self._max_importance - self._min_importance
                if importance_range > 0:
                    max_oppo_bid_ratio_for_me = (
                        self._max_oppo_bid_imp_for_me - self._min_importance
                    ) / importance_range
                else:
                    max_oppo_bid_ratio_for_me = 0.0
                # 1.414 is circle, 2 is line
                self._estimated_nash_point = (
                    1 - max_oppo_bid_ratio_for_me
                ) / 1.7 + max_oppo_bid_ratio_for_me
                self._max_oppo_bid_imp_for_me_got = True
        else:
            if self._last_received_bid != self._received_bid:
                self._initial_time_pass = True
                self._start_time = time

    def _get_threshold(self, time: float) -> None:
        """
        Get upper and lower thresholds based on time.

        Args:
            time: Current negotiation time (0-1).
        """
        if time < 0.01:
            # First 10 rounds at 0.9999
            self._offer_lower_ratio = 0.9999
        elif time < 0.02:
            # 10-20 rounds at 0.99
            self._offer_lower_ratio = 0.99
        elif time < 0.2:
            # 20-200 rounds, drop to 0.9
            self._offer_lower_ratio = 0.99 - 0.5 * (time - 0.02)
        elif time < 0.5:
            self._offer_randomly = False
            # 200-500 rounds, gradually reduce to estimated Nash point
            p2 = 0.3 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            self._offer_lower_ratio = 0.9 - (0.9 - p2) / (0.5 - 0.2) * (time - 0.2)
        elif time < 0.9:
            # 500-900 rounds
            p1 = 0.3 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            p2 = 0.15 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            self._offer_lower_ratio = p1 - (p1 - p2) / (0.9 - 0.5) * (time - 0.5)
        elif time < 0.98:
            # Compromise 1
            p1 = 0.15 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            p2 = 0.05 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            possible_ratio = p1 - (p1 - p2) / (0.98 - 0.9) * (time - 0.9)
            self._offer_lower_ratio = max(
                possible_ratio, self._reservation_importance_ratio + 0.3
            )
        elif time < 0.995:
            # Compromise 2: 980-995 rounds
            p1 = 0.05 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            p2 = 0.0 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            possible_ratio = p1 - (p1 - p2) / (0.995 - 0.98) * (time - 0.98)
            self._offer_lower_ratio = max(
                possible_ratio, self._reservation_importance_ratio + 0.25
            )
        elif time < 0.999:
            # Compromise 3: 995-999 rounds
            p1 = 0.0 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            p2 = -0.35 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            possible_ratio = p1 - (p1 - p2) / (0.9989 - 0.995) * (time - 0.995)
            self._offer_lower_ratio = max(
                possible_ratio, self._reservation_importance_ratio + 0.25
            )
        else:
            possible_ratio = (
                -0.4 * (1 - self._estimated_nash_point) + self._estimated_nash_point
            )
            self._offer_lower_ratio = max(
                possible_ratio, self._reservation_importance_ratio + 0.2
            )

        self._offer_higher_ratio = self._offer_lower_ratio + 0.1

    def _get_reservation_ratio(self) -> float:
        """
        Get the reservation ratio.

        Returns:
            The reservation importance ratio.
        """
        if self._profile_interface is None or self._imp_map is None:
            return 0.1

        importance_range = self._max_importance - self._min_importance
        if importance_range == 0:
            return 0.1

        median_bid_ratio = (
            self._median_importance - self._min_importance
        ) / importance_range

        try:
            profile = self._profile_interface.getProfile()
            res_bid = profile.getReservationBid()
            res_value = 0.1
            if res_bid is not None:
                res_value = self._imp_map.get_importance(res_bid)
            return res_value * median_bid_ratio / 0.5
        except Exception:
            return 0.1

    def _get_max_and_min_bid(self) -> None:
        """Calculate maximum and minimum importance bids."""
        if self._imp_map is None:
            return

        l_values1: dict[str, Value] = {}
        l_values2: dict[str, Value] = {}

        for issue, imp_units in self._imp_map.items():
            if imp_units:
                # First value has highest importance (sorted descending)
                value1 = imp_units[0].value_of_issue
                # Last value has lowest importance
                value2 = imp_units[-1].value_of_issue
                l_values1[issue] = value1
                l_values2[issue] = value2

        self._max_importance_bid = Bid(l_values1)
        self._min_importance_bid = Bid(l_values2)
        self._max_importance = self._imp_map.get_importance(self._max_importance_bid)
        self._min_importance = self._imp_map.get_importance(self._min_importance_bid)

    def _get_median_bid(self, ordered_bids: list[Bid]) -> None:
        """
        Get the median bid importance.

        Args:
            ordered_bids: List of bids ordered from low to high utility.
        """
        if not ordered_bids or self._imp_map is None:
            self._median_importance = 0.0
            return

        median = (len(ordered_bids) - 1) // 2
        median2 = -1
        if len(ordered_bids) % 2 == 0:
            median2 = median + 1

        current = 0
        for bid in ordered_bids:
            current += 1
            if current == median:
                self._median_importance = self._imp_map.get_importance(bid)
                if median2 == -1:
                    break
            if current == median2:
                self._median_importance += self._imp_map.get_importance(bid)
                break

        if median2 != -1:
            self._median_importance /= 2

    def _get_optimize_bid(self) -> Bid:
        """
        Get an optimized bid using hill climbing.

        Returns:
            The optimized bid.
        """
        if (
            self._hill_climbing is None
            or self._fitness_function is None
            or self._local_search_space is None
            or self._estimated_profile is None
            or self._allbids is None
        ):
            # Fallback to max importance bid
            return self._max_importance_bid if self._max_importance_bid else Bid({})

        return self._hill_climbing.search(
            self._fitness_function,
            self._local_search_space,
            self._estimated_profile,
            self._allbids,
        )

    def _get_bids(self) -> list[Bid]:
        """
        Get all bids from the bid space.

        Returns:
            List of all possible bids.
        """
        if self._allbids is None:
            return []
        return [self._allbids.get(i) for i in range(int(self._allbids.size()))]

    def _get_current_time_ms(self) -> float:
        """Get current time in milliseconds."""
        import time

        return time.time() * 1000
