"""
Expert bidding strategies for the portfolio meta-controller — v2.

Five experts with improved concession curves and late-game behavior:
- E0: Boulware/Hardheaded (slower concession, but slightly faster than v1)
- E1: Pareto-friendly (maximize opponent utility at fixed self utility)
- E2: NiceTFT (reciprocal concession — NEW, targets MiCRO/TFT opponents)
- E3: Forecast-aware (adaptive concession based on opponent predictions)
- E4: DealSeeker (late-game specialist — NEW, maximizes agreement probability)

Changes from v1:
- Boulware e: 0.05 → 0.08 (slightly faster concession avoids stalemate)
- Pareto alpha: 0.30 → 0.35 (more opponent-aware for Pareto discovery)
- Removed old MiCRO expert (replaced by NiceTFT which handles TFT opponents
  better by explicitly matching opponent concession rate)
- Added DealSeeker for late-game agreement securing
- All experts now handle stalemate detection and emergency concession

Pure NegMAS implementation — outcomes are tuples, ufun is callable.
"""

from __future__ import annotations

from random import randint
from typing import Any, Callable

from negmas import Outcome
from negmas.preferences import UtilityFunction

from .opponent_model import OpponentModel


class ExpertBase:
    """Base class for expert strategies."""

    name: str = "base"

    def propose(
        self,
        sorted_outcomes: list[Outcome],
        ufun: UtilityFunction,
        opp_model: OpponentModel | None,
        t: float,
        state: dict[str, Any],
    ) -> Outcome | None:
        raise NotImplementedError

    def should_accept(
        self,
        offer: Outcome,
        ufun: UtilityFunction,
        opp_model: OpponentModel | None,
        t: float,
        state: dict[str, Any],
    ) -> bool:
        raise NotImplementedError

    def _get_utility(self, ufun: UtilityFunction, outcome: Outcome) -> float:
        """Get utility as float."""
        u = ufun(outcome)
        return float(u) if u is not None else 0.0

    def _get_target_utility(self, t: float, e: float, min_util: float, max_util: float) -> float:
        """
        Time-dependent aspiration: u(t) = min + (max - min) * (1 - t^(1/e))
        e < 1: Boulware (slow concession)
        e = 1: Linear
        e > 1: Conceder (fast concession)
        """
        if e <= 0:
            return max_util
        ft = 1.0 - (t ** (1.0 / e))
        ft = max(0.0, min(1.0, ft))
        return min_util + (max_util - min_util) * ft

    def _find_outcomes_in_range(
        self, sorted_outcomes: list[Outcome], ufun: UtilityFunction,
        target: float, tolerance: float = 0.05
    ) -> list[Outcome]:
        """Find outcomes with utility in [target - tolerance, target + tolerance]."""
        lower = target - tolerance
        upper = target + tolerance
        result = []
        for outcome in sorted_outcomes:
            u = self._get_utility(ufun, outcome)
            if u < lower:
                break  # sorted descending, all remaining are lower
            if u <= upper:
                result.append(outcome)
        return result

    def _pick_best_for_opponent(
        self, candidates: list[Outcome], ufun: UtilityFunction,
        opp_model: OpponentModel, alpha: float = 0.3,
    ) -> Outcome:
        """Pick outcome that maximizes (1-alpha)*self + alpha*opp among candidates."""
        best_score = -1.0
        best = candidates[0]
        for outcome in candidates:
            u_self = self._get_utility(ufun, outcome)
            u_opp = opp_model.get_predicted_utility(outcome)
            score = (1.0 - alpha) * u_self + alpha * u_opp
            if score > best_score:
                best_score = score
                best = outcome
        return best


