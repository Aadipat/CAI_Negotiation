"""
Expert bidding strategies for the portfolio meta-controller.

Each expert implements the same interface:
    propose(sorted_bids, profile, opponent_model, t, state_info) -> Bid | None
    should_accept(bid, profile, opponent_model, t, state_info) -> bool

Experts:
- E1: Boulware/Hardheaded (pressure late, concede slowly)
- E2: Pareto-friendly (maximize opponent utility at fixed self utility)
- E3: MiCRO (simple tit-for-tat concession)
- E4: Forecast-aware (adjust based on predicted opponent concession)
"""

from __future__ import annotations

import math
from random import randint, random
from decimal import Decimal
from typing import Any

from geniusweb.issuevalue.Bid import Bid
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive

from .opponent_model import OpponentModel


class ExpertBase:
    """Base class for expert strategies."""

    name: str = "base"

    def propose(
        self,
        sorted_bids: list[Bid],
        profile: LinearAdditive,
        opp_model: OpponentModel | None,
        t: float,
        state: dict[str, Any],
    ) -> Bid | None:
        raise NotImplementedError

    def should_accept(
        self,
        bid: Bid,
        profile: LinearAdditive,
        opp_model: OpponentModel | None,
        t: float,
        state: dict[str, Any],
    ) -> bool:
        raise NotImplementedError

    def _get_utility(self, profile: LinearAdditive, bid: Bid) -> float:
        """Get utility as float."""
        u = profile.getUtility(bid)
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

    def _find_bids_in_range(
        self, sorted_bids: list[Bid], profile: LinearAdditive,
        target: float, tolerance: float = 0.05
    ) -> list[Bid]:
        """Find bids with utility in [target - tolerance, target + tolerance]."""
        lower = target - tolerance
        upper = target + tolerance
        result = []
        for bid in sorted_bids:
            u = self._get_utility(profile, bid)
            if u < lower:
                break  # sorted descending, all remaining are lower
            if u <= upper:
                result.append(bid)
        return result


class BoulwareExpert(ExpertBase):
    """
    E1: Hardheaded/Boulware expert.

    Concedes very slowly (e=0.08), maintains high demands until late.
    Inspired by HardHeaded (ANAC 2011 winner) — late concession, bid cycling.
    """

    name = "boulware"

    def __init__(self, e: float = 0.08):
        self.e = e

    def propose(self, sorted_bids, profile, opp_model, t, state) -> Bid | None:
        if not sorted_bids:
            return None

        min_util = state.get("min_util", 0.6)
        max_util = state.get("max_util", 1.0)
        target = self._get_target_utility(t, self.e, min_util, max_util)

        candidates = self._find_bids_in_range(sorted_bids, profile, target, tolerance=0.02)

        if not candidates:
            # Fall back to best bid above target
            for bid in sorted_bids:
                if self._get_utility(profile, bid) >= target:
                    candidates.append(bid)
                if len(candidates) >= 5:
                    break
            if not candidates:
                candidates = [sorted_bids[0]]

        # Pick best for opponent among candidates (if opponent model available)
        if opp_model is not None and len(opp_model.offers) > 3 and len(candidates) > 1:
            best_score = -1.0
            best_bid = candidates[0]
            for bid in candidates:
                opp_u = opp_model.get_predicted_utility(bid)
                if opp_u > best_score:
                    best_score = opp_u
                    best_bid = bid
            return best_bid

        # Cycle through candidates (hardheaded pattern)
        return candidates[randint(0, len(candidates) - 1)]

    def should_accept(self, bid, profile, opp_model, t, state) -> bool:
        if bid is None:
            return False
        u = self._get_utility(profile, bid)
        min_util = state.get("min_util", 0.6)
        max_util = state.get("max_util", 1.0)
        target = self._get_target_utility(t, self.e, min_util, max_util)
        # Only accept if at or above our aspiration
        return u >= target and u >= min_util


