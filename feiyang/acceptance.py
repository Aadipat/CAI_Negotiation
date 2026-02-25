"""
Composite acceptance controller — v4 tuned for higher self-utility.

Combines multiple acceptance conditions inspired by top ANAC agents:
1. Sliding threshold: linearly decrease from initial_threshold to final_threshold
2. No early acceptance: 2 rounds (build opponent model)
3. AC_next: accept if u(offer) >= u(planned counter-offer) with tolerance
4. Emergency acceptance: starts at t=0.88, progressive lowering
5. Stalemate breaker: when opponent is stuck, lower bar moderately
6. TFT-aware: when opponent reciprocates, be more accepting
7. Last-resort at t>=0.95

v4 changes (utility-maximising):
- initial_threshold: 0.88 → 0.92 (hold ground longer)
- final_threshold: 0.40 → 0.50 (never accept below 50%)
- emergency_time: 0.80 → 0.88 (later panic)
- Removed AC_midgame (was accepting 0.65 at t>0.60 — too lenient!)
- Tightened stalemate threshold (*0.75 → *0.85)
- Tightened reciprocal threshold (*0.80 → *0.90)
- Last-resort pushed from t>=0.92 to t>=0.95

Safety gates:
- NEVER accept below reservation value
- NEVER accept below hard min_util floor
"""

from __future__ import annotations

from typing import Any

from negmas import Outcome
from negmas.preferences import UtilityFunction

from .opponent_model import OpponentModel
from .experts import ExpertBase


class AcceptanceController:
    """
    Composite acceptance decision engine — v4 for higher self-utility.
    """

    def __init__(
        self,
        reservation: float = 0.0,
        min_util: float = 0.30,
        initial_threshold: float = 0.92,
        final_threshold: float = 0.50,
        no_accept_rounds: int = 2,
        emergency_time: float = 0.88,
        emergency_floor: float = 0.0,
    ):
        self.reservation = reservation
        self.min_util = min_util
        self.initial_threshold = initial_threshold
        self.final_threshold = max(final_threshold, min_util)
        self.no_accept_rounds = no_accept_rounds
        self.emergency_time = emergency_time
        self.emergency_floor = max(emergency_floor, reservation, min_util * 0.90)

    def should_accept(
        self,
        offer: Outcome,
        ufun: UtilityFunction,
        opp_model: OpponentModel | None,
        expert: ExpertBase,
        t: float,
        state: dict[str, Any],
    ) -> bool:
        """
        Determine whether to accept the given offer.

        Returns True only when strategically sound AND above utility floor.
        """
        if offer is None:
            return False

        u = float(ufun(offer))
        round_num = state.get("round", 0)

        # === HARD CONSTRAINTS (never violated) ===
        if u < self.reservation:
            return False
        if u < self.min_util:
            return False

        # === Don't accept in the first rounds ===
        if round_num <= self.no_accept_rounds:
            return False

        # === Compute sliding acceptance threshold ===
        threshold = max(
            self.initial_threshold
            - (self.initial_threshold - self.final_threshold) * t,
            self.final_threshold,
        )

        # === AC_threshold: accept if above sliding threshold ===
        if u >= threshold:
            return True

        # === AC_next: accept if offer >= planned counter-offer ===
        planned_counter = state.get("planned_counter", None)
        if planned_counter is not None:
            u_counter = float(ufun(planned_counter))
            # Accept if offer beats our counter AND is near threshold
            if u >= u_counter and u >= threshold * 0.93:
                return True

        # === AC_expert: let expert weigh in ===
        if expert.should_accept(offer, ufun, opp_model, t, state):
            if u >= threshold * 0.90:
                return True

        # === AC_stalemate: break stalemate by accepting decent offers ===
        is_stalemate = state.get("is_stalemate", False)
        if opp_model is not None and (opp_model.is_stalemate or is_stalemate):
            stalemate_threshold = max(
                self.final_threshold,
                threshold * 0.85,
            )
            if u >= stalemate_threshold:
                return True

        # === AC_reciprocal: if opponent keeps offering same thing, consider accepting ===
        if opp_model is not None and opp_model._consecutive_repeats >= 3:
            if u >= max(self.final_threshold, threshold * 0.90):
                return True

        # === AC_best_received: near deadline, accept near best seen ===
        best_received = state.get("best_received_util", 0.0)
        if t > 0.80 and u >= best_received * 0.98 and u >= self.final_threshold:
            return True

        # === AC_emergency: progressive emergency acceptance ===
        if t >= self.emergency_time:
            remaining = max(1.0 - t, 0.001)
            total_emergency = max(1.0 - self.emergency_time, 0.001)
            progress = 1.0 - (remaining / total_emergency)

            # Linearly interpolate between threshold and emergency_floor
            emergency_thresh = threshold - (threshold - self.emergency_floor) * progress

            if best_received > emergency_thresh:
                tolerance = 0.05 + 0.10 * progress
                if u >= best_received * (1.0 - tolerance):
                    return True

            if u >= emergency_thresh:
                return True

            # Last-resort: at t > 0.95, accept anything above hard floor
            if t >= 0.95:
                hard_floor = max(self.reservation, self.min_util)
                if u >= hard_floor:
                    return True

        return False

    def update_reservation(self, new_reservation: float):
        """Update the reservation value."""
        self.reservation = new_reservation
        self.emergency_floor = max(new_reservation, self.min_util * 0.90)
