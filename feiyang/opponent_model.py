"""
Frequency-based opponent model for preference estimation.

Tracks how often each issue-value pair appears in opponent bids,
and estimates opponent utility using frequency counts, issue weight
estimation via concentration metrics, and concession trend tracking.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import TYPE_CHECKING

from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value
from geniusweb.issuevalue.DiscreteValueSet import DiscreteValueSet


class ValueEstimator:
    """Tracks frequency of a single issue-value and estimates its utility."""

    def __init__(self):
        self.count: int = 0
        self.utility: float = 0.0

    def update(self):
        self.count += 1

    def recalculate_utility(self, max_value_count: int, weight: float):
        """Recalculate utility using smoothed frequency ratio."""
        if max_value_count == 0:
            self.utility = 0.0
            return
        if weight < 1.0:
            mod_value = ((self.count + 1) ** (1.0 - weight)) - 1.0
            mod_max = ((max_value_count + 1) ** (1.0 - weight)) - 1.0
            self.utility = mod_value / mod_max if mod_max > 0 else 0.0
        else:
            self.utility = 1.0 if self.count == max_value_count else 0.0


class IssueEstimator:
    """Estimates opponent preference weight and value utilities for one issue."""

    def __init__(self, value_set):
        self.bids_received: int = 0
        self.max_value_count: int = 0
        self.num_values: int = value_set.size() if hasattr(value_set, 'size') else len(value_set)
        self.value_trackers: dict[Value, ValueEstimator] = defaultdict(ValueEstimator)
        self.weight: float = 0.0

    def update(self, value: Value):
        self.bids_received += 1
        tracker = self.value_trackers[value]
        tracker.update()
        self.max_value_count = max(tracker.count, self.max_value_count)

        # Weight = how concentrated the opponent's choices are on this issue
        equal_shares = self.bids_received / max(self.num_values, 1)
        denom = self.bids_received - equal_shares
        if denom > 0:
            self.weight = (self.max_value_count - equal_shares) / denom
        else:
            self.weight = 0.0

        # Recalculate all value utilities
        for vt in self.value_trackers.values():
            vt.recalculate_utility(self.max_value_count, self.weight)

    def get_value_utility(self, value: Value) -> float:
        if value in self.value_trackers:
            return self.value_trackers[value].utility
        return 0.0


class OpponentModel:
    """
    Frequency-based opponent model.

    Tracks opponent bids to estimate:
    - Per-issue weights (how important each issue is to the opponent)
    - Per-value utilities (how much the opponent values each option)
    - Concession trends over time
    - Opponent style classification
    """

    def __init__(self, domain: Domain):
        self.domain = domain
        self.offers: list[Bid] = []
        self.offer_utilities: list[float] = []  # estimated opp utilities over time
        self.unique_offers: set[str] = set()

        # Per-issue estimators
        self.issue_estimators: dict[str, IssueEstimator] = {}
        for issue_id, value_set in domain.getIssuesValues().items():
            self.issue_estimators[issue_id] = IssueEstimator(value_set)

        # Concession tracking
        self.time_segments: int = 40
        self.segment_sums: list[float] = [0.0] * self.time_segments
        self.segment_counts: list[int] = [0] * self.time_segments
        self.segment_unique: list[int] = [0] * self.time_segments
        self._segment_seen: set[str] = set()
        self._current_segment: int = 0

        # Style classification
        self.is_hardheaded: bool = False
        self.is_conceder: bool = False
        self.is_micro_style: bool = False
        self.concession_rate: float = 0.0  # positive = conceding, negative = hardening

    def update(self, bid: Bid, normalized_time: float):
        """Update model with a new opponent bid."""
        if bid is None:
            return

        self.offers.append(bid)
        bid_key = str(bid)

        # Update issue estimators
        for issue_id, estimator in self.issue_estimators.items():
            value = bid.getValue(issue_id)
            if value is not None:
                estimator.update(value)

        # Track estimated utility
        est_util = self.get_predicted_utility(bid)
        self.offer_utilities.append(est_util)

        # Track uniqueness
        is_new = bid_key not in self.unique_offers
        self.unique_offers.add(bid_key)

        # Time segment tracking
        if normalized_time > 0.2:
            seg_idx = min(
                int((self.time_segments - 1) * ((normalized_time - 0.2) / 0.8)),
                self.time_segments - 1,
            )
            self.segment_sums[seg_idx] += est_util
            self.segment_counts[seg_idx] += 1
            if is_new:
                self.segment_unique[seg_idx] += 1

            if seg_idx > self._current_segment:
                self._segment_seen.clear()
                self._current_segment = seg_idx

        # Update style classification periodically
        if len(self.offers) >= 10:
            self._classify_style()

    def get_predicted_utility(self, bid: Bid) -> float:
        """Estimate how much the opponent values a given bid."""
        if bid is None or len(self.offers) == 0:
            return 0.0

        total_weight = 0.0
        weighted_util = 0.0

        for issue_id, estimator in self.issue_estimators.items():
            value = bid.getValue(issue_id)
            if value is not None:
                vu = estimator.get_value_utility(value)
                w = estimator.weight
                weighted_util += vu * w
                total_weight += w

        if total_weight == 0.0:
            # Fallback: equal weights
            n = len(self.issue_estimators)
            if n == 0:
                return 0.0
            for issue_id, estimator in self.issue_estimators.items():
                value = bid.getValue(issue_id)
                if value is not None:
                    weighted_util += estimator.get_value_utility(value) / n
            return weighted_util

        return weighted_util / total_weight

    def get_average_segment_utility(self, segment: int) -> float:
        """Get average estimated opponent utility for a time segment."""
        seg = max(0, min(segment, self.time_segments - 1))
        if self.segment_counts[seg] > 0:
            return self.segment_sums[seg] / self.segment_counts[seg]
        return 0.0

    def get_current_opponent_threshold(self) -> float:
        """Estimate opponent's current utility threshold based on recent segments."""
        if self._current_segment <= 0:
            return 0.8
        # Look at last few segments
        recent_avg = 0.0
        count = 0
        for i in range(max(0, self._current_segment - 3), self._current_segment + 1):
            avg = self.get_average_segment_utility(i)
            if avg > 0:
                recent_avg += avg
                count += 1
        if count > 0:
            return max(recent_avg / count, 0.5)
        return 0.8

    def predict_future_concession(self, current_time: float, deadline: float = 1.0) -> float:
        """
        Predict how much the opponent will concede by the deadline.
        Returns estimated minimum opponent utility threshold at deadline.
        """
        if len(self.offer_utilities) < 5:
            return 0.5  # conservative default

        # Use linear regression on recent utilities
        n = min(len(self.offer_utilities), 20)
        recent = self.offer_utilities[-n:]
        x_mean = (n - 1) / 2.0
        y_mean = sum(recent) / n
        num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(recent))
        denom = sum((i - x_mean) ** 2 for i in range(n))

        if denom > 0:
            slope = num / denom
        else:
            slope = 0.0

        # Project to remaining time
        remaining_steps_fraction = (deadline - current_time) / max(current_time, 0.01)
        projected_change = slope * remaining_steps_fraction * n
        predicted = y_mean + projected_change

        return max(min(predicted, 1.0), 0.3)

    def _classify_style(self):
        """Classify opponent negotiation style."""
        n = len(self.offer_utilities)
        if n < 10:
            return

        # Check concession trend
        first_third = self.offer_utilities[: n // 3]
        last_third = self.offer_utilities[-(n // 3):]

        if first_third and last_third:
            early_avg = sum(first_third) / len(first_third)
            late_avg = sum(last_third) / len(last_third)
            self.concession_rate = early_avg - late_avg  # positive = conceding

        # Hardheaded: very little change, high utility demands
        if abs(self.concession_rate) < 0.05 and n > 20:
            self.is_hardheaded = True
            self.is_conceder = False
        elif self.concession_rate > 0.15:
            self.is_conceder = True
            self.is_hardheaded = False
        else:
            self.is_hardheaded = False
            self.is_conceder = False

        # MiCRO-style: unique count close to ours
        unique_ratio = len(self.unique_offers) / max(n, 1)
        self.is_micro_style = unique_ratio > 0.8 and n > 15

    def get_style_features(self) -> dict:
        """Return features describing opponent's style for meta-controller."""
        n = len(self.offers)
        return {
            "num_offers": n,
            "unique_ratio": len(self.unique_offers) / max(n, 1),
            "concession_rate": self.concession_rate,
            "is_hardheaded": self.is_hardheaded,
            "is_conceder": self.is_conceder,
            "is_micro_style": self.is_micro_style,
            "current_threshold": self.get_current_opponent_threshold(),
        }