class BoulwareExpert(ExpertBase):
    """
    E0: Hardheaded/Boulware expert.

    Concedes slowly (e=0.08, slightly faster than v1's 0.05), maintains
    high demands until late. Bid cycling among outcomes near target utility.
    Now with stalemate-aware boost.
    """

    name = "boulware"

    def __init__(self, e: float = 0.08):
        self.e = e

    def propose(self, sorted_outcomes, ufun, opp_model, t, state) -> Outcome | None:
        if not sorted_outcomes:
            return None

        min_util = state.get("min_util", 0.5)
        max_util = state.get("max_util", 1.0)

        # Stalemate boost: if opponent is stuck, concede much faster
        effective_e = self.e
        if opp_model is not None and opp_model.is_stalemate and t > 0.4:
            effective_e = min(self.e * 2.5, 0.30)

        target = self._get_target_utility(t, effective_e, min_util, max_util)

        candidates = self._find_outcomes_in_range(sorted_outcomes, ufun, target, tolerance=0.04)

        if not candidates:
            for outcome in sorted_outcomes:
                if self._get_utility(ufun, outcome) >= target:
                    candidates.append(outcome)
                if len(candidates) >= 10:
                    break
            if not candidates:
                candidates = [sorted_outcomes[0]]

        # Pick best for opponent among candidates (if opponent model available)
        if opp_model is not None and len(opp_model.offers) > 3 and len(candidates) > 1:
            return self._pick_best_for_opponent(candidates, ufun, opp_model, alpha=0.25)

        # Cycle through candidates
        return candidates[randint(0, len(candidates) - 1)]

    def should_accept(self, offer, ufun, opp_model, t, state) -> bool:
        if offer is None:
            return False
        u = self._get_utility(ufun, offer)
        min_util = state.get("min_util", 0.5)
        max_util = state.get("max_util", 1.0)
        target = self._get_target_utility(t, self.e, min_util, max_util)
        return u >= target and u >= min_util


class ParetoExpert(ExpertBase):
    """
    E1: Smart Pareto bidder.

    Selects outcomes that maximize estimated opponent utility while keeping
    our utility high. alpha=0.35 for better Pareto discovery.
    """

    name = "pareto"

    def __init__(self, e: float = 0.10, alpha: float = 0.30):
        self.e = e
        self.alpha = alpha

    def propose(self, sorted_outcomes, ufun, opp_model, t, state) -> Outcome | None:
        if not sorted_outcomes:
            return None

        min_util = state.get("min_util", 0.5)
        max_util = state.get("max_util", 1.0)
        target = self._get_target_utility(t, self.e, min_util, max_util)

        # Gather candidates at or above target
        candidates = []
        for outcome in sorted_outcomes:
            u = self._get_utility(ufun, outcome)
            if u < target:
                break
            candidates.append(outcome)
            if len(candidates) >= 200:
                break

        if not candidates:
            candidates = [sorted_outcomes[0]]

        # Score by combined self + opponent utility
        if opp_model is not None and len(opp_model.offers) > 3:
            # Increase alpha over time to become more cooperative
            dynamic_alpha = self.alpha + 0.10 * t  # 0.30 → 0.40
            return self._pick_best_for_opponent(candidates, ufun, opp_model, alpha=dynamic_alpha)
        else:
            return candidates[randint(0, len(candidates) - 1)]

    def should_accept(self, offer, ufun, opp_model, t, state) -> bool:
        if offer is None:
            return False
        u = self._get_utility(ufun, offer)
        min_util = state.get("min_util", 0.5)
        max_util = state.get("max_util", 1.0)
        target = self._get_target_utility(t, self.e, min_util, max_util)
        return u >= target and u >= min_util


