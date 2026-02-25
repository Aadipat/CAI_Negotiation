"""
Meta-controller for portfolio-based expert selection.

Implements bandit-style expert selection with guarded switching,
inspired by Caduceus (ANAC 2016) and strategy portfolio research.

Selects among experts based on:
- Opponent style features (from OpponentModel)
- Phase of negotiation (early/mid/late)
- Online reward estimation (how well each expert's suggestions perform)
"""

from __future__ import annotations

import math
from typing import Any

from .experts import ExpertBase, BoulwareExpert, ParetoExpert, MiCROExpert, ForecastExpert
from .opponent_model import OpponentModel


class MetaController:
    """
    Portfolio meta-controller with expert voting and guarded switching.

    Maintains weights for each expert and selects based on:
    1. Phase-dependent priors (early: boulware, mid: adaptive, late: secure deal)
    2. Opponent classification feedback
    3. Online reward signals from acceptance/agreement quality

    Switching policy:
    - Early (t < 0.5): bias toward hardheaded (E1) or Pareto (E2)
    - Mid (0.5 <= t < 0.85): switch based on opponent concession rate
    - Late (t >= 0.85): allow forced switch to "secure agreement" expert
    """

    def __init__(self, experts: list[ExpertBase] | None = None):
        if experts is None:
            self.experts = [
                BoulwareExpert(e=0.08),
                ParetoExpert(e=0.15, alpha=0.2),
                MiCROExpert(),
                ForecastExpert(base_e=0.12),
            ]
        else:
            self.experts = experts

        self.n_experts = len(self.experts)

        # Bandit weights (initialized to favor boulware)
        self.weights = [1.0] * self.n_experts
        self.weights[0] = 2.5  # Boulware starts much stronger
        self.weights[2] = 1.5  # MiCRO also strong

        # Performance tracking
        self.expert_rewards: list[float] = [0.0] * self.n_experts
        self.expert_counts: list[int] = [0] * self.n_experts
        self.last_selected: int = 0

        # EMA of expert quality
        self.expert_ema: list[float] = [0.5] * self.n_experts

        # Switching cooldown (avoid rapid switches)
        self._switch_cooldown: int = 0
        self._min_switches_apart: int = 8  # at least 8 rounds between switches

    def select_expert(
        self,
        opp_model: OpponentModel | None,
        t: float,
        round_num: int,
    ) -> int:
        """
        Select which expert to use this round.

        Returns the index of the selected expert.
        """
        # Decrement cooldown
        if self._switch_cooldown > 0:
            self._switch_cooldown -= 1
            return self.last_selected

        # Compute scores for each expert
        scores = self._compute_scores(opp_model, t)

        # Select best scoring expert
        best_idx = max(range(self.n_experts), key=lambda i: scores[i])

        # Only switch if the new expert is significantly better
        if best_idx != self.last_selected:
            improvement = scores[best_idx] - scores[self.last_selected]
            if improvement > 0.2 or t > 0.95:  # Higher threshold for switching
                self.last_selected = best_idx
                self._switch_cooldown = self._min_switches_apart
            # else keep current expert (stability)

        self.expert_counts[self.last_selected] += 1
        return self.last_selected

    def _compute_scores(self, opp_model: OpponentModel | None, t: float) -> list[float]:
        """Compute selection scores for each expert based on context."""
        scores = [0.0] * self.n_experts

        # === Phase-dependent priors ===
        if t < 0.3:
            # Early: strongly favor boulware and MiCRO (stay tough)
            phase_priors = [3.0, 0.5, 2.0, 1.0]
        elif t < 0.5:
            # Early-mid: still favor tough strategies
            phase_priors = [2.5, 1.0, 1.5, 1.2]
        elif t < 0.7:
            # Mid: start considering adaptation
            phase_priors = [2.0, 1.2, 1.2, 1.5]
        elif t < 0.85:
            # Late-mid: allow some flexibility
            phase_priors = [1.5, 1.5, 1.0, 1.5]
        elif t < 0.95:
            # Late: still maintain some toughness
            phase_priors = [1.0, 1.8, 0.8, 1.8]
        else:
            # Very late: maximize deal chance with smart concession
            phase_priors = [0.5, 2.0, 0.7, 2.0]

        for i in range(self.n_experts):
            scores[i] += phase_priors[i] if i < len(phase_priors) else 1.0

        # === Opponent-style adjustments ===
        if opp_model is not None and len(opp_model.offers) >= 10:
            features = opp_model.get_style_features()

            if features["is_hardheaded"]:
                # Against hardheaded: use forecast (adapts) or pareto (find mutual gains)
                scores[0] -= 0.5  # boulware less useful (stalemate risk)
                scores[1] += 0.5  # pareto can find acceptable bids
                scores[3] += 1.0  # forecast adapts to hardheaded
                if t > 0.7:
                    scores[1] += 0.5  # Pareto even more important late

            elif features["is_conceder"]:
                # Against conceder: stay tough with boulware, let them come to us
                scores[0] += 1.0  # boulware: maintain pressure
                scores[2] += 0.5  # micro is also good
                scores[1] -= 0.5  # less need for pareto compromise

            elif features["is_micro_style"]:
                # Against MiCRO-style: respond in kind or use forecast
                scores[2] += 0.5  # mirror micro
                scores[3] += 0.5  # forecast can adapt

            # Dynamic concession rate adjustment
            cr = features.get("concession_rate", 0.0)
            if cr > 0.15:  # Opponent conceding quickly
                scores[0] += 0.5  # Stay tough
            elif cr < -0.05:  # Opponent hardening
                scores[1] += 0.3  # Try pareto
                scores[3] += 0.3  # Adapt

        # === Online performance (EMA rewards) ===
        for i in range(self.n_experts):
            scores[i] += self.expert_ema[i] * 0.5

        # === Bandit weights ===
        for i in range(self.n_experts):
            scores[i] *= self.weights[i]

        return scores

    def update_reward(self, expert_idx: int, reward: float):
        """
        Update the reward estimate for an expert.

        Args:
            expert_idx: Index of the expert that was used.
            reward: Reward signal (e.g., utility of accepted offer, or 0 for no deal).
        """
        if expert_idx < 0 or expert_idx >= self.n_experts:
            return

        self.expert_rewards[expert_idx] += reward
        self.expert_counts[expert_idx] += 1

        # Update EMA
        alpha = 0.3  # EMA smoothing factor
        self.expert_ema[expert_idx] = (
            alpha * reward + (1.0 - alpha) * self.expert_ema[expert_idx]
        )

        # Update bandit weights (softmax-style)
        avg_reward = reward
        if self.expert_counts[expert_idx] > 0:
            avg_reward = self.expert_rewards[expert_idx] / self.expert_counts[expert_idx]
        self.weights[expert_idx] = max(0.1, self.weights[expert_idx] * (1.0 + 0.1 * (avg_reward - 0.5)))

    def get_expert(self, idx: int) -> ExpertBase:
        """Get expert by index."""
        return self.experts[idx]

    def get_status(self) -> dict:
        """Return current controller status for logging/debugging."""
        return {
            "weights": list(self.weights),
            "ema": list(self.expert_ema),
            "counts": list(self.expert_counts),
            "selected": self.last_selected,
            "selected_name": self.experts[self.last_selected].name,
        }
