"""
AhBuNeAgent - A negotiation agent using similarity-based bidding strategy.

AI-translated from Java (ANAC 2020 competition).

Original strategy:
- Uses similarity maps to estimate bid utilities
- Maintains linear orderings for both own and opponent preferences
- Time-dependent concession strategy with elicitation support
- Supports SHAOP and SAOP protocols
"""

from __future__ import annotations

import logging
import math
import random
from collections import OrderedDict
from decimal import Decimal
from typing import TYPE_CHECKING

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Comparison import Comparison
from geniusweb.actions.ElicitComparison import ElicitComparison
from geniusweb.actions.EndNegotiation import EndNegotiation
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
from geniusweb.profile.PartialOrdering import PartialOrdering
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


class IssueValueUnit:
    """Unit for tracking importance of issue values."""

    def __init__(self, value: Value):
        """
        Initialize the issue value unit.

        Args:
            value: The value for this unit.
        """
        self.value_of_issue: Value = value
        self.importance_list: list[float] = []


class OppIssueValueUnit:
    """Unit for tracking opponent's importance of issue values."""

    def __init__(self, value: Value):
        """
        Initialize the opponent issue value unit.

        Args:
            value: The value for this unit.
        """
        self.value_of_issue: Value = value
        self.importance_list: list[float] = []