class NiceTFTExpert(ExpertBase):
    """
    E2: Nice Tit-for-Tat expert (replaces old MiCRO expert).

    Concedes in proportion to opponent's concession. Starts near top,
    tracks opponent's concession and mirrors it. Specifically designed
    to handle MiCRO and TitForTat opponents who only concede when we do.

    Key idea: instead of pure "concede only when opponent proposes new",
    actively track concession AMOUNT and match rate, proposing outcomes
    that show good faith.
    """

    name = "nice_tft"

    def __init__(self):
        self.num_proposed: int = 0
        self._our_concession_idx: int = 0  # tracks how far we've conceded

    def propose(self, sorted_outcomes, ufun, opp_model, t, state) -> Outcome | None:
        if not sorted_outcomes:
            return None

        min_util = state.get("min_util", 0.5)
        max_util = state.get("max_util", 1.0)
        reservation = state.get("reservation", 0.0)

        # Compute how much opponent has conceded (relative to their starting utility)
        opp_concession_fraction = 0.0
        if opp_model is not None and len(opp_model.offer_utilities) >= 3:
            first_few = opp_model.offer_utilities[:3]
            recent_few = opp_model.offer_utilities[-3:]
            start_util = sum(first_few) / len(first_few)
            current_util = sum(recent_few) / len(recent_few)
            if start_util > 0.01:
                opp_concession_fraction = max(0.0, (start_util - current_util) / start_util)

        # Match opponent's concession: our target drops proportionally
        # But always concede significantly to trigger reciprocation
        base_concession = 0.04 + 0.08 * t  # moderate base concession
        matched_concession = opp_concession_fraction * 1.1  # slightly outpace opponent
        total_concession = min(
            base_concession + matched_concession,
            0.45  # cap: allow up to 45% of range
        )

        target = max_util - (max_util - min_util) * total_concession
        target = max(target, min_util)

        # Stalemate? Concede more to break deadlock
        if opp_model is not None and opp_model.is_stalemate:
            target = max(target * 0.88, min_util)

        candidates = self._find_outcomes_in_range(sorted_outcomes, ufun, target, tolerance=0.05)

        if not candidates:
            for outcome in sorted_outcomes:
                u = self._get_utility(ufun, outcome)
                if u >= target:
                    candidates.append(outcome)
                if len(candidates) >= 10:
                    break
            if not candidates:
                # Find closest outcome above min_util
                for outcome in sorted_outcomes:
                    u = self._get_utility(ufun, outcome)
                    if u >= min_util:
                        candidates.append(outcome)
                        break
                if not candidates:
                    candidates = [sorted_outcomes[0]]

        # Pick one that's good for opponent (reciprocal gesture)
        if opp_model is not None and len(opp_model.offers) > 3 and len(candidates) > 1:
            # Prefer outcomes the opponent has already proposed (signal convergence)
            for outcome in candidates:
                if outcome in opp_model.unique_offers:
                    return outcome
            # Otherwise pick best for opponent
            return self._pick_best_for_opponent(candidates, ufun, opp_model, alpha=0.35)

        self.num_proposed += 1
        return candidates[randint(0, len(candidates) - 1)]

    def should_accept(self, offer, ufun, opp_model, t, state) -> bool:
        if offer is None:
            return False
        u = self._get_utility(ufun, offer)
        min_util = state.get("min_util", 0.5)
        max_util = state.get("max_util", 1.0)

        if u < min_util:
            return False

        # Accept if above our current aspiration (moderate time-based)
        target = max_util - (max_util - min_util) * (0.04 + 0.08 * t)

        # Factor in opponent concession matching
        if opp_model is not None and len(opp_model.offer_utilities) >= 3:
            first_few = opp_model.offer_utilities[:3]
            recent_few = opp_model.offer_utilities[-3:]
            start_util = sum(first_few) / len(first_few)
            current_util = sum(recent_few) / len(recent_few)
            if start_util > 0.01:
                opp_concession = max(0.0, (start_util - current_util) / start_util)
                target = max_util - (max_util - min_util) * (0.04 + opp_concession * 1.1)
                target = max(target, min_util)

        return u >= target


class ForecastExpert(ExpertBase):
    """
    E3: Forecast-aware expert.

    Adjusts concession based on predicted opponent behavior. If opponent
    is predicted to concede more, we can be tougher; if opponent is stubborn,
    we adjust to secure an agreement.

    v2 changes:
    - base_e: 0.08 → 0.10 (slightly faster default concession)
    - Against hardheaded: stronger concession acceleration in late game
    - Better stalemate awareness
    """

    name = "forecast"

    def __init__(self, base_e: float = 0.10):
        self.base_e = base_e  # tighter default — hold ground

    def _adaptive_e(self, opp_model: OpponentModel | None, t: float) -> float:
        """Adjust concession exponent based on opponent behavior."""
        if opp_model is None or len(opp_model.offers) < 8:
            return self.base_e

        features = opp_model.get_style_features()

        # Stalemate override: concede faster
        if features.get("is_stalemate", False) and t > 0.4:
            return self.base_e * 2.5

        if features["is_hardheaded"]:
            if t > 0.80:
                return self.base_e * 2.5  # accelerate late vs hardheaded
            elif t > 0.6:
                return self.base_e * 1.5
            return self.base_e * 1.1

        if features.get("is_tft_style", False):
            # Mirror: moderate concession to trigger reciprocation
            return self.base_e * 1.3

        if features["is_conceder"]:
            return self.base_e * 0.5  # hold ground vs conceders

        cr = features["concession_rate"]
        if cr > 0.1:
            return self.base_e * 0.6
        elif cr < -0.05:
            return self.base_e * 1.2
        return self.base_e * 0.9

    def propose(self, sorted_outcomes, ufun, opp_model, t, state) -> Outcome | None:
        if not sorted_outcomes:
            return None

        min_util = state.get("min_util", 0.5)
        max_util = state.get("max_util", 1.0)
        e = self._adaptive_e(opp_model, t)
        target = self._get_target_utility(t, e, min_util, max_util)

        # Use opponent model to predict future and adjust
        if opp_model and len(opp_model.offers) > 5:
            predicted_opp_floor = opp_model.predict_future_concession(t)
            if predicted_opp_floor < 0.5:
                target = max(target, min_util + 0.05)

        candidates = self._find_outcomes_in_range(sorted_outcomes, ufun, target, tolerance=0.05)

        if not candidates:
            for outcome in sorted_outcomes:
                if self._get_utility(ufun, outcome) >= target:
                    candidates.append(outcome)
                if len(candidates) >= 10:
                    break
            if not candidates:
                candidates = [sorted_outcomes[0]]

        # Score candidates using opponent model
        if opp_model and len(opp_model.offers) > 3:
            alpha = min(0.4, 0.20 + 0.20 * t)
            return self._pick_best_for_opponent(candidates, ufun, opp_model, alpha=alpha)

        return candidates[randint(0, len(candidates) - 1)]

    def should_accept(self, offer, ufun, opp_model, t, state) -> bool:
        if offer is None:
            return False
        u = self._get_utility(ufun, offer)
        min_util = state.get("min_util", 0.5)
        max_util = state.get("max_util", 1.0)
        reservation = state.get("reservation", 0.0)

        if u < reservation:
            return False

        e = self._adaptive_e(opp_model, t)
        target = self._get_target_utility(t, e, min_util, max_util)

        if opp_model and len(opp_model.offers) > 5:
            best_received = state.get("best_received_util", 0.0)
            if t > 0.90 and u >= best_received * 0.98:
                return True
            return u >= target

        return u >= target


