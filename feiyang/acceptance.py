"""
Composite acceptance controller.

Combines multiple acceptance conditions:
1. AC_next: accept if u(offer) >= u(our planned counter-offer) AND above floor
2. Expert vote: let the selected expert vote on acceptance
3. AC_future: approaching deadline, accept if offer is near best received
4. AC_emergency: very near deadline, accept above floor to avoid no-deal

Safety gates:
- NEVER accept below reservation value
- NEVER accept below min_util floor (hard aspiration minimum)
"""

from __future__ import annotations

from typing import Any

from geniusweb.issuevalue.Bid import Bid
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive

from .opponent_model import OpponentModel
from .experts import ExpertBase


class AcceptanceController:
    """
    Composite acceptance decision engine.

    Much tighter than before: ensures we never accept offers that are
    too far below our aspiration. Key change: hard utility floor that
    prevents over-concession.
    """

    def __init__(
        self,
        reservation: float = 0.0,
        min_util: float = 0.55,
        emergency_time: float = 0.98,
        emergency_floor: float = 0.0,
    ):
        self.reservation = reservation
        self.min_util = min_util  # Hard floor: never accept below this
        self.emergency_time = emergency_time
        self.emergency_floor = max(emergency_floor, min_util * 0.85)

    def should_accept(
        self,
        bid: Bid,
        profile: LinearAdditive,
        opp_model: OpponentModel | None,
        expert: ExpertBase,
        t: float,
        state: dict[str, Any],
    ) -> bool:
        """
        Determine whether to accept the given bid.

        Returns True only when strategically sound AND above utility floor.
        """
        if bid is None:
            return False

        # Get our utility for this offer
        u = float(profile.getUtility(bid))

        # === HARD CONSTRAINTS ===
        # Never accept below reservation value
        if u < self.reservation:
            return False
        # Never accept below our hard utility floor
        if u < self.min_util:
            return False

        # === AC_next: Accept if u(offer) >= u(our planned counter-offer) ===
        # Only if our counter-offer is also above the floor
        planned_counter = state.get("planned_counter", None)
        if planned_counter is not None:
            u_counter = float(profile.getUtility(planned_counter))
            if u >= u_counter and u >= self.min_util:
                return True

        # === AC_threshold: Expert's acceptance recommendation ===
        if expert.should_accept(bid, profile, opp_model, t, state):
            return True

        # === AC_future: Only very late, accept offers close to best received ===
        best_received = state.get("best_received_util", 0.0)
        if t > 0.95 and u >= best_received * 0.995:
            return True

        # === AC_emergency: Very near deadline, accept above emergency floor ===
        if t >= self.emergency_time:
            # Use a high emergency threshold to avoid giving away utility
            emergency_threshold = max(self.reservation, self.emergency_floor)
            # Linear ramp: start at best_received level, decrease toward floor
            remaining = 1.0 - t
            total_emergency = 1.0 - self.emergency_time
            if total_emergency > 0:
                patience = remaining / total_emergency
            else:
                patience = 0.0
            dynamic_floor = emergency_threshold + (best_received - emergency_threshold) * patience * 0.7
            if u >= dynamic_floor:
                return True

        return False

    def update_reservation(self, new_reservation: float):
        """Update the reservation value."""
        self.reservation = new_reservation
        self.emergency_floor = max(new_reservation, self.min_util * 0.85)
