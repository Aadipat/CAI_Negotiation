"""
NiceAgent - A negotiation agent with preference elicitation for SHAOP protocol.

AI-translated from Java.

Original: ANAC 2020 competition agent.

The agent uses:
- Preference elicitation to learn issue and value importance
- A "mirroring" strategy to offer bids based on opponent's first bid
- Time-dependent acceptance threshold (meetpoint + concession)
- Issue/value importance maps to generate optimized full preference ordering

Strategy Overview:
1. In the beginning, estimates utilities from partial ordering
2. Uses elicitation to discover issue importance by comparing bids that
   differ only in one issue (using best/worst values)
3. After gathering enough information, creates a full preference table
4. During negotiation, tries to find bids good for both sides using
   opponent modeling (tracking which values opponent prefers)
5. Acceptance is based on a "meetpoint" (midpoint between opponent's first
   offer utility and 1) with time-dependent concession
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Comparison import Comparison
from geniusweb.actions.ElicitComparison import ElicitComparison
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value
from geniusweb.issuevalue.ValueSet import ValueSet
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.DefaultPartialOrdering import DefaultPartialOrdering
from geniusweb.profile.Profile import Profile
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.profileconnection.ProfileInterface import ProfileInterface
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft_utilities_logging.Reporter import Reporter


class IssVl:
    """
    Issue-Value tuple for tracking importance.

    Holds an issue-value pair with its average position in bids,
    used to determine the importance of different values.

    Attributes:
        average: Average position/round where this value appeared.
        issue: The issue name.
        value: The value for this issue.
        rec: Number of times this value was recorded.
    """

    def __init__(self, average: float, issue: str, value: Value):
        """
        Initialize an IssVl tuple.

        Args:
            average: Initial average value (typically the first index).
            issue: The issue name.
            value: The value for this issue.
        """
        self.average: float = average
        self.issue: str = issue
        self.value: Value = value
        self.rec: int = 1

    def __lt__(self, other: IssVl) -> bool:
        """Compare by average for sorting."""
        if self.average < other.average:
            return True
        elif (
            self.average == other.average
            and self.issue == other.issue
            and self.value == other.value
        ):
            return False
        return False

    def __eq__(self, other: object) -> bool:
        """Check equality based on average, issue, and value."""
        if not isinstance(other, IssVl):
            return False
        return (
            self.average == other.average
            and self.issue == other.issue
            and self.value == other.value
        )

    def __hash__(self) -> int:
        """Hash for use in sets."""
        return hash((self.average, self.issue, str(self.value)))

    def __repr__(self) -> str:
        return f"IssVl(average={self.average}, issue={self.issue!r}, value={self.value}, rec={self.rec})"


class SortedIssVlSet:
    """
    A sorted set of IssVl objects, similar to Java's TreeSet.

    Maintains IssVl objects sorted by their average value.
    """

    def __init__(self) -> None:
        """Initialize an empty sorted set."""
        self._items: list[IssVl] = []

    def add(self, item: IssVl) -> None:
        """Add an item to the set, maintaining sort order."""
        # Remove if exists with same issue and value
        self._items = [
            x
            for x in self._items
            if not (x.issue == item.issue and x.value == item.value)
        ]
        self._items.append(item)
        self._items.sort(key=lambda x: x.average)

    def remove(self, item: IssVl) -> None:
        """Remove an item from the set."""
        self._items = [
            x
            for x in self._items
            if not (x.issue == item.issue and x.value == item.value)
        ]

    def clear(self) -> None:
        """Clear all items."""
        self._items.clear()

    def __iter__(self) -> Iterator[IssVl]:
        """Iterate in ascending order."""
        return iter(self._items)

    def __reversed__(self) -> Iterator[IssVl]:
        """Iterate in descending order."""
        return reversed(self._items)

    def __len__(self) -> int:
        """Return number of items."""
        return len(self._items)

    def find(self, issue: str, value: Value) -> IssVl | None:
        """Find an IssVl by issue and value."""
        for item in self._items:
            if item.issue == issue and item.value == value:
                return item
        return None


class EditedSLO(UtilitySpace):
    """
    Edited Simple Linear Ordering - manages bid preferences and utility estimation.

    This class maintains a partial ordering of bids and can estimate utilities.
    It also tracks issue/value importance for creating full preference orderings.

    Attributes:
        impmap: TreeSet of IssVl for tracking opponent value preferences.
        mynewbids: Full preference list created after initialization.
        issues: List of issues ordered by importance.
        isissues_ok: Whether issue importance has been determined.
        state: 0 = using partial ordering, 1 = using full preference table.
        valuesfound: List of value orderings found through elicitation.
    """

    def __init__(self, profile: Profile):
        """
        Initialize from a profile.

        Args:
            profile: The profile to initialize from (must be DefaultPartialOrdering).
        """
        if not isinstance(profile, DefaultPartialOrdering):
            raise ValueError("Only DefaultPartialOrdering supported")

        self._domain: Domain = profile.getDomain()
        self._bids: list[Bid] = self._get_sorted_bids(profile)

        # Issue-value importance tracking
        self.impmap: SortedIssVlSet = SortedIssVlSet()
        self.mynewbids: list[Bid] = []
        self.issues: list[str] | None = None
        self._values: list[ValueSet] = []
        self.isissues_ok: bool = False
        self.state: int = 0
        self.valuesfound: list[list[Value]] = []

    @staticmethod
    def _get_sorted_bids(profile: DefaultPartialOrdering) -> list[Bid]:
        """
        Sort bids from low to high utility.

        Args:
            profile: The partial ordering profile.

        Returns:
            List of bids sorted from worst to best.
        """
        bids_list = list(profile.getBids())
        # Sort ascending (worse bids first)
        bids_list.sort(key=lambda b1: 1 if profile.isPreferredOrEqual(b1, b1) else -1)
        # More accurate pairwise sorting
        for i in range(len(bids_list)):
            for j in range(i + 1, len(bids_list)):
                if profile.isPreferredOrEqual(bids_list[i], bids_list[j]):
                    bids_list[i], bids_list[j] = bids_list[j], bids_list[i]
        return bids_list

    def getName(self) -> str:
        """Get profile name (not supported)."""
        raise NotImplementedError()

    def getDomain(self) -> Domain:
        """Get the negotiation domain."""
        return self._domain

    def getReservationBid(self) -> Bid | None:
        """Get reservation bid (not supported)."""
        raise NotImplementedError()

    def getUtility(self, bid: Bid) -> Decimal:
        """
        Get the utility of a bid.

        Args:
            bid: The bid to evaluate.

        Returns:
            Utility value between 0 and 1.
        """
        if self.state == 0:
            if len(self._bids) < 2 or bid not in self._bids:
                return Decimal(0)
            index = self._bids.index(bid)
            return Decimal(index) / Decimal(len(self._bids) - 1)
        else:
            if bid in self.mynewbids:
                index = self.mynewbids.index(bid)
                return Decimal(index) / Decimal(len(self.mynewbids) - 1)
            return Decimal(0)

    def getbid(self, utility: float) -> Bid:
        """
        Get a bid with approximately the given utility.

        Args:
            utility: Target utility (0 to 1).

        Returns:
            The bid at that utility level.
        """
        if self.state == 0:
            index = int(utility * (len(self._bids) - 1))
            return self._bids[index]
        else:
            index = int(utility * (len(self.mynewbids) - 1))
            return self.mynewbids[index]

    def lookforoptions(self, curutil: float) -> Bid:
        """
        Find a bid that might be better for both parties.

        Tries to improve the bid by substituting values that the opponent
        prefers while maintaining acceptable utility.

        Args:
            curutil: Current target utility.

        Returns:
            An optimized bid.
        """
        done_issues: list[str] = []
        tooffer = self.getbid(curutil)
        bid_map: dict[str, Value]

        for issvl in reversed(self.impmap):
            bid_map = dict(tooffer.getIssueValues())
            if issvl.issue not in done_issues:
                bid_map[issvl.issue] = issvl.value
                tmpbid = Bid(bid_map)
                if float(self.getUtility(tmpbid)) >= curutil:
                    tooffer = tmpbid
                    done_issues.append(issvl.issue)

        return tooffer

    def leastcostelicitissvl(self, issue: str) -> dict[str, Value]:
        """
        Find the issue-value combination that appears most frequently in bids.

        This helps reduce elicitation cost by choosing familiar value combinations.

        Args:
            issue: The issue to exclude from the search.

        Returns:
            Dictionary of issue-value pairs that appear most frequently.
        """
        if self.issues is None:
            return {}

        issues_wo_issue = [iss for iss in self.issues if iss != issue]
        if not issues_wo_issue:
            return {}

        limits: list[int] = []
        issvls: list[dict[str, Value]] = []
        tmp_values: list[ValueSet] = []

        for iss in issues_wo_issue:
            vs = self._domain.getValues(iss)
            tmp_values.append(vs)
            limits.append(vs.size().intValue() - 1)

        # Generate all combinations
        while limits[0] != -1:
            tmp_hash: dict[str, Value] = {}
            for i, iss in enumerate(issues_wo_issue):
                tmp_hash[iss] = tmp_values[i].get(limits[i])

            limits[-1] -= 1
            for i in range(len(limits) - 1, 0, -1):
                if limits[i] == -1:
                    limits[i] = tmp_values[i].size().intValue() - 1
                    limits[i - 1] -= 1
                else:
                    break

            issvls.append(tmp_hash)

        return self._most_freq_map(issvls)

    def _most_freq_map(self, issvals: list[dict[str, Value]]) -> dict[str, Value]:
        """Find the most frequently occurring issue-value combination."""
        most_freq: dict[str, Value] = {}
        max_count = 0

        for issval in issvals:
            count = self._count_freq_map(issval)
            if count > max_count:
                max_count = count
                most_freq = issval

        return most_freq

    def _count_freq_map(self, issval: dict[str, Value]) -> int:
        """Count how many bids contain this exact issue-value combination."""
        count = 0
        for bid in self._bids:
            matches = True
            for iss, val in issval.items():
                if bid.getValue(iss) != val:
                    matches = False
                    break
            if matches:
                count += 1
        return count

    def updateissvlopp(self, bid: Bid, progress: ProgressRounds) -> None:
        """
        Update opponent issue-value preferences based on received bid.

        Tracks when each value was offered to estimate opponent preferences.

        Args:
            bid: The bid received from opponent.
            progress: Current progress for getting round number.
        """
        for issue in bid.getIssues():
            value = bid.getValue(issue)
            if value is not None:
                self._add_issvl(progress.getCurrentRound(), issue, value)

    def inittable(self) -> None:
        """
        Initialize the full preference table.

        Creates issue-value importance entries and builds the complete
        preference ordering based on discovered importance.
        """
        self._values.clear()
        self.impmap.clear()
        mybids = self.getBids()

        if self.issues is None:
            self.issues = list(self._domain.getIssues())

        for i, issue in enumerate(self.issues):
            if i > len(self.valuesfound) - 1:
                vs = self._domain.getValues(issue)
                self._values.append(vs)
                for value in vs:
                    for j, bid in enumerate(mybids):
                        if bid.getValue(issue) == value:
                            self._add_issvl(j, issue, value)

        self._createnewtable()

    def _add_issvl(self, index: int, issue: str, value: Value) -> None:
        """
        Add or update an issue-value entry.

        Args:
            index: The index/round where this value appeared.
            issue: The issue name.
            value: The value.
        """
        existing = self.impmap.find(issue, value)
        if existing is not None:
            self.impmap.remove(existing)
            existing.average = (index + existing.average * existing.rec) / (
                existing.rec + 1
            )
            existing.rec += 1
            self.impmap.add(existing)
        else:
            self.impmap.add(IssVl(float(index), issue, value))

    def _createnewtable(self) -> None:
        """
        Create the new full preference table.

        Extracts issue-value tuples in order of importance and creates
        an ordered list of issues and 2D list of values.
        """
        if self.issues is None:
            return

        orderedissue: list[str]
        divvl: list[list[Value]] = []

        if self.isissues_ok:
            orderedissue = list(self.issues)
            for i, issue in enumerate(self.issues):
                if i <= len(self.valuesfound) - 1:
                    divvl.append(self.valuesfound[i])
                else:
                    # Get values from impmap in descending order
                    issue_values: list[Value] = []
                    items_to_remove: list[IssVl] = []

                    for issvl in reversed(self.impmap):
                        if issvl.issue == issue:
                            issue_values.append(issvl.value)
                            items_to_remove.append(issvl)

                    for item in items_to_remove:
                        self.impmap.remove(item)

                    divvl.append(issue_values)
        else:
            orderedissue = []
            for i in range(len(self.issues)):
                items_to_remove = []
                for issvl in reversed(self.impmap):
                    orderedissue.append(issvl.issue)
                    divvl.append([])
                    divvl[i].append(self.getbid(1).getValue(issvl.issue))

                    best_val = self.getbid(1).getValue(issvl.issue)
                    worst_val = self.getbid(0).getValue(issvl.issue)

                    if issvl.value != best_val and issvl.value != worst_val:
                        divvl[i].append(issvl.value)

                    items_to_remove.append(issvl)

                    # Find remaining values for this issue
                    remaining = []
                    for other in reversed(self.impmap):
                        if (
                            other.issue == orderedissue[-1]
                            and other not in items_to_remove
                        ):
                            if other.value != best_val and other.value != worst_val:
                                divvl[i].append(other.value)
                            remaining.append(other)

                    items_to_remove.extend(remaining)
                    break

                for item in items_to_remove:
                    self.impmap.remove(item)

                if orderedissue:
                    worst_val = self.getbid(0).getValue(orderedissue[-1])
                    if worst_val is not None:
                        divvl[i].append(worst_val)

        self.mynewbids = self._creatett(orderedissue, divvl)

    def _creatett(self, orderedissue: list[str], divvl: list[list[Value]]) -> list[Bid]:
        """
        Create the full preference table using ordered issues and values.

        Args:
            orderedissue: List of issues ordered by importance.
            divvl: List of value lists, each ordered by importance.

        Returns:
            List of bids ordered from worst to best.
        """
        self.issues = list(orderedissue)
        newbids: list[Bid] = []
        curpass: list[int] = []

        for i in range(len(orderedissue)):
            if i < len(divvl) and divvl[i]:
                curpass.append(len(divvl[i]) - 1)
            else:
                curpass.append(0)

        while curpass and curpass[0] != -1:
            temp: dict[str, Value] = {}
            for i, issue in enumerate(orderedissue):
                if i < len(divvl) and divvl[i] and curpass[i] < len(divvl[i]):
                    temp[issue] = divvl[i][curpass[i]]

            newbids.append(Bid(temp))

            if curpass:
                curpass[-1] -= 1
                for i in range(len(curpass) - 1, 0, -1):
                    if curpass[i] == -1 and i < len(divvl):
                        curpass[i] = len(divvl[i]) - 1 if divvl[i] else 0
                        curpass[i - 1] -= 1

        return newbids

    def contains(self, bid: Bid) -> bool:
        """Check if a bid is in the ordering."""
        return bid in self._bids

    def getBids(self) -> list[Bid]:
        """Get all bids in the current ordering."""
        return list(self._bids)

    def with_comparison(self, bid: Bid, worse_bids: list[Bid]) -> None:
        """
        Update the ordering with a new comparison.

        Inserts the bid after the first bid that is not worse than it.

        Args:
            bid: The new bid to insert.
            worse_bids: All bids that are worse than this bid.
        """
        n = 0
        while n < len(self._bids) and self._bids[n] in worse_bids:
            n += 1

        new_bids = list(self._bids)
        new_bids.insert(n, bid)
        self._bids = new_bids


class NiceAgent(DefaultParty):
    """
    NiceAgent - ANAC 2020 negotiation agent with preference elicitation.

    AI-translated from Java.

    This agent is designed for the SHAOP protocol and uses preference
    elicitation to learn about its own preferences. The strategy involves:

    1. Issue Importance Discovery: Creates bids that differ only in one issue
       from the best bid (using the worst value) and elicits comparisons to
       determine issue importance ordering.

    2. Value Importance Discovery: For each issue, creates bids with different
       values while keeping other issues fixed at known good values.

    3. Mirroring Strategy: Calculates a "meetpoint" based on opponent's first
       offer and mirrors their concession pattern.

    4. Opponent Modeling: Tracks which values the opponent offers frequently
       to find mutually beneficial bids.
    """

    def __init__(self, reporter: Reporter | None = None):
        """
        Initialize the agent.

        Args:
            reporter: Optional reporter for logging.
        """
        super().__init__(reporter)

        # Profile and connection
        self._profile_interface: ProfileInterface | None = None
        self._me: PartyId | None = None
        self._progress: ProgressRounds | None = None

        # Bid tracking
        self._last_received_bid: Bid | None = None
        self._first_received_bid: Bid | None = None  # For meetpoint calculation

        # Profile estimation
        self._estimated_profile: EditedSLO | None = None
        self._meetpoint: float = 0.0  # Predicted agreement utility

        # Issues list
        self._issues: list[str] = []

        # Initialization state
        self._tableinit: int = 0  # 0 = not initialized, 1 = initialized

        # Elicitation parameters
        self._elicit_cost: float = 0.1
        self._elicit_limit: int = 3

        # Best/worst bids from partial profile
        self._best_bid: Bid | None = None
        self._worst_bid: Bid | None = None

        # Elicitation state machine
        self._done: bool = False  # True when elicitation phase finished
        self._phase_prev: int = 0  # Previous phase for interpreting results
        self._phase: int = 0  # 0=issue importance, 1=eliciting, 2=value importance
        self._elicit_bids: list[Bid] = []  # Bids to elicit
        self._elicit_index: int = 0  # Current index in elicit_bids
        self._elicit_gain: float = 1.0  # Information gain from elicitation
        self._temp_issue: str = ""  # Current issue being explored
        self._elicit_sent: bool = False  # Whether elicitation was sent
        self._first_round_complete: bool = False  # First round tracking

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
                other_action = info.getAction()
                if isinstance(other_action, Offer):
                    if not self._first_round_complete:
                        self._first_received_bid = other_action.getBid()
                    self._last_received_bid = other_action.getBid()
                elif isinstance(other_action, Comparison):
                    # Process comparison result
                    if self._estimated_profile is not None:
                        self._estimated_profile.with_comparison(
                            other_action.getBid(), list(other_action.getWorse())
                        )
                    self._elicit_sent = False
                    self._init_my_table()
            elif isinstance(info, YourTurn):
                if self._progress is not None and self._progress.getCurrentRound() == 0:
                    self._init_my_table()
                else:
                    self._my_turn()
            elif isinstance(info, Finished):
                self.getReporter().log(logging.INFO, f"Final outcome: {info}")
        except Exception as e:
            raise RuntimeError(f"Failed to handle info: {e}") from e

    def getCapabilities(self) -> Capabilities:
        """
        Return agent capabilities.

        Returns:
            Capabilities indicating SHAOP and SAOP protocol support.
        """
        return Capabilities(
            {"SHAOP", "SAOP"},
            {"geniusweb.profile.Profile", "geniusweb.profile.DefaultPartialOrdering"},
        )

    def getDescription(self) -> str:
        """
        Return agent description.

        Returns:
            Description string.
        """
        return (
            "NiceAgent: Uses elicitation to learn preferences and mirroring "
            "strategy for offers. Requires partial profile for SHAOP mode. "
            "(AI-translated from Java, ANAC 2020)"
        )

    def _init(self, info: Settings) -> None:
        """
        Initialize the agent with settings.

        Args:
            info: The settings information.
        """
        self._profile_interface = ProfileConnectionFactory.create(
            info.getProfile().getURI(), self.getReporter()
        )
        self._me = info.getID()
        self._progress = info.getProgress()

        if not isinstance(self._progress, ProgressRounds):
            # For SAOP mode, we might get ProgressTime - handle gracefully
            self.getReporter().log(
                logging.WARNING,
                "NiceAgent prefers ProgressRounds but got different progress type",
            )

        # Initialize estimated profile
        profile = self._profile_interface.getProfile()
        if isinstance(profile, DefaultPartialOrdering):
            self._estimated_profile = EditedSLO(profile)
            self._best_bid = self._estimated_profile.getbid(1)
            self._worst_bid = self._estimated_profile.getbid(0)
        else:
            # SAOP mode with full profile - create minimal EditedSLO
            self.getReporter().log(
                logging.INFO, "Running in SAOP mode - limited elicitation support"
            )
            # For non-SHAOP, we'll skip elicitation
            self._done = True

        # Get elicitation cost from parameters
        try:
            cost = info.getParameters().get("elicitationcost")
            if cost is not None:
                self._elicit_cost = float(cost)
        except (TypeError, ValueError):
            self._elicit_cost = 0.1

        self._elicit_limit = int(0.3 / self._elicit_cost)

    def _my_turn(self) -> None:
        """Execute the agent's turn."""
        self._first_round_complete = True

        # Calculate meetpoint from first received bid
        if self._first_received_bid is not None and self._estimated_profile is not None:
            first_util = float(
                self._estimated_profile.getUtility(self._first_received_bid)
            )
            self._meetpoint = (first_util + 1) / 2
            self._first_received_bid = None
            self._estimated_profile.impmap.clear()

        action: Action | None = None

        # Calculate acceptable utility for this round
        current_util = self._utility_goal()
        if current_util > 1:
            current_util = 1.0

        if self._last_received_bid is not None and self._estimated_profile is not None:
            # Update opponent value preferences
            if self._progress is not None:
                self._estimated_profile.updateissvlopp(
                    self._last_received_bid, self._progress
                )

            if self._tableinit == 0:
                # Before full preference table initialization
                if self._is_good(self._last_received_bid):
                    action = Accept(self._me, self._last_received_bid)
                else:
                    # Switch to looking for mutual options at midpoint
                    if self._progress is not None:
                        time_ratio = (
                            self._progress.getCurrentRound()
                            / self._progress.getTotalRounds()
                        )
                        if time_ratio >= 0.5 and self._tableinit == 0:
                            self._tableinit = 1

                    action = Offer(
                        self._me, self._estimated_profile.getbid(current_util)
                    )
            else:
                # After initialization - use lookforoptions
                if self._is_good(self._last_received_bid):
                    action = Accept(self._me, self._last_received_bid)
                else:
                    bid = self._estimated_profile.lookforoptions(current_util)
                    action = Offer(self._me, bid)

        # First action - offer best bid
        if action is None and self._estimated_profile is not None:
            action = Offer(self._me, self._estimated_profile.getbid(1))
            self._first_round_complete = False

        # Advance progress and send action
        if self._progress is not None and isinstance(self._progress, ProgressRounds):
            self._progress = self._progress.advance()

        if action is not None:
            self.getConnection().send(action)

    def _init_my_table(self) -> None:
        """
        Initialize the full preference table through elicitation.

        This method runs the elicitation state machine until complete.
        """
        while not self._elicit_sent:
            self._impmap()

            if self._done:
                if self._estimated_profile is not None:
                    self._estimated_profile.inittable()
                    self._estimated_profile.state = 1
                self._my_turn()
                break

    def _impmap(self) -> None:
        """
        Run the importance mapping state machine.

        Has 3 phases:
        0: Create bids to discover issue importance
        1: Elicitation phase - send bids for comparison
        2: Create bids to discover value importance for specific issue
        """
        if self._estimated_profile is None or self._profile_interface is None:
            self._done = True
            return

        if self._phase == 0:
            # Phase 0: Create bids for issue importance discovery
            if self._best_bid is not None:
                self._issues = list(self._best_bid.getIssues())
            self._elicit_bids = []

            for i in range(len(self._issues)):
                temp: dict[str, Value] = {}
                for j, issue in enumerate(self._issues):
                    if j == i:
                        # Use worst value for this issue
                        if self._worst_bid is not None:
                            val = self._worst_bid.getValue(issue)
                            if val is not None:
                                temp[issue] = val
                    else:
                        # Use best value for other issues
                        if self._best_bid is not None:
                            val = self._best_bid.getValue(issue)
                            if val is not None:
                                temp[issue] = val

                self._elicit_bids.append(Bid(temp))

            self._elicit_index = len(self._elicit_bids)
            self._phase = 1

        elif self._phase == 1:
            # Phase 1: Elicitation
            if self._elicit_limit == 0:
                self._done = True
            else:
                if self._elicit_index > 0:
                    self._elicit_index -= 1
                    if not self._estimated_profile.contains(
                        self._elicit_bids[self._elicit_index]
                    ):
                        self._elicit_limit -= 1
                        self.getReporter().log(
                            logging.INFO,
                            f"Sending {self._elicit_bids[self._elicit_index]} to elicit "
                            f"(index={self._elicit_index})",
                        )
                        self.getConnection().send(
                            ElicitComparison(
                                self._me,
                                self._elicit_bids[self._elicit_index],
                                self._estimated_profile.getBids(),
                            )
                        )
                        self._elicit_sent = True
                else:
                    # Sort elicit_bids by utility (bubble sort, ascending)
                    for i in range(len(self._elicit_bids) - 1, 0, -1):
                        for j in range(i):
                            u1 = self._estimated_profile.getUtility(
                                self._elicit_bids[j]
                            )
                            u2 = self._estimated_profile.getUtility(
                                self._elicit_bids[j + 1]
                            )
                            if u1 > u2:
                                self._elicit_bids[j], self._elicit_bids[j + 1] = (
                                    self._elicit_bids[j + 1],
                                    self._elicit_bids[j],
                                )

                    if self._phase_prev == 0:
                        # Extract issue importance ordering
                        ord_issue_list: list[str] = []
                        for bid in self._elicit_bids:
                            for issue in self._issues:
                                if self._worst_bid is not None and bid.getValue(
                                    issue
                                ) == self._worst_bid.getValue(issue):
                                    ord_issue_list.append(issue)
                                    break

                        self._estimated_profile.isissues_ok = True
                        self._issues = list(ord_issue_list)
                        self._estimated_profile.issues = list(ord_issue_list)

                    elif self._phase_prev == 2:
                        # Extract value importance for temp_issue
                        ord_val_list: list[Value] = []
                        if self._best_bid is not None:
                            best_val = self._best_bid.getValue(self._temp_issue)
                            if best_val is not None:
                                ord_val_list.append(best_val)

                        for i in range(len(self._elicit_bids) - 1, -1, -1):
                            val = self._elicit_bids[i].getValue(self._temp_issue)
                            if val is not None:
                                ord_val_list.append(val)

                        if self._worst_bid is not None:
                            worst_val = self._worst_bid.getValue(self._temp_issue)
                            if worst_val is not None:
                                ord_val_list.append(worst_val)

                        self._estimated_profile.valuesfound.append(ord_val_list)

                    self._phase = 2

        else:
            # Phase 2: Create bids for value importance discovery
            profile = self._profile_interface.getProfile()

            for i in range(len(self._issues)):
                if self._issues[i]:
                    value_set = profile.getDomain().getValues(self._issues[i])
                    self._elicit_gain *= 1.0 / value_set.size().intValue()

                    if self._elicit_gain < self._elicit_cost:
                        self._done = True
                    else:
                        self._elicit_bids.clear()
                        other_issvls = self._estimated_profile.leastcostelicitissvl(
                            self._issues[i]
                        )

                        for value in value_set:
                            if (
                                self._best_bid is not None
                                and self._worst_bid is not None
                                and value != self._best_bid.getValue(self._issues[i])
                                and value != self._worst_bid.getValue(self._issues[i])
                            ):
                                tmp_hash = dict(other_issvls)
                                tmp_hash[self._issues[i]] = value
                                self._elicit_bids.append(Bid(tmp_hash))

                        self._temp_issue = self._issues[i]
                        self._issues[i] = ""  # Mark as processed
                        self._phase_prev = 2
                        self._elicit_index = len(self._elicit_bids)
                        self._phase = 1
                        break

    def _is_good(self, bid: Bid) -> bool:
        """
        Check if a bid is acceptable.

        Uses meetpoint and time-based concession.

        Args:
            bid: The bid to evaluate.

        Returns:
            True if the bid should be accepted.
        """
        if self._estimated_profile is None or self._progress is None:
            return False

        utility = float(self._estimated_profile.getUtility(bid))
        time_ratio = self._progress.getCurrentRound() / self._progress.getTotalRounds()

        # Acceptance threshold: meetpoint + (1-meetpoint) * (1-time)
        threshold = self._meetpoint + (1 - self._meetpoint) * (1 - time_ratio)
        return utility >= threshold

    def _utility_goal(self) -> float:
        """
        Calculate the target utility for the next offer.

        Uses mirroring strategy: offers utility that mirrors what opponent offered.

        Returns:
            Target utility for the next bid.
        """
        if self._estimated_profile is None or self._last_received_bid is None:
            return 1.0

        opponent_utility = float(
            self._estimated_profile.getUtility(self._last_received_bid)
        )
        # Mirror: 2*meetpoint - opponent_utility
        return (self._meetpoint * 2) - opponent_utility