class DealSeekerExpert(ExpertBase):
    """
    E4: Late-game deal-seeking specialist (NEW).

    Designed specifically for the last 15-20% of negotiation to maximize
    the probability of reaching an agreement. Aggressively searches for
    mutually acceptable outcomes, even at some self-utility cost.

    Strategy:
    - Rapidly concede to find overlap zone
    - Propose outcomes that were previously offered by opponent (if acceptable)
    - Use large tolerance window to find any acceptable deal
    """

    name = "deal_seeker"

    def propose(self, sorted_outcomes, ufun, opp_model, t, state) -> Outcome | None:
        if not sorted_outcomes:
            return None

        min_util = state.get("min_util", 0.5)
        max_util = state.get("max_util", 1.0)
        best_received = state.get("best_received_util", 0.0)

        # Target: rapidly decrease from max_util to min_util
        # Using time since entry (assumed t > 0.82)
        t_late = min(max((t - 0.82) / 0.18, 0.0), 1.0)  # 0 at 0.82, 1 at 1.0
        target = max_util - (max_util - min_util) * (0.15 + 0.85 * t_late)
        target = max(target, min_util)

        # PRIORITY 1: propose opponent's best offer if it's acceptable to us
        if opp_model is not None and len(opp_model.offers) > 0:
            # Find opponent's offers that we'd accept
            acceptable_opp_offers = []
            for opp_offer in opp_model.unique_offers:
                u = self._get_utility(ufun, opp_offer)
                if u >= target:
                    acceptable_opp_offers.append((u, opp_offer))

            if acceptable_opp_offers:
                # Pick the one that's best for both parties
                acceptable_opp_offers.sort(key=lambda x: x[0], reverse=True)
                # Return best self-utility among acceptable opponent offers
                return acceptable_opp_offers[0][1]

        # PRIORITY 2: find outcomes near the overlap zone
        candidates = self._find_outcomes_in_range(sorted_outcomes, ufun, target, tolerance=0.08)

        if not candidates:
            # Widen search
            for outcome in sorted_outcomes:
                u = self._get_utility(ufun, outcome)
                if u >= min_util:
                    candidates.append(outcome)
                if len(candidates) >= 30:
                    break
            if not candidates:
                candidates = [sorted_outcomes[0]]

        # Pick the most opponent-friendly candidate
        if opp_model is not None and len(opp_model.offers) > 3:
            return self._pick_best_for_opponent(candidates, ufun, opp_model, alpha=0.45)

        return candidates[randint(0, len(candidates) - 1)]

    def should_accept(self, offer, ufun, opp_model, t, state) -> bool:
        """DealSeeker is ready to accept any offer above min_util."""
        if offer is None:
            return False
        u = self._get_utility(ufun, offer)
        min_util = state.get("min_util", 0.5)
        return u >= min_util