class ParetoExpert(ExpertBase):
    """
    E2: Smart Pareto bidder.

    Selects bids that maximize estimated opponent utility while keeping
    our utility high. Less generous than before — alpha reduced.
    """

    name = "pareto"

    def __init__(self, e: float = 0.15, alpha: float = 0.2):
        """
        Args:
            e: concession exponent (slow, like boulware)
            alpha: weight on opponent utility in scoring (reduced from 0.4 to 0.2)
        """
        self.e = e
        self.alpha = alpha

    def propose(self, sorted_bids, profile, opp_model, t, state) -> Bid | None:
        if not sorted_bids:
            return None

        min_util = state.get("min_util", 0.6)
        max_util = state.get("max_util", 1.0)
        target = self._get_target_utility(t, self.e, min_util, max_util)

        # Gather candidates strictly at or above target
        candidates = []
        for bid in sorted_bids:
            u = self._get_utility(profile, bid)
            if u < target:
                break
            candidates.append(bid)
            if len(candidates) >= 200:
                break

        if not candidates:
            candidates = [sorted_bids[0]]

        # Score by combined self + opponent utility
        if opp_model is not None and len(opp_model.offers) > 3:
            best_score = -1.0
            best_bid = candidates[0]
            for bid in candidates:
                u_self = self._get_utility(profile, bid)
                u_opp = opp_model.get_predicted_utility(bid)
                score = (1.0 - self.alpha) * u_self + self.alpha * u_opp
                if score > best_score:
                    best_score = score
                    best_bid = bid
            return best_bid
        else:
            return candidates[randint(0, len(candidates) - 1)]

    def should_accept(self, bid, profile, opp_model, t, state) -> bool:
        if bid is None:
            return False
        u = self._get_utility(profile, bid)
        min_util = state.get("min_util", 0.6)
        max_util = state.get("max_util", 1.0)
        target = self._get_target_utility(t, self.e, min_util, max_util)
        return u >= target and u >= min_util


class MiCROExpert(ExpertBase):
    """
    E3: MiCRO-style expert.

    Proposes bids in decreasing utility order; concedes only when
    opponent makes new proposals (tit-for-tat concession). Ultra-simple
    but competitive baseline.
    """

    name = "micro"

    def __init__(self):
        self.num_proposed: int = 0
        self.received_unique: set[str] = set()

    def propose(self, sorted_bids, profile, opp_model, t, state) -> Bid | None:
        if not sorted_bids:
            return None

        reservation = state.get("reservation", 0.0)

        # Tit-for-tat: concede only if opponent has made at least as many unique proposals
        if opp_model is not None:
            opp_unique = len(opp_model.unique_offers)
        else:
            opp_unique = self.num_proposed

        ready_to_concede = self.num_proposed <= opp_unique
        next_idx = min(self.num_proposed, len(sorted_bids) - 1)
        next_bid = sorted_bids[next_idx]
        next_util = self._get_utility(profile, next_bid)

        if ready_to_concede and next_util > reservation:
            # Try to pick a bid the opponent already proposed at same utility
            if opp_model is not None:
                for i in range(next_idx, min(next_idx + 20, len(sorted_bids))):
                    alt = sorted_bids[i]
                    alt_util = self._get_utility(profile, alt)
                    if abs(alt_util - next_util) < 0.001:
                        if str(alt) in opp_model.unique_offers:
                            next_bid = alt
                            break
                    elif alt_util < next_util - 0.001:
                        break

            self.num_proposed += 1
            return next_bid
        else:
            # Repeat a previous bid
            if self.num_proposed > 0:
                idx = randint(0, self.num_proposed - 1)
                return sorted_bids[min(idx, len(sorted_bids) - 1)]
            return sorted_bids[0]

    def should_accept(self, bid, profile, opp_model, t, state) -> bool:
        if bid is None:
            return False
        u = self._get_utility(profile, bid)
        min_util = state.get("min_util", 0.6)

        if u < min_util:
            return False

        if opp_model is not None:
            opp_unique = len(opp_model.unique_offers)
        else:
            opp_unique = self.num_proposed

        ready_to_concede = self.num_proposed <= opp_unique
        threshold_idx = self.num_proposed if ready_to_concede else max(0, self.num_proposed - 1)
        threshold_idx = min(threshold_idx, len(state.get("sorted_bids", [])) - 1)

        sorted_bids = state.get("sorted_bids", [])
        if sorted_bids and threshold_idx >= 0:
            threshold_util = self._get_utility(profile, sorted_bids[threshold_idx])
            return u >= threshold_util
        return u >= 0.8


