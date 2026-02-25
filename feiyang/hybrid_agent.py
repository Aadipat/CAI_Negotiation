"""
HybridAgent v2 — Portfolio meta-controller with enhanced agreement-seeking.

A NegMAS SAONegotiator implementing an improved Strategy B:
- Five expert strategies (Boulware, Pareto, NiceTFT, Forecast, DealSeeker)
- Frequency-based opponent model with TFT/stalemate detection
- Bandit-style meta-controller with forced overrides for TFT/deadline
- Composite acceptance controller with progressive emergency lowering
- Phase-aware negotiation with stalemate-breaking

Architecture (BOA-style):
    ┌──────────────────────────────────────────────────────────┐
    │ HybridAgent v2 (SAONegotiator)                          │
    │  ├─ OpponentModel (frequency + TFT + stalemate)         │
    │  ├─ MetaController (5-expert bandit with overrides)      │
    │  │   ├─ E0: BoulwareExpert (e=0.08)                     │
    │  │   ├─ E1: ParetoExpert (alpha=0.35)                   │
    │  │   ├─ E2: NiceTFTExpert (reciprocal concession)       │
    │  │   ├─ E3: ForecastExpert (adaptive, e=0.10)           │
    │  │   └─ E4: DealSeekerExpert (late-game closer)         │
    │  └─ AcceptanceController (progressive emergency)         │
    └──────────────────────────────────────────────────────────┘

Key improvements over v1:
1. Agreement rate: min_util floor 50% → 35-40% (prevents stalemate)
2. Emergency acceptance: t=0.97 → t=0.90 (earlier deal-seeking)
3. NiceTFT expert: defeats MiCRO/TFT opponents via reciprocal concession
4. DealSeeker expert: forced near deadline to maximize agreement probability
5. Stalemate detection: breaks deadlocks by switching strategy
6. Reciprocity tracking: adapts concession to opponent's behavior
7. Offer self-correction: verifies proposed offers meet utility floor

Pure NegMAS implementation — no GeniusWeb dependency.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from negmas import Outcome
from negmas.sao import SAONegotiator, SAOState, ResponseType

from .opponent_model import OpponentModel
from .meta_controller import MetaController
from .acceptance import AcceptanceController


class HybridAgent(SAONegotiator):
    """
    Portfolio-based hybrid negotiation agent v2.

    Hard invariants enforced:
    - Never accept below reservation value
    - Never propose offers below min_util floor
    - Never accept in first 2 rounds (opponent model bootstrap)
    - Deterministic safety gates on all decisions
    - Self-correction: verify every proposed outcome meets constraints
    """

    def _init_agent(self):
        """Lazy initialization — called on first propose/respond."""
        if hasattr(self, "_is_initialized"):
            return

        # Reservation value
        self._reservation: float = 0.0
        if self.ufun is not None and self.ufun.reserved_value is not None:
            self._reservation = float(self.ufun.reserved_value)

        # Enumerate and sort all outcomes by descending utility
        self._all_outcomes: list[Outcome] = list(
            self.nmi.outcome_space.enumerate_or_sample(max_cardinality=10000)
        )
        self._my_utilities: dict[Outcome, float] = {
            o: float(self.ufun(o)) for o in self._all_outcomes
        }
        self._sorted_outcomes: list[Outcome] = sorted(
            self._all_outcomes,
            key=lambda o: self._my_utilities[o],
            reverse=True,
        )

        # Compute utility bounds
        if self._sorted_outcomes:
            self._max_util = self._my_utilities[self._sorted_outcomes[0]]
            raw_min = self._my_utilities[self._sorted_outcomes[-1]]
        else:
            self._max_util = 1.0
            raw_min = 0.0

        # Hard floor — 35% of max_util balances deal-making with utility
        hard_floor = max(0.35 * self._max_util, self._reservation, raw_min)
        self._min_util = hard_floor

        # Build opponent model info
        n_issues = len(self._all_outcomes[0]) if self._all_outcomes else 0
        values_per_issue: list[int] = []
        for i in range(n_issues):
            unique_vals = set(o[i] for o in self._all_outcomes)
            values_per_issue.append(len(unique_vals))

        # Initialize BOA components with improved parameters
        self._opp_model = OpponentModel(n_issues, values_per_issue)
        self._meta = MetaController()
        self._acceptance = AcceptanceController(
            reservation=self._reservation,
            min_util=self._min_util,
            initial_threshold=0.92,         # tighter opening to hold ground
            final_threshold=max(0.50, self._min_util),  # don't go below 50%
            no_accept_rounds=2,             # build opponent model before accepting
            emergency_time=0.88,            # later emergency — don't panic early
            emergency_floor=max(self._reservation, self._min_util),
        )

        # Negotiation state
        self._last_received_offer: Outcome | None = None
        self._last_received_util: float = 0.0
        self._best_received_offer: Outcome | None = None
        self._best_received_util: float = 0.0
        self._round: int = 0

        # Offer tracking for self-correction
        self._last_proposed_util: float = self._max_util
        self._proposal_history: list[float] = []

        self._is_initialized = True

    # ── NegMAS interface ─────────────────────────────────────────────

    def respond(self, state: SAOState, source: str | None = None) -> ResponseType:
        """Decide whether to accept or reject the current offer."""
        self._init_agent()

        offer = state.current_offer
        if offer is None:
            return ResponseType.REJECT_OFFER

        t = state.relative_time

        # Track opponent offer
        offer_util = self._my_utilities.get(offer, float(self.ufun(offer)))
        self._last_received_offer = offer
        self._last_received_util = offer_util
        if offer_util > self._best_received_util:
            self._best_received_util = offer_util
            self._best_received_offer = offer

        # Update opponent model
        self._opp_model.update(offer, t)

        self._round += 1

        # Build shared state
        state_dict = self._build_state(t)

        # Select expert
        expert_idx = self._meta.select_expert(self._opp_model, t, self._round)
        expert = self._meta.get_expert(expert_idx)

        # Get what we would propose as a counter-offer (for AC_next)
        proposed = expert.propose(
            self._sorted_outcomes, self.ufun, self._opp_model, t, state_dict
        )
        proposed = self._verify_proposal(proposed)
        state_dict["planned_counter"] = proposed

        # Acceptance decision
        should_accept = self._acceptance.should_accept(
            offer, self.ufun, self._opp_model, expert, t, state_dict,
        )

        if should_accept:
            # Safety gate: double-check min_util floor
            if offer_util >= self._min_util:
                self._meta.update_reward(expert_idx, offer_util)
                return ResponseType.ACCEPT_OFFER

        return ResponseType.REJECT_OFFER

    def propose(self, state: SAOState, dest: str | None = None) -> Outcome:
        """Generate a proposal for the current negotiation state."""
        self._init_agent()

        t = state.relative_time
        state_dict = self._build_state(t)

        # Select expert via meta-controller
        expert_idx = self._meta.select_expert(self._opp_model, t, self._round)
        expert = self._meta.get_expert(expert_idx)

        # Get expert's proposed outcome
        proposed = expert.propose(
            self._sorted_outcomes, self.ufun, self._opp_model, t, state_dict
        )

        # Self-correction: verify and fix the proposal
        proposed = self._verify_proposal(proposed)

        # Track our offer for reciprocity detection
        u_proposed = self._my_utilities.get(proposed, float(self.ufun(proposed)))
        opp_util_est = self._opp_model.get_predicted_utility(proposed) if len(self._opp_model.offers) > 0 else 0.0
        self._opp_model.track_our_offer(u_proposed, opp_util_est)
        self._last_proposed_util = u_proposed
        self._proposal_history.append(u_proposed)

        # Provide reward signal to meta-controller
        self._meta.update_reward(expert_idx, u_proposed)

        return proposed

    # ── Self-correction & verification ────────────────────────────────

    def _verify_proposal(self, proposed: Outcome | None) -> Outcome:
        """
        Verify that a proposed outcome meets all constraints.
        If not, find the closest valid outcome.

        This is the "tool-use verification" step — ensures expert output
        is always valid before sending to the mechanism.
        """
        if proposed is None:
            return self._sorted_outcomes[0]

        u_proposed = self._my_utilities.get(proposed, float(self.ufun(proposed)))

        # Check: is the outcome in our known outcome space?
        if proposed not in self._my_utilities:
            # Unknown outcome — compute and cache utility
            u_proposed = float(self.ufun(proposed))
            self._my_utilities[proposed] = u_proposed

        # Check: does it meet min_util floor?
        if u_proposed < self._min_util:
            # Recovery: find the closest outcome above min_util
            # Start from the end of sorted_outcomes (lowest acceptable)
            for outcome in reversed(self._sorted_outcomes):
                u = self._my_utilities[outcome]
                if u >= self._min_util:
                    return outcome
            # Fallback: return best outcome
            return self._sorted_outcomes[0]

        return proposed

    # ── Helpers ───────────────────────────────────────────────────────

    def _build_state(self, t: float) -> dict[str, Any]:
        """Build the shared state dictionary for experts and acceptance controller."""
        return {
            "t": t,
            "round": self._round,
            "min_util": self._min_util,
            "max_util": self._max_util,
            "reservation": self._reservation,
            "best_received_util": self._best_received_util,
            "best_received_offer": self._best_received_offer,
            "last_received_util": self._last_received_util,
            "last_received_offer": self._last_received_offer,
            "sorted_outcomes": self._sorted_outcomes,
            "num_outcomes": len(self._sorted_outcomes),
            "planned_counter": None,
            "opponent_max_util": self._best_received_util,
            "last_proposed_util": self._last_proposed_util,
            "is_stalemate": self._opp_model.is_stalemate if hasattr(self._opp_model, 'is_stalemate') else False,
        }
