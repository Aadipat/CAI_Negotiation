"""
HybridAgent — Portfolio meta-controller with expert voting and guarded switching.

A GeniusWeb DefaultParty implementing Strategy B:
- Multiple expert strategies (Boulware, Pareto, MiCRO, Forecast-aware)
- Frequency-based opponent model for preference estimation
- Bandit-style meta-controller for expert selection/switching
- Composite acceptance controller with safety gates
- Phase-aware negotiation (early/mid/late)

Architecture (BOA-style):
    ┌──────────────────────────────────────────────┐
    │ HybridAgent (DefaultParty)                   │
    │  ├─ OpponentModel (frequency-based)          │
    │  ├─ MetaController (bandit selection)         │
    │  │   ├─ E1: BoulwareExpert                   │
    │  │   ├─ E2: ParetoExpert                     │
    │  │   ├─ E3: MiCROExpert                      │
    │  │   └─ E4: ForecastExpert                   │
    │  └─ AcceptanceController (composite)         │
    └──────────────────────────────────────────────┘

Compatible with GeniusWeb SAOP protocol and NegMAS via the wrapper bridge.
"""

from __future__ import annotations

import logging
from random import randint
from time import time as clock
from typing import cast, Any
from decimal import Decimal

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.LearningDone import LearningDone
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.profileconnection.ProfileConnectionFactory import ProfileConnectionFactory
from geniusweb.profileconnection.ProfileInterface import ProfileInterface
from geniusweb.progress.Progress import Progress
from geniusweb.progress.ProgressRounds import ProgressRounds
from geniusweb.progress.ProgressTime import ProgressTime

from .opponent_model import OpponentModel
from .meta_controller import MetaController
from .acceptance import AcceptanceController
from .experts import BoulwareExpert, ParetoExpert, MiCROExpert, ForecastExpert