class SimpleLinearOrdering:
    """
    A simple list of bids ordered from worst to best.

    All bids are fully ordered (better or worse than other bids in the list).
    """

    def __init__(self, domain: Domain, bids: list[Bid] | None = None):
        """
        Initialize the linear ordering.

        Args:
            domain: The negotiation domain.
            bids: Initial list of bids (worst first, best last).
        """
        self._domain = domain
        self._bids: list[Bid] = list(bids) if bids else []

    @classmethod
    def from_profile(cls, profile: PartialOrdering) -> SimpleLinearOrdering:
        """
        Create ordering from a profile.

        Args:
            profile: The partial ordering profile or LinearAdditive profile.

        Returns:
            A new SimpleLinearOrdering.
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
            # Sort ascending: worse bids first, better bids last
            bids_list.sort(
                key=lambda b1: 1 if profile.isPreferredOrEqual(b1, bids_list[0]) else -1
            )
            # More precise sorting
            bids_list.sort(
                key=lambda b: sum(
                    1 for other in bids_list if profile.isPreferredOrEqual(b, other)
                )
            )
            return cls(domain, bids_list)
        else:
            raise ValueError(f"Unsupported profile type: {type(profile)}")

    def get_min_bid(self) -> Bid | None:
        """Get the lowest utility bid."""
        return self._bids[0] if self._bids else None

    def get_max_bid(self) -> Bid | None:
        """Get the highest utility bid."""
        return self._bids[-1] if self._bids else None

    def get_bid_by_index(self, index: int) -> Bid | None:
        """Get bid at a specific index."""
        return self._bids[index] if index < len(self._bids) else None

    def get_known_bids_size(self) -> int:
        """Get the number of known bids."""
        return len(self._bids)

    def get_utility(self, bid: Bid) -> Decimal:
        """Get the utility of a bid (based on position)."""
        if bid not in self._bids:
            return Decimal(0)
        return Decimal(self._bids.index(bid) + 1)

    def contains(self, bid: Bid) -> bool:
        """Check if bid is in the ordering."""
        return bid in self._bids

    def get_bids(self) -> list[Bid]:
        """Get an unmodifiable view of the bids."""
        return list(self._bids)

    def with_comparison(self, bid: Bid, worse_bids: list[Bid]) -> SimpleLinearOrdering:
        """
        Create new ordering with an additional bid.

        Args:
            bid: The bid to add.
            worse_bids: Bids that are worse than this bid.

        Returns:
            A new SimpleLinearOrdering with the bid inserted.
        """
        n = 0
        while n < len(self._bids) and self._bids[n] in worse_bids:
            n += 1
        new_bids = list(self._bids)
        new_bids.insert(n, bid)
        return SimpleLinearOrdering(self._domain, new_bids)


class OppSimpleLinearOrdering:
    """
    A simple ordering for opponent bids.

    Tracks opponent's bid history to estimate their preferences.
    """

    def __init__(self):
        """Initialize the opponent ordering."""
        self._bids: list[Bid] = []

    def get_utility(self, bid: Bid) -> Decimal:
        """Get the utility of a bid (based on position)."""
        if bid not in self._bids:
            return Decimal(0)
        return Decimal(self._bids.index(bid) + 1)

    def get_max_bid(self) -> Bid | None:
        """Get the highest utility bid (most important for opponent)."""
        return self._bids[-1] if self._bids else None

    def get_known_bids_size(self) -> int:
        """Get the number of known bids."""
        return len(self._bids)

    def is_available(self) -> bool:
        """Check if enough data is available for predictions."""
        return len(self._bids) >= 6

    def contains(self, bid: Bid) -> bool:
        """Check if bid is in the ordering."""
        return bid in self._bids

    def get_bids(self) -> list[Bid]:
        """Get an unmodifiable view of the bids."""
        return list(self._bids)

    def get_bid_by_index(self, index: int) -> Bid | None:
        """Get bid at a specific index."""
        return self._bids[index] if index < len(self._bids) else None

    def update_bid(self, bid: Bid) -> None:
        """
        Update the ordering with a new bid.

        Bids that are offered first are considered more important.
        """
        if not self.contains(bid):
            # Add at the beginning - first offers are most important
            self._bids.insert(0, bid)


class SimilarityMap:
    """Map for tracking similarity of bid values to estimate utilities."""

    def __init__(self, domain: Domain):
        """
        Initialize the similarity map.

        Args:
            domain: The negotiation domain.
        """
        self._domain = domain
        self._issue_list: list[str] = list(domain.getIssues())
        self._issue_value_imp_map: dict[str, list[IssueValueUnit]] = {}
        self._issue_imp_map: dict[str, float] = {}
        self._estimated_profile: SimpleLinearOrdering | None = None
        self._max_imp_bid: Bid | None = None
        self._min_imp_bid: Bid | None = None
        self._available_values: dict[str, list[Value]] = {}
        self._forbidden_values: dict[str, list[Value]] = {}
        self._random = random.Random()
        self._sorted_issue_imp_map: OrderedDict[str, float] = OrderedDict()
        self._renew_maps()

    def _renew_maps(self) -> None:
        """Reset the importance maps."""
        self._issue_value_imp_map = {}
        self._issue_imp_map = {}
        for issue in self._domain.getIssues():
            self._issue_imp_map[issue] = 0.0
            values = self._domain.getValues(issue)
            issue_value_units: list[IssueValueUnit] = []
            for value in values:
                issue_value_units.append(IssueValueUnit(value))
            self._issue_value_imp_map[issue] = issue_value_units

    def _renew_lists(self) -> None:
        """Reset the available/forbidden value lists."""
        self._available_values = {}
        self._forbidden_values = {}
        for issue in self._domain.getIssues():
            self._available_values[issue] = []
            self._forbidden_values[issue] = []

    def _create_condition_lists(self, num_first_bids: int, num_last_bids: int) -> None:
        """
        Create lists of available and forbidden values.

        Args:
            num_first_bids: Number of best bids to consider.
            num_last_bids: Number of worst bids to consider.
        """
        self._renew_lists()
        if self._estimated_profile is None:
            return

        sorted_bids = self._estimated_profile.get_bids()
        first_start_index = (len(sorted_bids) - 1) - num_first_bids
        if first_start_index <= 0:
            first_start_index = 1

        # Add values from best bids to available
        for bid_index in range(first_start_index, len(sorted_bids)):
            current_bid = sorted_bids[bid_index]
            for issue in current_bid.getIssues():
                current_issue_list = self._issue_value_imp_map.get(issue, [])
                for current_unit in current_issue_list:
                    if current_unit.value_of_issue == current_bid.getValue(issue):
                        if (
                            current_bid.getValue(issue)
                            not in self._available_values[issue]
                        ):
                            self._available_values[issue].append(
                                current_bid.getValue(issue)
                            )
                        break

        # Add values from worst bids to forbidden
        if num_last_bids >= len(sorted_bids):
            num_last_bids = len(sorted_bids) - 1

        for bid_index in range(num_last_bids):
            current_bid = sorted_bids[bid_index]
            for issue in current_bid.getIssues():
                current_issue_list = self._issue_value_imp_map.get(issue, [])
                for current_unit in current_issue_list:
                    if current_unit.value_of_issue == current_bid.getValue(issue):
                        bid_value = current_bid.getValue(issue)
                        if (
                            bid_value not in self._forbidden_values[issue]
                            and bid_value not in self._available_values[issue]
                        ):
                            self._forbidden_values[issue].append(bid_value)
                        break

    def is_compatible_with_similarity(
        self, bid: Bid, num_first_bids: int, num_last_bids: int, min_utility: float
    ) -> bool:
        """
        Check if a bid is compatible with the desired utility.

        Args:
            bid: The bid to check.
            num_first_bids: Number of best bids to consider.
            num_last_bids: Number of worst bids to consider.
            min_utility: Minimum utility threshold.

        Returns:
            True if the bid is compatible.
        """
        self._create_condition_lists(num_first_bids, num_last_bids)
        if self._max_imp_bid is None:
            return False

        issue_change_loss = 1.0 / len(self._domain.getIssues())
        change_rest = int((1 - min_utility) / issue_change_loss) + 1
        if change_rest > len(self._domain.getIssues()):
            change_rest = len(self._domain.getIssues())

        changed_issue_best = 0
        changed_issue_worst = 0
        changed_not_available = 0

        sorted_issue_arr_list = list(self._sorted_issue_imp_map.items())

        for i, (issue, _) in enumerate(sorted_issue_arr_list):
            all_availables_forbidden = True
            for issue_value in self._available_values.get(issue, []):
                if issue_value not in self._forbidden_values.get(issue, []):
                    all_availables_forbidden = False

            available_issue_value_list = self._available_values.get(issue, [])
            max_bid_value = self._max_imp_bid.getValue(issue)

            if max_bid_value != bid.getValue(issue):
                if not all_availables_forbidden and bid.getValue(
                    issue
                ) in self._forbidden_values.get(issue, []):
                    return False
                if bid.getValue(issue) not in available_issue_value_list:
                    changed_not_available += 1
                elif i < (len(sorted_issue_arr_list) + 1) // 2:
                    changed_issue_worst += 1
                else:
                    changed_issue_best += 1

        change_rest_best = change_rest // 2
        change_rest_worst = (change_rest // 2) + (change_rest % 2)
        changed_issue_best += changed_not_available
        changed_issue_worst += changed_not_available

        exceed_best_bid_num = changed_issue_best - change_rest_best
        if exceed_best_bid_num > 0:
            equivalent_worst_bid_num = exceed_best_bid_num * 2
            changed_issue_best -= exceed_best_bid_num
            changed_issue_worst += equivalent_worst_bid_num

        exceed_worst_bid_num = changed_issue_worst - change_rest_worst
        if exceed_worst_bid_num > 0:
            equivalent_best_bid_num = (exceed_worst_bid_num + 1) // 2
            changed_issue_worst -= exceed_worst_bid_num
            changed_issue_best += equivalent_best_bid_num

        return (
            changed_issue_best <= change_rest_best
            and changed_issue_worst <= change_rest_worst
        )

    def find_bid_compatible_with_similarity(
        self,
        num_first_bids: int,
        num_last_bids: int,
        min_utility: float,
        opp_max_bid: Bid | None,
    ) -> Bid:
        """
        Find a bid compatible with the desired utility.

        Args:
            num_first_bids: Number of best bids to consider.
            num_last_bids: Number of worst bids to consider.
            min_utility: Minimum utility threshold.
            opp_max_bid: Opponent's maximum utility bid.

        Returns:
            A compatible bid.
        """
        self._create_condition_lists(num_first_bids, num_last_bids)

        issue_change_loss = 1.0 / len(self._domain.getIssues())
        change_rest = int((1 - min_utility) / issue_change_loss) + 1

        if change_rest > len(self._domain.getIssues()):
            change_rest = len(self._domain.getIssues())

        change_rest_best = change_rest // 2
        change_rest_worst = (change_rest // 2) + (change_rest % 2)

        sorted_issue_arr_list = list(self._sorted_issue_imp_map.items())

        created_bid: dict[str, Value] = {}
        for issue, _ in sorted_issue_arr_list:
            if self._max_imp_bid is not None:
                max_value = self._max_imp_bid.getValue(issue)
                if max_value is not None:
                    created_bid[issue] = max_value

        select_opp_value_count = 0
        while not (change_rest_worst == 0 and change_rest_best == 0):
            not_available_chance = min(change_rest_worst, change_rest_best)
            best_issue_start_index = (len(sorted_issue_arr_list) + 1) // 2
            rand_issue = self._random.randint(0, len(sorted_issue_arr_list) - 1)

            if (rand_issue < best_issue_start_index and change_rest_worst != 0) or (
                rand_issue >= best_issue_start_index and change_rest_best != 0
            ):
                issue = sorted_issue_arr_list[rand_issue][0]

                all_availables_forbidden = True
                for issue_value in self._available_values.get(issue, []):
                    if issue_value not in self._forbidden_values.get(issue, []):
                        all_availables_forbidden = False

                available_issue_value_list = self._available_values.get(issue, [])
                forbidden_issue_value_list = self._forbidden_values.get(issue, [])
                all_issue_values = self._issue_value_imp_map.get(issue, [])

                if not all_issue_values:
                    continue

                rand_issue_value_index = self._random.randint(
                    0, len(all_issue_values) - 1
                )
                if select_opp_value_count < 500 and opp_max_bid is not None:
                    random_issue_value = opp_max_bid.getValue(issue)
                    select_opp_value_count += 1
                else:
                    random_issue_value = all_issue_values[
                        rand_issue_value_index
                    ].value_of_issue

                if not all_availables_forbidden:
                    while random_issue_value in forbidden_issue_value_list:
                        rand_issue_value_index = self._random.randint(
                            0, len(all_issue_values) - 1
                        )
                        random_issue_value = all_issue_values[
                            rand_issue_value_index
                        ].value_of_issue

                select_value = False

                if random_issue_value not in available_issue_value_list:
                    if not_available_chance != 0:
                        change_rest_worst -= 1
                        change_rest_best -= 1
                        select_value = True
                elif rand_issue < best_issue_start_index:
                    if change_rest_worst != 0:
                        change_rest_worst -= 1
                        select_value = True
                elif change_rest_best != 0:
                    change_rest_best -= 1
                    select_value = True

                if select_value and random_issue_value is not None:
                    created_bid[issue] = random_issue_value

        return Bid(created_bid)

    def update(self, estimated_profile: SimpleLinearOrdering) -> None:
        """
        Update the similarity map with a new profile estimation.

        Args:
            estimated_profile: The estimated profile ordering.
        """
        self._renew_maps()
        self._estimated_profile = estimated_profile
        sorted_bids = estimated_profile.get_bids()

        if not sorted_bids:
            return

        self._max_imp_bid = sorted_bids[-1]
        self._min_imp_bid = sorted_bids[0]

        for bid_index, current_bid in enumerate(sorted_bids):
            bid_importance = float(estimated_profile.get_utility(current_bid))
            for issue in current_bid.getIssues():
                current_issue_list = self._issue_value_imp_map.get(issue, [])
                for current_unit in current_issue_list:
                    if current_unit.value_of_issue == current_bid.getValue(issue):
                        current_unit.importance_list.append(bid_importance)
                        break

        for issue in self._issue_imp_map.keys():
            issue_val_avg_list: list[float] = []
            current_issue_list = self._issue_value_imp_map.get(issue, [])
            for current_unit in current_issue_list:
                if current_unit.importance_list:
                    issue_value_avg = sum(current_unit.importance_list) / len(
                        current_unit.importance_list
                    )
                    issue_val_avg_list.append(issue_value_avg)
            self._issue_imp_map[issue] = self._stdev(issue_val_avg_list)

        self._sorted_issue_imp_map = self._sort_by_value(self._issue_imp_map)

    @staticmethod
    def _stdev(arr: list[float]) -> float:
        """Calculate standard deviation."""
        if not arr:
            return 0.0
        mean = sum(arr) / len(arr)
        variance = sum((val - mean) ** 2 for val in arr) / len(arr)
        return math.sqrt(variance)

    @staticmethod
    def _sort_by_value(hm: dict[str, float]) -> OrderedDict[str, float]:
        """Sort a dictionary by value."""
        sorted_items = sorted(hm.items(), key=lambda x: x[1])
        return OrderedDict(sorted_items)


class OppSimilarityMap:
    """Map for tracking opponent's bid similarity."""

    def __init__(self, domain: Domain):
        """
        Initialize the opponent similarity map.

        Args:
            domain: The negotiation domain.
        """
        self._domain = domain
        self._issue_list: list[str] = list(domain.getIssues())
        self._opp_issue_value_imp_map: dict[str, list[OppIssueValueUnit]] = {}
        self._opp_estimated_profile: OppSimpleLinearOrdering | None = None
        self._max_imp_bid: Bid | None = None
        self._available_values: dict[str, list[Value]] = {}
        self._renew_maps()

    def _renew_maps(self) -> None:
        """Reset the importance maps."""
        self._opp_issue_value_imp_map = {}
        for issue in self._domain.getIssues():
            values = self._domain.getValues(issue)
            issue_value_units: list[OppIssueValueUnit] = []
            for value in values:
                issue_value_units.append(OppIssueValueUnit(value))
            self._opp_issue_value_imp_map[issue] = issue_value_units

    def _renew_lists(self) -> None:
        """Reset the available value lists."""
        self._available_values = {}
        for issue in self._domain.getIssues():
            self._available_values[issue] = []

    def _create_condition_lists(self, num_first_bids: int) -> None:
        """
        Create lists of available values.

        Args:
            num_first_bids: Number of best bids to consider.
        """
        self._renew_lists()
        if self._opp_estimated_profile is None:
            return

        sorted_bids = self._opp_estimated_profile.get_bids()
        first_start_index = (len(sorted_bids) - 1) - num_first_bids
        if first_start_index <= 0:
            first_start_index = 0

        for bid_index in range(first_start_index, len(sorted_bids)):
            current_bid = sorted_bids[bid_index]
            for issue in current_bid.getIssues():
                current_issue_list = self._opp_issue_value_imp_map.get(issue, [])
                for current_unit in current_issue_list:
                    if current_unit.value_of_issue == current_bid.getValue(issue):
                        if (
                            current_bid.getValue(issue)
                            not in self._available_values[issue]
                        ):
                            self._available_values[issue].append(
                                current_bid.getValue(issue)
                            )
                        break

    def is_compromised(self, bid: Bid, num_first_bids: int, min_utility: float) -> bool:
        """
        Check if a bid represents a compromise for the opponent.

        Args:
            bid: The bid to check.
            num_first_bids: Number of best bids to consider.
            min_utility: Minimum utility threshold.

        Returns:
            True if the bid is a compromise.
        """
        self._create_condition_lists(num_first_bids)
        if self._max_imp_bid is None:
            return False

        issue_change_loss = 1.0 / len(self._domain.getIssues())
        change_rest = int((1 - min_utility) / issue_change_loss) + 1
        if change_rest > len(self._issue_list):
            change_rest = len(self._issue_list)

        changed_issue = 0
        for issue in self._issue_list:
            available_issue_value_list = self._available_values.get(issue, [])
            max_bid_value = self._max_imp_bid.getValue(issue)
            if max_bid_value != bid.getValue(issue):
                if bid.getValue(issue) not in available_issue_value_list:
                    changed_issue += 2
                else:
                    changed_issue += 1

        return changed_issue > change_rest

    def update(self, estimated_profile: OppSimpleLinearOrdering) -> None:
        """
        Update the similarity map with opponent's profile.

        Args:
            estimated_profile: The opponent's estimated profile.
        """
        self._renew_maps()
        self._opp_estimated_profile = estimated_profile
        sorted_bids = estimated_profile.get_bids()
        self._max_imp_bid = estimated_profile.get_max_bid()

        for current_bid in sorted_bids:
            bid_importance = float(estimated_profile.get_utility(current_bid))
            for issue in current_bid.getIssues():
                current_issue_list = self._opp_issue_value_imp_map.get(issue, [])
                for current_unit in current_issue_list:
                    if current_unit.value_of_issue == current_bid.getValue(issue):
                        current_unit.importance_list.append(bid_importance)
                        break

    def most_compromised_bids(self) -> OrderedDict[Bid, int]:
        """
        Get bids sorted by compromise level.

        Returns:
            Ordered dict of bids and their compromise counts.
        """
        if self._opp_estimated_profile is None:
            return OrderedDict()

        ordered_bids = self._opp_estimated_profile.get_bids()
        if not ordered_bids:
            return OrderedDict()

        max_util_bid = ordered_bids[-1]
        list_of_opponent_compromised: dict[Bid, int] = {}

        for test_bid in ordered_bids:
            compromise_count = 0
            for issue in self._domain.getIssues():
                if max_util_bid.getValue(issue) != test_bid.getValue(issue):
                    compromise_count += 1
            list_of_opponent_compromised[test_bid] = compromise_count

        sorted_items = sorted(list_of_opponent_compromised.items(), key=lambda x: x[1])
        return OrderedDict(sorted_items)