class ForecastExpert(ExpertBase):
    """
    E4: Forecast-aware expert.

    Adjusts concession based on predicted opponent behavior. If opponent
    is predicted to concede more, we can be tougher; if opponent is stubborn,
    we adjust to secure an agreement. Inspired by IAMhaggler (ANAC 2011).
    """

    name = "forecast"

    def __init__(self, base_e: float = 0.12):
        self.base_e = base_e

    def _adaptive_e(self, opp_model: OpponentModel | None, t: float) -> float:
        """Adjust concession exponent based on opponent behavior."""
        if opp_model is None or len(opp_model.offers) < 10:
            return self.base_e

        features = opp_model.get_style_features()

        if features["is_hardheaded"]:
            # Against hardheaded: concede a bit more but never drastically
            if t > 0.9:
                return self.base_e * 2.0  # modest increase near deadline
            return self.base_e * 1.2
        elif features["is_conceder"]:
            # Against conceder: stay tough, they'll come to us
            return self.base_e * 0.5
        else:
            # Moderate: match concession rate
            cr = features["concession_rate"]
            if cr > 0.1:
                return self.base_e * 0.6  # opponent conceding, stay firm
            elif cr < -0.05:
                return self.base_e * 1.1  # opponent hardening, slight concession
            return self.base_e

    def propose(self, sorted_bids, profile, opp_model, t, state) -> Bid | None:
        if not sorted_bids:
            return None

        min_util = state.get("min_util", 0.6)
        max_util = state.get("max_util", 1.0)
        e = self._adaptive_e(opp_model, t)
        target = self._get_target_utility(t, e, min_util, max_util)

        # Use opponent model to predict future and adjust
        if opp_model and len(opp_model.offers) > 5:
            predicted_opp_floor = opp_model.predict_future_concession(t)
            # If opponent is predicted to concede, we can aim higher
            if predicted_opp_floor < 0.5:
                target = max(target, min_util + 0.1)

        candidates = self._find_bids_in_range(sorted_bids, profile, target, tolerance=0.05)

        if not candidates:
            for bid in sorted_bids:
                if self._get_utility(profile, bid) >= target:
                    candidates.append(bid)
                if len(candidates) >= 10:
                    break
            if not candidates:
                candidates = [sorted_bids[0]]

        # Score candidates using opponent model
        if opp_model and len(opp_model.offers) > 3:
            best_score = -1.0
            best_bid = candidates[0]
            for bid in candidates:
                u_self = self._get_utility(profile, bid)
                u_opp = opp_model.get_predicted_utility(bid)
                # More weight on opponent as time increases
                alpha = min(0.5, 0.2 + 0.3 * t)
                score = (1.0 - alpha) * u_self + alpha * u_opp
                if score > best_score:
                    best_score = score
                    best_bid = bid
            return best_bid

        return candidates[randint(0, len(candidates) - 1)]

    def should_accept(self, bid, profile, opp_model, t, state) -> bool:
        if bid is None:
            return False
        u = self._get_utility(profile, bid)
        min_util = state.get("min_util", 0.6)
        max_util = state.get("max_util", 1.0)
        reservation = state.get("reservation", 0.0)

        if u < reservation:
            return False

        e = self._adaptive_e(opp_model, t)
        target = self._get_target_utility(t, e, min_util, max_util)

        # Future-aware: accept if this is better than what we predict we can get
        if opp_model and len(opp_model.offers) > 5:
            # Best received so far
            best_received = state.get("best_received_util", 0.0)
            # Accept only very late if current offer is at least 99% of best
            if t > 0.95 and u >= best_received * 0.99:
                return True
            # Accept if above target
            if u >= target:
                return True
            return False

        return u >= target
