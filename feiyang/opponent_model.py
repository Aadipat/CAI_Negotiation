"""
Frequency-based opponent model with enhanced detection capabilities.

Tracks how often each issue-value pair appears in opponent bids,
and estimates opponent utility using frequency counts, issue weight
estimation via concentration metrics, and concession trend tracking.

Enhanced features:
- Reciprocity detection (TFT-style opponent awareness)
- Stalemate detection (repeated same offers)
- Better concession rate estimation with sliding window
- Move diversity tracking for MiCRO-style detection
- Our-offer tracking for self-check verification

Pure NegMAS implementation — outcomes are tuples.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from negmas import Outcome


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

    def __init__(self, num_values: int):
        self.bids_received: int = 0
        self.max_value_count: int = 0
        self.num_values: int = max(num_values, 1)
        self.value_trackers: dict[Any, ValueEstimator] = defaultdict(ValueEstimator)
        self.weight: float = 0.0

    def update(self, value):
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

    def get_value_utility(self, value) -> float:
        if value in self.value_trackers:
            return self.value_trackers[value].utility
        return 0.0


class OpponentModel:
    """
    Frequency-based opponent model with enhanced detection capabilities.

    Tracks opponent bids to estimate:
    - Per-issue weights (how important each issue is to the opponent)
    - Per-value utilities (how much the opponent values each option)
    - Concession trends over time (sliding window)
    - Opponent style classification (hardheaded, conceder, TFT, MiCRO)
    - Stalemate detection (repeated offers with no progress)
    - Reciprocity signals (does opponent concede when we concede?)

    Works with NegMAS outcomes (tuples). Issues are identified by index.
    """

    def __init__(self, n_issues: int, values_per_issue: list[int]):
        self.n_issues = n_issues
        self.offers: list[Outcome] = []
        self.offer_utilities: list[float] = []  # estimated opp utilities over time
        self.unique_offers: set[Outcome] = set()

        # Per-issue estimators
        self.issue_estimators: dict[int, IssueEstimator] = {}
        for i in range(n_issues):
            nv = values_per_issue[i] if i < len(values_per_issue) else 1
            self.issue_estimators[i] = IssueEstimator(nv)

        # Concession tracking
        self.time_segments: int = 40
        self.segment_sums: list[float] = [0.0] * self.time_segments
        self.segment_counts: list[int] = [0] * self.time_segments
        self.segment_unique: list[int] = [0] * self.time_segments
        self._segment_seen: set = set()
        self._current_segment: int = 0

        # Style classification
        self.is_hardheaded: bool = False
        self.is_conceder: bool = False
        self.is_micro_style: bool = False
        self.is_tft_style: bool = False
        self.concession_rate: float = 0.0

        # Stalemate detection
        self._consecutive_repeats: int = 0
        self._last_offer: Outcome | None = None
        self._stalemate_count: int = 0

        # Reciprocity tracking
        self._our_prev_util: float | None = None
        self._opp_prev_util: float | None = None
        self._reciprocity_events: list[bool] = []
        self._reciprocity_score: float = 0.5

    def update(self, offer: Outcome, normalized_time: float):
        """Update model with a new opponent offer (a tuple)."""
        if offer is None:
            return

        self.offers.append(offer)

        # Update issue estimators
        for i, estimator in self.issue_estimators.items():
            if i < len(offer):
                estimator.update(offer[i])

        # Track estimated utility
        est_util = self.get_predicted_utility(offer)
        self.offer_utilities.append(est_util)

        # Track uniqueness
        is_new = offer not in self.unique_offers
        self.unique_offers.add(offer)

        # Stalemate detection — detect faster
        if self._last_offer is not None and offer == self._last_offer:
            self._consecutive_repeats += 1
            if self._consecutive_repeats >= 3:  # need clear repetition signal
                self._stalemate_count += 1
        else:
            self._consecutive_repeats = 0
        self._last_offer = offer

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

        # Update style classification after enough data
        if len(self.offers) >= 8:  # need enough data for reliable classification
            self._classify_style()

    def track_our_offer(self, our_util: float, opp_util_of_our_offer: float):
        """
        Track our own offers to detect reciprocity.
        Call this after we propose, with our utility and estimated opponent utility.
        """
        if self._our_prev_util is not None and self._opp_prev_util is not None:
            # Did we concede? (our utility decreased)
            we_conceded = our_util < self._our_prev_util - 0.01
            # Did opponent concede since last turn? (their self-util decreased, our util increased)
            if len(self.offer_utilities) >= 2:
                opp_conceded = self.offer_utilities[-1] < self.offer_utilities[-2] - 0.01
            else:
                opp_conceded = False

            if we_conceded:
                self._reciprocity_events.append(opp_conceded)
                if len(self._reciprocity_events) >= 3:
                    recent = self._reciprocity_events[-10:]
                    self._reciprocity_score = sum(
                        1.0 for r in recent if r
                    ) / len(recent)

        self._our_prev_util = our_util
        self._opp_prev_util = opp_util_of_our_offer

    def get_predicted_utility(self, offer: Outcome) -> float:
        """Estimate how much the opponent values a given outcome."""
        if offer is None or len(self.offers) == 0:
            return 0.0

        total_weight = 0.0
        weighted_util = 0.0

        for i, estimator in self.issue_estimators.items():
            if i < len(offer):
                vu = estimator.get_value_utility(offer[i])
                w = estimator.weight
                weighted_util += vu * w
                total_weight += w

        if total_weight == 0.0:
            n = len(self.issue_estimators)
            if n == 0:
                return 0.0
            for i, estimator in self.issue_estimators.items():
                if i < len(offer):
                    weighted_util += estimator.get_value_utility(offer[i]) / n
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
            return 0.5

        n = min(len(self.offer_utilities), 20)
        recent = self.offer_utilities[-n:]
        x_mean = (n - 1) / 2.0
        y_mean = sum(recent) / n
        num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(recent))
        denom = sum((i - x_mean) ** 2 for i in range(n))

        slope = num / denom if denom > 0 else 0.0

        remaining_steps_fraction = (deadline - current_time) / max(current_time, 0.01)
        projected_change = slope * remaining_steps_fraction * n
        predicted = y_mean + projected_change

        return max(min(predicted, 1.0), 0.3)

    def _classify_style(self):
        """Classify opponent negotiation style with enhanced TFT detection."""
        n = len(self.offer_utilities)
        if n < 5:  # was 8
            return

        # Concession rate: compare early vs late average estimated utility
        third = max(n // 3, 1)
        first_third = self.offer_utilities[:third]
        last_third = self.offer_utilities[-third:]

        if first_third and last_third:
            early_avg = sum(first_third) / len(first_third)
            late_avg = sum(last_third) / len(last_third)
            self.concession_rate = early_avg - late_avg

        # Hardheaded: barely changes utility over time
        if abs(self.concession_rate) < 0.05 and n > 10:  # was 15
            self.is_hardheaded = True
            self.is_conceder = False
        elif self.concession_rate > 0.15:
            self.is_conceder = True
            self.is_hardheaded = False
        else:
            self.is_hardheaded = False
            self.is_conceder = False

        # MiCRO detection: many unique offers proposed in sequence
        unique_ratio = len(self.unique_offers) / max(n, 1)
        self.is_micro_style = unique_ratio > 0.65 and n > 8  # need more data

        # TFT detection: opponent concedes gradually AND uniqueness is high
        if n >= 8:  # need enough pattern data
            sliding_window = min(4, n // 2)  # wider window for stability
            gradual_changes = 0
            for i in range(sliding_window, n):
                window = self.offer_utilities[i - sliding_window:i]
                avg_window = sum(window) / len(window)
                diff = abs(self.offer_utilities[i] - avg_window)
                if diff < 0.15:
                    gradual_changes += 1

            gradual_ratio = gradual_changes / max(n - sliding_window, 1)

            # TFT = high unique ratio + gradual changes + some concession
            self.is_tft_style = (
                unique_ratio > 0.5
                and gradual_ratio > 0.4
                and 0.01 < abs(self.concession_rate) < 0.35
            )

    @property
    def is_stalemate(self) -> bool:
        """Return True if we detect a stalemate (repeated same offers)."""
        return self._consecutive_repeats >= 3 or self._stalemate_count >= 2

    @property
    def reciprocity_score(self) -> float:
        """How likely opponent is to reciprocate our concessions. [0, 1]."""
        return self._reciprocity_score

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
            "is_tft_style": self.is_tft_style,
            "is_stalemate": self.is_stalemate,
            "reciprocity": self._reciprocity_score,
            "consecutive_repeats": self._consecutive_repeats,
            "current_threshold": self.get_current_opponent_threshold(),
        }