class AhBuNeAgent(DefaultParty):
    """
    AhBuNeAgent - A negotiation agent using similarity-based bidding.

    AI-translated from Java (ANAC 2020).

    Strategy:
    - Uses similarity maps to estimate own and opponent bid utilities
    - Time-dependent concession with elicitation support
    - Supports both SHAOP and SAOP protocols
    """

    def __init__(self, reporter: Reporter | None = None):
        """
        Initialize the agent.

        Args:
            reporter: Optional reporter for logging.
        """
        super().__init__(reporter)
        self._random = random.Random()

        self._our_num_first_bids: int = 0
        self._our_num_last_bids: int = 0
        self._opp_num_first_bids: int = 0
        self._our_known_bid_num: int = 0
        self._opp_known_bid_num: int = 0

        self._profile_interface: ProfileInterface | None = None
        self._party_id: PartyId | None = None
        self._progress: Progress | None = None
        self._time: float = 0.0

        self._all_possible_bids: AllBidsList | None = None
        self._all_possible_bids_size: int = 0
        self._our_linear_partial_ordering: SimpleLinearOrdering | None = None
        self._opp_linear_partial_ordering: OppSimpleLinearOrdering | None = None
        self._our_similarity_map: SimilarityMap | None = None
        self._opp_similarity_map: OppSimilarityMap | None = None

        self._last_received_bid: Bid | None = None
        self._utility_lower_bound: float = 1.0
        self._our_max_compromise: float = 0.1

        # Elicitation tracking
        self._lost_elicit_score: float = 0.0
        self._elicitation_cost: float = 0.01
        self._max_elicitation_lost: Decimal = Decimal("0.05")
        self._left_elicitation_number: int = 0
        self._elicitation_bid: Bid | None = None
        self._most_compromised_bids: list[tuple[Bid, int]] = []
        self._opp_elicitated_bid: list[Bid] = []
        self._reservation_bid: Bid | None = None

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SHAOP", "SAOP"},
            {
                "geniusweb.profile.PartialOrdering",
                "geniusweb.profile.utilityspace.LinearAdditive",
            },
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return "AhBuNe Agent (AI-translated from Java)"

    def notifyChange(self, info: Inform) -> None:
        """
        Handle incoming information from the negotiation protocol.

        Args:
            info: The information received.
        """
        try:
            if isinstance(info, Settings):
                self._init(info)
            elif isinstance(info, ActionDone):
                last_received_action = info.getAction()
                if isinstance(last_received_action, Offer):
                    self._last_received_bid = last_received_action.getBid()
                elif isinstance(last_received_action, Comparison):
                    if self._our_linear_partial_ordering is not None:
                        self._our_linear_partial_ordering = (
                            self._our_linear_partial_ordering.with_comparison(
                                last_received_action.getBid(),
                                list(last_received_action.getWorse()),
                            )
                        )
                    self._my_turn()
            elif isinstance(info, YourTurn):
                if isinstance(self._progress, ProgressRounds):
                    self._progress = self._progress.advance()
                self._my_turn()
            elif isinstance(info, Finished):
                self.getReporter().log(logging.INFO, "Negotiation finished")
                self.terminate()
        except Exception as e:
            raise RuntimeError(f"Failed to handle info: {e}") from e

    def _init(self, settings: Settings) -> None:
        """
        Initialize the agent with settings.

        Args:
            settings: The negotiation settings.
        """
        self._party_id = settings.getID()
        self._progress = settings.getProgress()
        self._profile_interface = ProfileConnectionFactory.create(
            settings.getProfile().getURI(), self.getReporter()
        )

        profile = self._profile_interface.getProfile()

        if not isinstance(profile, PartialOrdering):
            raise ValueError("Only PartialOrdering is supported")

        partial_profile = profile
        self._all_possible_bids = AllBidsList(partial_profile.getDomain())
        self._all_possible_bids_size = int(self._all_possible_bids.size())
        self._our_similarity_map = SimilarityMap(partial_profile.getDomain())
        self._opp_similarity_map = OppSimilarityMap(partial_profile.getDomain())
        self._our_linear_partial_ordering = SimpleLinearOrdering.from_profile(
            partial_profile
        )
        self._opp_linear_partial_ordering = OppSimpleLinearOrdering()
        self._our_similarity_map.update(self._our_linear_partial_ordering)
        self._get_reservation_ratio()
        self._get_elicitation_cost(settings)

    def _select_action(self) -> Action:
        """Select the next action to take."""
        if self._do_we_make_elicitation():
            self._lost_elicit_score += self._elicitation_cost
            self._left_elicitation_number -= 1
            if self._our_linear_partial_ordering is not None:
                return ElicitComparison(
                    self._party_id,
                    self._elicitation_bid,
                    self._our_linear_partial_ordering.get_bids(),
                )

        if self._last_received_bid is None:
            return self._make_an_offer()

        if self._do_we_end_the_negotiation():
            return EndNegotiation(self._party_id)
        elif self._do_we_accept(self._last_received_bid):
            return Accept(self._party_id, self._last_received_bid)

        return self._make_an_offer()

    def _my_turn(self) -> None:
        """Execute the agent's turn."""
        if self._progress is not None:
            self._time = self._progress.get(
                int(1000 * random.random())
            )  # Simulating System.currentTimeMillis
        self._strategy_selection()
        action = self._select_action()
        self.getConnection().send(action)

    def _do_we_end_the_negotiation(self) -> bool:
        """Check if we should end the negotiation."""
        if (
            self._reservation_bid is not None
            and self._our_similarity_map is not None
            and self._our_similarity_map.is_compatible_with_similarity(
                self._reservation_bid,
                self._our_num_first_bids,
                self._our_num_last_bids,
                0.9 - self._time * 0.1,
            )
        ):
            return True
        return False

    def _elicitation_random_bid_generator(self) -> Bid:
        """Generate a random bid for elicitation."""
        if self._all_possible_bids is None or self._our_linear_partial_ordering is None:
            return Bid({})

        found_bid = self._all_possible_bids.get(
            self._random.randint(0, int(self._all_possible_bids.size()) - 1)
        )
        while self._our_linear_partial_ordering.contains(found_bid):
            found_bid = self._all_possible_bids.get(
                self._random.randint(0, int(self._all_possible_bids.size()) - 1)
            )
        return found_bid

    def _make_an_offer(self) -> Action:
        """Create an offer action."""
        if (
            self._our_linear_partial_ordering is None
            or self._our_similarity_map is None
        ):
            return Offer(self._party_id, Bid({}))

        if self._time > 0.96:
            for i in range(
                self._our_linear_partial_ordering.get_known_bids_size() - 1, -1, -1
            ):
                test_bid = self._our_linear_partial_ordering.get_bid_by_index(i)
                if (
                    test_bid is not None
                    and test_bid in self._opp_elicitated_bid
                    and self._do_we_accept(test_bid)
                ):
                    return Offer(self._party_id, test_bid)

        opp_max_bid = None
        if self._opp_linear_partial_ordering is not None:
            opp_max_bid = self._opp_linear_partial_ordering.get_max_bid()

        our_offer = self._our_similarity_map.find_bid_compatible_with_similarity(
            self._our_num_first_bids,
            self._our_num_last_bids,
            self._utility_lower_bound,
            opp_max_bid,
        )

        if self._time < 0.015:
            if (
                self._opp_linear_partial_ordering is not None
                and self._opp_linear_partial_ordering.is_available()
            ):
                count = 0
                while (
                    count < 500
                    and self._opp_similarity_map is not None
                    and not self._opp_similarity_map.is_compromised(
                        our_offer, self._opp_num_first_bids, 0.85
                    )
                    and our_offer == self._our_linear_partial_ordering.get_max_bid()
                ):
                    our_offer = (
                        self._our_similarity_map.find_bid_compatible_with_similarity(
                            self._our_num_first_bids,
                            self._our_num_last_bids,
                            0.85,
                            opp_max_bid,
                        )
                    )
                    count += 1
            else:
                count = 0
                while (
                    count < 500
                    and our_offer == self._our_linear_partial_ordering.get_max_bid()
                ):
                    our_offer = (
                        self._our_similarity_map.find_bid_compatible_with_similarity(
                            self._our_num_first_bids,
                            self._our_num_last_bids,
                            0.85,
                            opp_max_bid,
                        )
                    )
                    count += 1
        elif self._last_received_bid is not None:
            if self._our_similarity_map.is_compatible_with_similarity(
                self._last_received_bid,
                self._our_num_first_bids,
                self._our_num_last_bids,
                0.9,
            ):
                return Offer(self._party_id, self._last_received_bid)
            if (
                opp_max_bid is not None
                and self._our_similarity_map.is_compatible_with_similarity(
                    opp_max_bid, self._our_num_first_bids, self._our_num_last_bids, 0.9
                )
            ):
                return Offer(self._party_id, opp_max_bid)
            count = 0
            while (
                count < 500
                and self._opp_linear_partial_ordering is not None
                and self._opp_linear_partial_ordering.is_available()
                and self._opp_similarity_map is not None
                and not self._opp_similarity_map.is_compromised(
                    our_offer, self._opp_num_first_bids, self._utility_lower_bound
                )
            ):
                our_offer = (
                    self._our_similarity_map.find_bid_compatible_with_similarity(
                        self._our_num_first_bids,
                        self._our_num_last_bids,
                        self._utility_lower_bound,
                        opp_max_bid,
                    )
                )
                count += 1

        return Offer(self._party_id, our_offer)

    def _do_we_accept(self, bid: Bid) -> bool:
        """
        Check if we should accept a bid.

        Args:
            bid: The bid to evaluate.

        Returns:
            True if we should accept.
        """
        if self._our_similarity_map is None:
            return False

        if self._our_similarity_map.is_compatible_with_similarity(
            bid, self._our_num_first_bids, self._our_num_last_bids, 0.9
        ):
            return True

        start_utility_search = self._utility_lower_bound

        if self._time >= 0.98:
            start_utility_search = self._utility_lower_bound - self._our_max_compromise

        if (
            self._opp_linear_partial_ordering is not None
            and self._opp_linear_partial_ordering.is_available()
        ):
            for i in range(int(start_utility_search * 100), 96, 5):
                utility_test = i / 100.0
                if (
                    self._opp_similarity_map is not None
                    and self._opp_similarity_map.is_compromised(
                        bid, self._opp_num_first_bids, utility_test
                    )
                ):
                    if self._our_similarity_map.is_compatible_with_similarity(
                        bid,
                        self._our_num_first_bids,
                        self._our_num_last_bids,
                        utility_test,
                    ):
                        return True
                    break

        return False

    def _do_we_make_elicitation(self) -> bool:
        """Check if we should make an elicitation request."""
        if self._left_elicitation_number == 0:
            return False

        if self._our_linear_partial_ordering is None:
            return False

        if self._all_possible_bids_size <= 100:
            if (
                self._our_linear_partial_ordering.get_known_bids_size()
                < self._all_possible_bids_size * 0.1
            ):
                self._elicitation_bid = self._elicitation_random_bid_generator()
                return True
        elif self._our_linear_partial_ordering.get_known_bids_size() < 10:
            self._elicitation_bid = self._elicitation_random_bid_generator()
            return True
        elif (
            self._time > 0.98
            and self._opp_linear_partial_ordering is not None
            and self._opp_linear_partial_ordering.is_available()
        ):
            if self._most_compromised_bids:
                bid_entry = self._most_compromised_bids.pop()
                self._elicitation_bid = bid_entry[0]
                self._opp_elicitated_bid.append(self._elicitation_bid)
                return True
            else:
                if self._opp_similarity_map is not None:
                    most_compromised_bids_hash = (
                        self._opp_similarity_map.most_compromised_bids()
                    )
                    self._most_compromised_bids = list(
                        most_compromised_bids_hash.items()
                    )
                    if self._most_compromised_bids:
                        bid_entry = self._most_compromised_bids.pop()
                        self._elicitation_bid = bid_entry[0]
                        self._opp_elicitated_bid.append(self._elicitation_bid)
                        return True

        return False

    def _strategy_selection(self) -> None:
        """Update strategy parameters based on current state."""
        self._utility_lower_bound = self._get_utility_lower_bound(
            self._time, self._lost_elicit_score
        )

        if self._our_linear_partial_ordering is not None:
            self._our_known_bid_num = (
                self._our_linear_partial_ordering.get_known_bids_size()
            )
        if self._opp_linear_partial_ordering is not None:
            self._opp_known_bid_num = (
                self._opp_linear_partial_ordering.get_known_bids_size()
            )

        self._our_num_first_bids = self._get_num_first(
            self._utility_lower_bound, self._our_known_bid_num
        )
        self._our_num_last_bids = self._get_num_last(
            self._utility_lower_bound,
            self._get_utility_lower_bound(1.0, self._lost_elicit_score),
            self._our_known_bid_num,
        )

        if self._last_received_bid is not None:
            if self._opp_linear_partial_ordering is not None:
                self._opp_linear_partial_ordering.update_bid(self._last_received_bid)
            if (
                self._opp_similarity_map is not None
                and self._opp_linear_partial_ordering is not None
            ):
                self._opp_similarity_map.update(self._opp_linear_partial_ordering)
            self._opp_num_first_bids = self._get_opp_num_first(
                self._utility_lower_bound, self._opp_known_bid_num
            )

    def _get_elicitation_cost(self, settings: Settings) -> None:
        """Get the elicitation cost from settings."""
        try:
            params = settings.getParameters()
            cost_param = params.get("elicitationcost")
            if cost_param is not None:
                self._elicitation_cost = float(str(cost_param))
            self._left_elicitation_number = int(
                float(self._max_elicitation_lost) / self._elicitation_cost
            )
            self.getReporter().log(
                logging.INFO, f"leftElicitationNumber: {self._left_elicitation_number}"
            )
        except Exception:
            self._elicitation_cost = 0.01
            self._left_elicitation_number = int(
                float(self._max_elicitation_lost) / self._elicitation_cost
            )
            self.getReporter().log(
                logging.INFO,
                f"catch leftElicitationNumber: {self._left_elicitation_number}",
            )

    def _get_reservation_ratio(self) -> None:
        """Get the reservation bid from profile."""
        try:
            if self._profile_interface is not None:
                self._reservation_bid = (
                    self._profile_interface.getProfile().getReservationBid()
                )
        except Exception:
            self._reservation_bid = None

    def _get_utility_lower_bound(self, time: float, lost_elicit_score: float) -> float:
        """
        Calculate the utility lower bound based on time.

        Args:
            time: Current negotiation time (0-1).
            lost_elicit_score: Score lost to elicitation.

        Returns:
            The utility lower bound.
        """
        if time < 0.5:
            return -math.pow((time - 0.25), 2) + 0.9 + lost_elicit_score
        elif time < 0.7:
            return -math.pow((1.5 * (time - 0.7)), 2) + 0.9 + lost_elicit_score
        return (3.25 * time * time) - (6.155 * time) + 3.6105 + lost_elicit_score

    def _get_num_first(self, utility_lower_bound: float, known_bid_num: int) -> int:
        """Get the number of first (best) bids to consider."""
        return int(known_bid_num * (1 - utility_lower_bound)) + 1

    def _get_num_last(
        self,
        utility_lower_bound: float,
        min_utility_lower_bound: float,
        our_known_bid_num: int,
    ) -> int:
        """Get the number of last (worst) bids to consider."""
        return (
            int(our_known_bid_num * (1 - min_utility_lower_bound))
            - int(our_known_bid_num * (1 - utility_lower_bound))
            + 1
        )

    def _get_opp_num_first(
        self, utility_lower_bound: float, opp_known_bid_num: int
    ) -> int:
        """Get the number of first opponent bids to consider."""
        return int(opp_known_bid_num * (1 - utility_lower_bound)) + 1
