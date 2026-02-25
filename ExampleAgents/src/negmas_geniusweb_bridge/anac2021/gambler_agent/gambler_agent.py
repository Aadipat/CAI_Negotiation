"""
GamblerAgent - A Multi-Armed Bandit based negotiation agent.

This agent was translated from the original Java implementation from ANAC 2021.
Translation was performed using AI assistance.

Original strategy:
- Uses UCB (Upper Confidence Bound) Multi-Armed Bandit to select among 4 sub-agents
- Each sub-agent is a PonPoko-style agent with different acceptance strategies
- All sub-agents use time-dependent threshold patterns with oscillating behavior
- Learns which agent performs best against specific opponents over multiple sessions
- Persistent state tracks rewards per opponent to improve agent selection

Sub-agent acceptance strategies:
- PonPoko1: Simple threshold-based acceptance (accept if util > threshold_low)
- PonPoko2: ACcombi - Accept if util >= next_offer_util or (time > 0.99 and util >= 0.65)
- PonPoko3: ACp - Accept based on time-dependent power function threshold
- PonPoko4: ACstatistical - Statistical acceptance with roulette wheel selection

Original authors: Arash Ebrahimnezhad, Hamid Jazayeri (ANAC 2021)

Translation Notes:
-----------------
Complexity: Medium-High (multiple sub-agents, MAB algorithm, acceptance strategies)

Simplifications made:
- Persistent state stored in memory only. Original used file-based JSON storage
  to persist UCB rewards per opponent across JVM sessions. This means the bandit
  cannot learn which sub-agent works best against specific opponents over time.
- Learning protocol handler simplified (sends LearningDone immediately)

Known differences from original:
- UCB exploration/exploitation learning only works within a single session
- Without persistence, first encounter with any opponent starts with uniform
  rewards (1.0 for all agents), so initial agent selection is essentially random
- The `max_received_bid_details` tracking simplified (used in _get_best_opponent_bid_utility)

Library replacements:
- None required - UCB algorithm implemented from scratch using standard Python

Type handling:
- Uses `size.intValue() if hasattr(size, "intValue") else int(size)` pattern
  in SubAgent._generate_random_bids() and _get_best_bid() for BigInteger handling

Architecture notes:
- PonPoko sub-agents are inner classes that share threshold update logic but
  differ in acceptance strategy (AC classes)
- The oscillating threshold patterns (sin-based) are preserved exactly from original
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass
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
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.Progress import Progress
from geniusweb.progress.ProgressRounds import ProgressRounds

if TYPE_CHECKING:
    from geniusweb.profileconnection.ProfileInterface import ProfileInterface
    from tudelft_utilities_logging.Reporter import Reporter


# =============================================================================
# Bid Info Helper Classes
# =============================================================================


@dataclass
class BidInfo:
    """Stores a bid and its utility value."""

    bid: Bid
    util: float = 0.0


@dataclass
class BidDetails:
    """Details about a bid including utility."""

    bid: Bid
    my_undiscounted_util: float = 0.0


# =============================================================================
# Acceptance Strategy Classes
# =============================================================================


class ACcombi:
    """
    Combined acceptance strategy.

    Accept if:
    - alpha * bid_util + beta >= next_offer_util, OR
    - time > 0.99 AND bid_util >= 0.65
    """

    def __init__(self, utility_space: UtilitySpace):
        self.utility_space = utility_space
        self.alpha = 1.0
        self.beta = 0.0

    def is_good(self, bid: Bid, next_offer: Bid, t: float) -> bool:
        bid_util = float(self.utility_space.getUtility(bid))
        next_util = float(self.utility_space.getUtility(next_offer))

        b1 = self.alpha * bid_util + self.beta >= next_util
        b2 = t > 0.99
        b3 = bid_util >= 0.65

        return b1 or (b2 and b3)


class ACp:
    """
    ParsAgent-style acceptance strategy.

    Uses time-dependent threshold with power function decay.
    Accept if util >= U_T(time) AND util >= C, OR time > 0.99
    """

    def __init__(self, utility_space: UtilitySpace):
        self.utility_space = utility_space
        self.beta_without_discount = 0.2
        self.beta_with_discount = 0.15
        self.c = 0.65

    def is_good(self, bid: Bid, t: float, discounted_factor: bool = False) -> bool:
        bid_util = float(self.utility_space.getUtility(bid))

        b1 = bid_util >= self._u_t(t, discounted_factor)
        b2 = bid_util >= self.c
        b3 = t > 0.99

        return (b1 and b2) or b3

    def _u_t(self, t: float, discounted_factor: bool) -> float:
        beta = (
            self.beta_with_discount if discounted_factor else self.beta_without_discount
        )
        return 1 - math.pow(t, 1.0 / beta)


class ACstatistical:
    """
    Statistical acceptance strategy.

    Uses roulette wheel selection based on utility difference
    and time-dependent probability adjustment.
    """

    def __init__(self, utility_space: UtilitySpace):
        self.utility_space = utility_space
        self.a = 1.0
        self.b = 0.0
        self.e = 0.2
        self.min_val = 0.0
        self.max_val = 1.0

    def is_good(
        self,
        bid: Bid,
        next_bid: Bid,
        best_opponent_bid_utility: float,
        t: float,
        my_worst_offer_util: float,
    ) -> bool:
        last_opp_util = float(self.utility_space.getUtility(bid))
        next_my_util = float(self.utility_space.getUtility(next_bid))

        b1 = t >= 0.99 and last_opp_util >= 0.65
        b2 = self.a * last_opp_util + self.b >= next_my_util

        b3 = False
        if my_worst_offer_util != -1:
            b3 = self._roulette_wheel(1 - (my_worst_offer_util - last_opp_util), t)

        return b1 or b2 or b3

    def _roulette_wheel(self, p: float, nego_time: float) -> bool:
        r_value = random.random()
        new_r_value = self._update_p(r_value, nego_time)
        return p - new_r_value >= 0.1

    def _update_p(self, p: float, nego_time: float) -> float:
        temp = p + (
            self.min_val + (self.max_val - self.min_val) * (1 - self._f(nego_time))
        )
        return min(temp, 1.0)

    def _f(self, t: float) -> float:
        if self.e == 0:
            return 0.0
        return math.pow(t, 1.0 / self.e)


# =============================================================================
# PonPoko Sub-Agents
# =============================================================================


class SubAgent:
    """Base class for PonPoko sub-agents."""

    PATTERN_SIZE = 5
    NUM_SAMPLE_BIDS = 30000

    def __init__(self):
        self.utility_space: UtilitySpace | None = None
        self.me: PartyId | None = None
        self.domain = None
        self.bid_infos: list[BidInfo] = []
        self.threshold_low = 0.99
        self.threshold_high = 1.0
        self.pattern = 0
        self._rand = random.Random()

    def init(self, utility_space: UtilitySpace, me: PartyId) -> None:
        """Initialize the sub-agent."""
        self.utility_space = utility_space
        self.me = me
        self.domain = utility_space.getDomain()

        # Generate random sample bids
        self._generate_random_bids()

        # Sort by utility descending
        self.bid_infos.sort(key=lambda x: x.util, reverse=True)

        # Select random pattern
        self.pattern = self._rand.randint(0, self.PATTERN_SIZE - 1)

    def _generate_random_bids(self) -> None:
        """Generate a sample of random bids with their utilities."""
        if self.domain is None or self.utility_space is None:
            return

        all_bids = AllBidsList(self.domain)
        size = all_bids.size()
        size_int = size.intValue() if hasattr(size, "intValue") else int(size)

        seen_bids: set[str] = set()
        for _ in range(self.NUM_SAMPLE_BIDS):
            j = self._rand.randint(0, size_int - 1)
            bid = all_bids.get(j)
            bid_hash = str(bid)

            if bid_hash not in seen_bids:
                seen_bids.add(bid_hash)
                util = float(self.utility_space.getUtility(bid))
                self.bid_infos.append(BidInfo(bid=bid, util=util))

    def _update_thresholds(self, t: float) -> None:
        """Update threshold_high and threshold_low based on time and pattern."""
        if self.pattern == 0:
            self.threshold_high = 1 - 0.1 * t
            self.threshold_low = 1 - 0.1 * t - 0.1 * abs(math.sin(t * 40))
        elif self.pattern == 1:
            self.threshold_high = 1
            self.threshold_low = 1 - 0.22 * t
        elif self.pattern == 2:
            self.threshold_high = 1 - 0.1 * t
            self.threshold_low = 1 - 0.1 * t - 0.15 * abs(math.sin(t * 20))
        elif self.pattern == 3:
            self.threshold_high = 1 - 0.05 * t
            self.threshold_low = 1 - 0.1 * t
            if t > 0.99:
                self.threshold_low = 1 - 0.3 * t
        elif self.pattern == 4:
            self.threshold_high = 1 - 0.15 * t * abs(math.sin(t * 20))
            self.threshold_low = 1 - 0.21 * t * abs(math.sin(t * 20))
        else:
            self.threshold_high = 1 - 0.1 * t
            self.threshold_low = 1 - 0.2 * abs(math.sin(t * 40))

    def _select_bid_from_range(self) -> Bid | None:
        """Select a random bid within the threshold range."""
        candidates = [
            bi
            for bi in self.bid_infos
            if self.threshold_low <= bi.util <= self.threshold_high
        ]
        if not candidates:
            return None
        return self._rand.choice(candidates).bid

    def choose_action(
        self,
        last_received_bid: Bid | None,
        best_opponent_bid_utility: float,
        t: float,
        my_worst_offer_util: float,
    ) -> Action:
        """Choose an action based on the current state. Subclasses should override."""
        raise NotImplementedError("Subclasses must implement choose_action")


class PonPokoAgent1(SubAgent):
    """
    PonPoko agent with simple threshold-based acceptance.

    Accepts if opponent's bid utility > threshold_low.
    """

    def choose_action(
        self,
        last_received_bid: Bid | None,
        best_opponent_bid_utility: float,
        t: float,
        my_worst_offer_util: float,
    ) -> Action:
        self._update_thresholds(t)

        # Accept if opponent bid is above threshold_low
        if last_received_bid is not None and self.utility_space is not None:
            bid_util = float(self.utility_space.getUtility(last_received_bid))
            if bid_util > self.threshold_low:
                return Accept(self.me, last_received_bid)

        # Select bid within threshold range
        bid = None
        while bid is None:
            bid = self._select_bid_from_range()
            if bid is None:
                self.threshold_low -= 0.0001

        return Offer(self.me, bid)


class PonPokoAgent2(SubAgent):
    """
    PonPoko agent with ACcombi acceptance strategy.

    Uses combined acceptance: accept if bid >= next_offer OR near deadline.
    """

    def __init__(self):
        super().__init__()
        self.ac: ACcombi | None = None

    def init(self, utility_space: UtilitySpace, me: PartyId) -> None:
        super().init(utility_space, me)
        self.ac = ACcombi(utility_space)

    def choose_action(
        self,
        last_received_bid: Bid | None,
        best_opponent_bid_utility: float,
        t: float,
        my_worst_offer_util: float,
    ) -> Action:
        self._update_thresholds(t)

        # Select bid within threshold range
        bid = None
        while bid is None:
            bid = self._select_bid_from_range()
            if bid is None:
                self.threshold_low -= 0.0001

        # Check acceptance with ACcombi
        if last_received_bid is not None and self.ac is not None:
            if self.ac.is_good(last_received_bid, bid, t):
                return Accept(self.me, last_received_bid)

        return Offer(self.me, bid)


class PonPokoAgent3(SubAgent):
    """
    PonPoko agent with ACp (ParsAgent-style) acceptance strategy.

    Uses time-dependent power function threshold.
    """

    def __init__(self):
        super().__init__()
        self.ac: ACp | None = None

    def init(self, utility_space: UtilitySpace, me: PartyId) -> None:
        super().init(utility_space, me)
        self.ac = ACp(utility_space)

    def choose_action(
        self,
        last_received_bid: Bid | None,
        best_opponent_bid_utility: float,
        t: float,
        my_worst_offer_util: float,
    ) -> Action:
        self._update_thresholds(t)

        # Select bid within threshold range
        bid = None
        while bid is None:
            bid = self._select_bid_from_range()
            if bid is None:
                self.threshold_low -= 0.0001

        # Check acceptance with ACp
        if last_received_bid is not None and self.ac is not None:
            if self.ac.is_good(last_received_bid, t, discounted_factor=False):
                return Accept(self.me, last_received_bid)

        return Offer(self.me, bid)


class PonPokoAgent4(SubAgent):
    """
    PonPoko agent with ACstatistical acceptance strategy.

    Uses statistical acceptance with roulette wheel selection.
    """

    def __init__(self):
        super().__init__()
        self.ac: ACstatistical | None = None

    def init(self, utility_space: UtilitySpace, me: PartyId) -> None:
        super().init(utility_space, me)
        self.ac = ACstatistical(utility_space)

    def choose_action(
        self,
        last_received_bid: Bid | None,
        best_opponent_bid_utility: float,
        t: float,
        my_worst_offer_util: float,
    ) -> Action:
        self._update_thresholds(t)

        # Select bid within threshold range
        bid = None
        while bid is None:
            bid = self._select_bid_from_range()
            if bid is None:
                self.threshold_low -= 0.0001

        # Check acceptance with ACstatistical
        if last_received_bid is not None and self.ac is not None:
            if self.ac.is_good(
                last_received_bid,
                bid,
                best_opponent_bid_utility,
                t,
                my_worst_offer_util,
            ):
                return Accept(self.me, last_received_bid)

        return Offer(self.me, bid)


# =============================================================================
# Main GamblerAgent Class
# =============================================================================


class GamblerAgent(DefaultParty):
    """
    A Multi-Armed Bandit based negotiation agent from ANAC 2021.

    Uses UCB (Upper Confidence Bound) algorithm to select among 4 PonPoko-style
    sub-agents, learning which performs best against specific opponents over
    multiple negotiation sessions.
    """

    NUM_AGENTS = 4
    UCB_CONSTANT = 0.01

    def __init__(self, reporter: "Reporter | None" = None):
        super().__init__(reporter)

        # Multi-Armed Bandit state
        self._agents: list[SubAgent] = []
        self._rewards: list[float] = [1.0] * self.NUM_AGENTS
        self._chosen_agent_num: int = -1
        self._init1_done: bool = False
        self._init2_done: bool = False

        # Negotiation state
        self._last_received_bid: Bid | None = None
        self._me: PartyId | None = None
        self._profile_interface: "ProfileInterface | None" = None
        self._progress: Progress | None = None
        self._utility_space: UtilitySpace | None = None
        self._opponent_name: str | None = None

        # Simplified persistent state (no file I/O)
        self._persistent_state: dict[str, Any] = {
            "rewards": {},  # opponent_name -> {agent_num: reward}
            "max_received_bid_details": {},  # opponent_name -> BidDetails
        }

        # Negotiation data for this session
        self._negotiation_data: dict[str, Any] = {
            "opponent_name": None,
            "chosen_agent": -1,
            "my_bids": [],  # list of BidDetails
            "opp_bid_details": [],  # list of BidDetails
            "agreement_bid_details": None,
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

        protocol = settings.getProtocol().getURI().getPath()

        if protocol == "Learn":
            # Learning phase - update persistent state
            # (simplified: no file I/O in this implementation)
            from geniusweb.actions.LearningDone import LearningDone

            self.getConnection().send(LearningDone(self._me))
        else:
            # Negotiation phase
            self._profile_interface = ProfileConnectionFactory.create(
                settings.getProfile().getURI(), self.getReporter()
            )

            profile = self._profile_interface.getProfile()
            if isinstance(profile, UtilitySpace):
                self._utility_space = profile
                self._init_agents()

    def _init_agents(self) -> None:
        """Initialize the 4 PonPoko sub-agents."""
        if self._init1_done:
            return

        self._agents = [
            PonPokoAgent1(),
            PonPokoAgent2(),
            PonPokoAgent3(),
            PonPokoAgent4(),
        ]

        if self._utility_space is not None and self._me is not None:
            for agent in self._agents:
                agent.init(self._utility_space, self._me)

        self._init1_done = True

    def _init_agent_selection(self) -> None:
        """Initialize agent selection using UCB after learning opponent name."""
        if self._init2_done:
            return

        # Reset rewards
        self._rewards = [1.0] * self.NUM_AGENTS

        # Load rewards from persistent state if available
        if self._opponent_name is not None:
            opponent_rewards = self._persistent_state["rewards"].get(
                self._opponent_name, {}
            )
            for agent_num, reward in opponent_rewards.items():
                if 0 <= int(agent_num) < self.NUM_AGENTS:
                    self._rewards[int(agent_num)] = reward

        # Choose agent using UCB
        self._chosen_agent_num = self._choose_agent_ucb()
        self._negotiation_data["chosen_agent"] = self._chosen_agent_num

        self._init2_done = True

    def _choose_agent_ucb(self) -> int:
        """Choose an agent using UCB (Upper Confidence Bound) algorithm."""
        chosen = -1
        max_ucb = -100000.0

        opponent_rewards = self._persistent_state["rewards"].get(
            self._opponent_name, {}
        )
        n_total = len(opponent_rewards)  # Total number of plays

        for i in range(self.NUM_AGENTS):
            u_mean = self._rewards[i]

            # Count plays for this agent
            n_agent = sum(1 for k in opponent_rewards if int(k) == i)

            if n_total != 0 and n_agent != 0:
                # UCB formula
                ucb = u_mean + self.UCB_CONSTANT * math.sqrt(
                    math.log(n_total) / n_agent
                )
                if ucb > max_ucb:
                    max_ucb = ucb
                    chosen = i
            else:
                # No data for this agent - explore it
                return i

        return chosen

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
            self._process_action(action)

    def _process_action(self, action: Action) -> None:
        """Process an action performed by the opponent."""
        if isinstance(action, Offer):
            self._last_received_bid = action.getBid()

            if self._utility_space is not None:
                util = float(self._utility_space.getUtility(self._last_received_bid))
                self._negotiation_data["opp_bid_details"].append(
                    BidDetails(bid=self._last_received_bid, my_undiscounted_util=util)
                )

        # Initialize agent selection after receiving first opponent action
        self._init_agent_selection()

    def _my_turn(self) -> None:
        """Execute agent's turn."""
        if isinstance(self._progress, ProgressRounds):
            self._progress = self._progress.advance()

        if self._chosen_agent_num != -1 and self._chosen_agent_num < len(self._agents):
            # Get context for sub-agent
            best_opp_util = self._get_best_opponent_bid_utility()
            my_worst_util = self._get_my_worst_offer_utility()
            t = self._progress.get(int(time.time() * 1000)) if self._progress else 0

            # Get action from chosen sub-agent
            action = self._agents[self._chosen_agent_num].choose_action(
                self._last_received_bid,
                best_opp_util,
                t,
                my_worst_util,
            )

            # If offer, check if we can do better with opponent's previous bids
            if isinstance(action, Offer):
                action = self._find_in_opp_prev_bids(action.getBid())

                # Track our bids
                if self._utility_space is not None:
                    bid = action.getBid()
                    util = float(self._utility_space.getUtility(bid))
                    self._negotiation_data["my_bids"].append(
                        BidDetails(bid=bid, my_undiscounted_util=util)
                    )

            self.getConnection().send(action)
        else:
            # Fallback: offer best bid
            bid = self._get_best_bid()
            if self._utility_space is not None:
                util = float(self._utility_space.getUtility(bid))
                self._negotiation_data["my_bids"].append(
                    BidDetails(bid=bid, my_undiscounted_util=util)
                )
            self.getConnection().send(Offer(self._me, bid))

    def _get_best_opponent_bid_utility(self) -> float:
        """Get the utility of the best bid received from opponent."""
        max_stored = self._persistent_state["max_received_bid_details"].get(
            self._opponent_name
        )
        if max_stored is not None:
            return max_stored.my_undiscounted_util
        return -1.0

    def _get_my_worst_offer_utility(self) -> float:
        """Get the utility of our worst offer so far."""
        my_bids = self._negotiation_data["my_bids"]
        if not my_bids:
            return -1.0
        return min(bd.my_undiscounted_util for bd in my_bids)

    def _find_in_opp_prev_bids(self, bid: Bid) -> Action:
        """Check if any opponent's previous bid is better than our planned bid."""
        if self._utility_space is None:
            return Offer(self._me, bid)

        next_util = float(self._utility_space.getUtility(bid))

        opp_bids = self._negotiation_data["opp_bid_details"]
        if not opp_bids:
            return Offer(self._me, bid)

        # Find best opponent bid
        max_util = -1.0
        best_opp_bid: Bid | None = None

        for bd in opp_bids:
            if bd.my_undiscounted_util >= max_util:
                max_util = bd.my_undiscounted_util
                best_opp_bid = bd.bid

        # If opponent's best bid is better than our planned bid, use it
        if max_util >= next_util and max_util != -1.0 and best_opp_bid is not None:
            return Offer(self._me, best_opp_bid)

        return Offer(self._me, bid)

    def _get_best_bid(self) -> Bid:
        """Get the best bid in our utility space."""
        if self._utility_space is None:
            raise ValueError("Utility space not initialized")

        domain = self._utility_space.getDomain()
        all_bids = AllBidsList(domain)
        size = all_bids.size()
        size_int = size.intValue() if hasattr(size, "intValue") else int(size)

        max_bid: Bid | None = None
        max_util = -1.0

        # Sample bids to find best one
        sample_size = min(size_int, 10000)
        for _ in range(sample_size):
            idx = random.randint(0, size_int - 1)
            bid = all_bids.get(idx)
            util = float(self._utility_space.getUtility(bid))
            if util > max_util:
                max_util = util
                max_bid = bid

        if max_bid is None:
            max_bid = all_bids.get(0)

        return max_bid

    def _process_agreements(self, info: Finished) -> None:
        """Process final agreements."""
        agreements = info.getAgreements()
        if agreements and not agreements.getMap().isEmpty():
            agreement = list(agreements.getMap().values())[0]
            if self._utility_space is not None:
                util = float(self._utility_space.getUtility(agreement))
                self._negotiation_data["agreement_bid_details"] = BidDetails(
                    bid=agreement, my_undiscounted_util=util
                )

    def getCapabilities(self) -> Capabilities:
        """Return agent capabilities."""
        return Capabilities(
            {"SAOP", "Learn"},
            {"geniusweb.profile.utilityspace.LinearAdditive"},
        )

    def getDescription(self) -> str:
        """Return agent description."""
        return (
            "GamblerAgent: Multi-Armed Bandit agent using UCB to select among "
            "4 PonPoko-style sub-agents (AI-translated from Java, ANAC 2021)"
        )

    def terminate(self) -> None:
        """Clean up resources."""
        super().terminate()
        if self._profile_interface is not None:
            self._profile_interface.close()
            self._profile_interface = None