class HybridAgent(DefaultParty):
    """
    Portfolio-based hybrid negotiation agent with expert voting and guarded switching.

    Uses bandit-style meta-controller to select among four expert strategies:
    - Boulware: slow concession, pressure late
    - Pareto: maximize opponent utility at fixed self utility
    - MiCRO: tit-for-tat concession, simple but robust
    - Forecast: adapt concession to predicted opponent behavior

    Hard invariants enforced:
    - Never accept below reservation value
    - Never propose invalid offers
    - Deterministic safety gates on all decisions
    """

    def __init__(self, reporter=None):
        if reporter is not None:
            super().__init__(reporter)
        else:
            super().__init__()

        self.getReporter().log(logging.INFO, "HybridAgent initialized")

        # GeniusWeb state
        self._profile_interface: ProfileInterface | None = None
        self._profile: LinearAdditive | None = None
        self._domain: Domain | None = None
        self._me: PartyId | None = None
        self._progress: Progress | None = None
        self._settings: Settings | None = None

        # Negotiation state
        self._last_received_bid: Bid | None = None
        self._last_received_util: float = 0.0
        self._best_received_bid: Bid | None = None
        self._best_received_util: float = 0.0
        self._round: int = 0
        self._sorted_bids: list[Bid] = []
        self._min_util: float = 0.6
        self._max_util: float = 1.0
        self._reservation: float = 0.0

        # BOA components (initialized on Settings)
        self._opp_model: OpponentModel | None = None
        self._meta: MetaController | None = None
        self._acceptance: AcceptanceController | None = None

    # ── GeniusWeb interface ──────────────────────────────────────────

    def getCapabilities(self) -> Capabilities:
        return Capabilities(
            set(["SAOP", "Learn"]),
            set(["geniusweb.profile.utilityspace.LinearAdditive"]),
        )

    def getDescription(self) -> str:
        return (
            "HybridAgent: Portfolio meta-controller with expert voting "
            "and guarded switching (Strategy B). Uses Boulware, Pareto, "
            "MiCRO, and Forecast-aware experts with bandit selection."
        )

    def notifyChange(self, info: Inform):
        """Main entry point for GeniusWeb protocol messages."""
        try:
            if isinstance(info, Settings):
                self._handle_settings(info)
            elif isinstance(info, ActionDone):
                self._handle_action_done(info)
            elif isinstance(info, YourTurn):
                self._handle_your_turn()
            elif isinstance(info, Finished):
                self._handle_finished(info)
            else:
                self.getReporter().log(
                    logging.WARNING, f"Ignoring unknown info: {type(info)}"
                )
        except Exception as ex:
            self.getReporter().log(
                logging.CRITICAL, f"Error in HybridAgent: {ex}"
            )

    def terminate(self):
        self.getReporter().log(logging.INFO, "HybridAgent terminating")
        super().terminate()
        if self._profile_interface is not None:
            self._profile_interface.close()
            self._profile_interface = None

    # ── Event handlers ───────────────────────────────────────────────

    def _handle_settings(self, settings: Settings):
        """Initialize agent on receiving Settings."""
        self._settings = settings
        self._me = settings.getID()
        self._progress = settings.getProgress()

        protocol = str(settings.getProtocol().getURI())
        if protocol == "Learn":
            self.getConnection().send(LearningDone(self._me))
            return

        # Load profile
        self._profile_interface = ProfileConnectionFactory.create(
            settings.getProfile().getURI(), self.getReporter()
        )
        self._profile = cast(LinearAdditive, self._profile_interface.getProfile())
        self._domain = self._profile.getDomain()

        # Pre-sort all bids by descending utility
        all_bids = AllBidsList(self._domain)
        bid_list = list(all_bids)
        bid_list.sort(key=lambda b: self._profile.getUtility(b), reverse=True)
        self._sorted_bids = bid_list

        # Compute utility bounds
        if self._sorted_bids:
            self._max_util = float(self._profile.getUtility(self._sorted_bids[0]))
            raw_min = float(self._profile.getUtility(self._sorted_bids[-1]))
        else:
            self._max_util = 1.0
            raw_min = 0.0

        # Check for reservation bid
        rv_bid = self._profile.getReservationBid()
        if rv_bid is not None:
            self._reservation = float(self._profile.getUtility(rv_bid))
        else:
            self._reservation = 0.0

        # CRITICAL: Set a hard floor — never aspirate below 60% of max utility
        # or reservation, whichever is higher. This prevents over-concession.
        hard_floor = max(0.55 * self._max_util, self._reservation, raw_min)
        self._min_util = hard_floor

        # Initialize BOA components
        self._opp_model = OpponentModel(self._domain)
        self._meta = MetaController()
        self._acceptance = AcceptanceController(
            reservation=self._reservation,
            min_util=self._min_util,
            emergency_time=0.98,
            emergency_floor=max(self._reservation, self._min_util * 0.9),
        )

        self.getReporter().log(
            logging.INFO,
            f"Initialized: {len(self._sorted_bids)} bids, "
            f"util=[{self._min_util:.3f}, {self._max_util:.3f}], "
            f"reservation={self._reservation:.3f}"
        )

    def _handle_action_done(self, info: ActionDone):
        """Process opponent's action."""
        action = info.getAction()
        actor = action.getActor()

        if actor == self._me:
            return  # Ignore our own actions

        if isinstance(action, Offer):
            bid = action.getBid()
            self._last_received_bid = bid
            if self._profile is not None:
                self._last_received_util = float(self._profile.getUtility(bid))
                if self._last_received_util > self._best_received_util:
                    self._best_received_util = self._last_received_util
                    self._best_received_bid = bid

                # Update opponent model
                t = self._get_time()
                if self._opp_model is not None:
                    self._opp_model.update(bid, t)

    def _handle_your_turn(self):
        """Decide what to do on our turn."""
        self._round += 1

        if self._profile is None or not self._sorted_bids:
            # Fallback: offer best bid
            if self._sorted_bids:
                self.getConnection().send(Offer(self._me, self._sorted_bids[0]))
                self._advance_progress()
            return

        try:
            self._do_turn()
        except Exception as ex:
            self.getReporter().log(
                logging.WARNING, f"Error in turn logic, sending best bid: {ex}"
            )
            # CRITICAL: always send an action to avoid BROKEN status
            self.getConnection().send(Offer(self._me, self._sorted_bids[0]))
            self._advance_progress()

    def _do_turn(self):
        """Core turn logic, separated for error recovery."""
        t = self._get_time()

        # Build shared state dict
        state = self._build_state(t)

        # Select expert via meta-controller
        expert_idx = self._meta.select_expert(self._opp_model, t, self._round)
        expert = self._meta.get_expert(expert_idx)

        # Get expert's proposed bid
        proposed = expert.propose(
            self._sorted_bids, self._profile, self._opp_model, t, state
        )

        # Safety: ensure proposed bid has utility above min_util
        if proposed is not None:
            u_proposed = float(self._profile.getUtility(proposed))
            if u_proposed < self._min_util:
                proposed = self._sorted_bids[0]  # fallback to best
        else:
            proposed = self._sorted_bids[0]

        # Update state with planned counter-offer
        state["planned_counter"] = proposed

        # Acceptance decision
        if self._last_received_bid is not None:
            should_accept = self._acceptance.should_accept(
                self._last_received_bid,
                self._profile,
                self._opp_model,
                expert,
                t,
                state,
            )

            if should_accept:
                # Safety gate: double-check min_util floor
                u_accept = float(self._profile.getUtility(self._last_received_bid))
                if u_accept >= self._min_util:
                    self._meta.update_reward(expert_idx, u_accept)
                    self.getConnection().send(Accept(self._me, self._last_received_bid))
                    self._advance_progress()
                    return
                # If below floor, fall through to make offer

        # Provide reward signal to meta-controller
        u_proposed = float(self._profile.getUtility(proposed))
        self._meta.update_reward(expert_idx, u_proposed)

        self.getConnection().send(Offer(self._me, proposed))
        self._advance_progress()

    def _handle_finished(self, info: Finished):
        """Handle negotiation end."""
        self.getReporter().log(logging.INFO, f"Negotiation finished: {info}")
        self.terminate()

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_time(self) -> float:
        """Get normalized time in [0, 1]."""
        if self._progress is None:
            return 0.0
        if isinstance(self._progress, ProgressTime):
            return self._progress.get(round(clock() * 1000))
        elif isinstance(self._progress, ProgressRounds):
            return self._progress.get(round(clock() * 1000))
        return 0.0

    def _advance_progress(self):
        """Advance round-based progress if applicable."""
        if isinstance(self._progress, ProgressRounds):
            self._progress = self._progress.advance()

    def _build_state(self, t: float) -> dict[str, Any]:
        """Build the shared state dictionary for experts and acceptance controller."""
        return {
            "t": t,
            "round": self._round,
            "min_util": self._min_util,
            "max_util": self._max_util,
            "reservation": self._reservation,
            "best_received_util": self._best_received_util,
            "best_received_bid": self._best_received_bid,
            "last_received_util": self._last_received_util,
            "last_received_bid": self._last_received_bid,
            "sorted_bids": self._sorted_bids,
            "num_bids": len(self._sorted_bids),
            "planned_counter": None,  # filled in after expert proposes
        }
