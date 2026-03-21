"""
Meta-controller for portfolio-based expert selection — v2.

Improved expert selection with:
- 5 experts: Boulware, Pareto, NiceTFT, Forecast, DealSeeker
- Reduced Boulware bias in early phases
- TFT/MiCRO opponent detection → route to NiceTFT expert
- Stalemate detection → route to DealSeeker
- No switching cooldown in late phases (t > 0.85)
- Faster switching to allow adaptive behavior
- Forced DealSeeker when near deadline

Expert indices:
  0: BoulwareExpert  (hardheaded, slow concession)
  1: ParetoExpert    (Pareto-optimal bidding)
  2: NiceTFTExpert   (reciprocal concession for TFT opponents)
  3: ForecastExpert  (adaptive concession based on predictions)
  4: DealSeekerExpert (late-game agreement maximizer)
"""

from __future__ import annotations

from typing import Any

from .experts import (
    ExpertBase,
    BoulwareExpert,
    ParetoExpert,
    NiceTFTExpert,
    ForecastExpert,
    DealSeekerExpert,
)
from .opponent_model import OpponentModel


class MetaController:
    """
    Portfolio meta-controller with expert voting and guarded switching — v2.

    Key changes from v1:
    - 5 experts instead of 4 (added DealSeeker, replaced MiCRO with NiceTFT)
    - Balanced initial weights (less Boulware dominance)
    - Stalemate-aware routing
    - TFT opponent detection → NiceTFT expert
    - Forced DealSeeker activation near deadline
    - Reduced switching cooldown (5 → 3, disabled after t=0.85)
    """

    def __init__(self, experts: list[ExpertBase] | None = None):
        if experts is None:
            self.experts = [
                BoulwareExpert(e=0.08),       # E0: tighter concession
                ParetoExpert(e=0.10, alpha=0.30),  # E1: Pareto bidder (self-interest first)
                NiceTFTExpert(),               # E2: reciprocal (for TFT opponents)
                ForecastExpert(base_e=0.10),   # E3: adaptive
                DealSeekerExpert(),            # E4: late-game deal closer
            ]
        else:
            self.experts = experts

        self.n_experts = len(self.experts)

        # Balanced initial weights 
        self.weights = [1.0] * self.n_experts
        self.weights[0] = 1.5   # Boulware — 稍微保留前期强硬优势，从 2.0 降到 1.5（原值：2.0）
        self.weights[2] = 1.0   # NiceTFT — 降回 1.0，与其他自适应专家平起平坐（原值：2.0)

        # Performance tracking
        self.expert_rewards: list[float] = [0.0] * self.n_experts
        self.expert_counts: list[int] = [0] * self.n_experts
        self.last_selected: int = 0

        # EMA of expert quality
        self.expert_ema: list[float] = [0.5] * self.n_experts

        # Switching cooldown (minimal for faster adaptation)
        self._switch_cooldown: int = 0
        self._min_switches_apart: int = 2  # was 3

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
        # === FORCED OVERRIDES ===

        # Force DealSeeker only very near deadline
        if t >= 0.93:
            self.last_selected = 4  # DealSeeker
            return 4

        # Force NiceTFT if stalemate detected (but wait longer)
        if (opp_model is not None
                and opp_model.is_stalemate
                and t < 0.90
                and round_num > 8):  # wait for clear stalemate
            self.last_selected = 2  # NiceTFT
            self._switch_cooldown = 0
            return 2

        # Force NiceTFT early if opponent looks like TFT/MiCRO
        if (opp_model is not None
                and len(opp_model.offers) >= 8
                and (opp_model.is_tft_style or opp_model.is_micro_style)
                and t < 0.90):
            self.last_selected = 2  # NiceTFT
            self._switch_cooldown = 0
            return 2

        # === Normal selection with cooldown ===
        # Disable cooldown in late phases for faster adaptation
        if t > 0.70:  # was 0.85
            self._switch_cooldown = 0

        if self._switch_cooldown > 0:
            self._switch_cooldown -= 1
            return self.last_selected

        scores = self._compute_scores(opp_model, t)
        best_idx = max(range(self.n_experts), key=lambda i: scores[i])

        if best_idx != self.last_selected:
            # Lower switching threshold for faster adaptation
            improvement = scores[best_idx] - scores[self.last_selected]
            if improvement > 0.10 or t > 0.60:  # was 0.15 / 0.80
                self.last_selected = best_idx
                self._switch_cooldown = self._min_switches_apart

        self.expert_counts[self.last_selected] += 1
        return self.last_selected

    def _compute_scores(self, opp_model: OpponentModel | None, t: float) -> list[float]:
        """Compute selection scores for each expert based on context."""
        # Indices: 0=Boulware, 1=Pareto, 2=NiceTFT, 3=Forecast, 4=DealSeeker
        scores = [0.0] * self.n_experts

        # === Phase-dependent priors (5 experts) ===
        # Format: [Boulware, Pareto, NiceTFT, Forecast, DealSeeker]
        if t < 0.15:
            # Early: hold ground with Boulware, some NiceTFT signaling
            phase_priors = [3.0, 0.5, 1.5, 0.8, 0.0]
        elif t < 0.30:
            phase_priors = [2.4, 1.0, 1.4, 1.2, 0.0]
        elif t < 0.50:
            # Mid-early: add more Pareto exploration for trade opportunities
            phase_priors = [1.8, 1.8, 1.4, 2.0, 0.0]
        elif t < 0.70:
            # Mid: Forecast + Pareto, some NiceTFT
            phase_priors = [1.3, 2.1, 1.3, 2.4, 0.3]
        elif t < 0.85:
            # Mid-late: DealSeeker + Forecast
            phase_priors = [0.8, 1.8, 1.1, 1.9, 2.0]
        else:
            # Late: DealSeeker dominates
            phase_priors = [0.3, 1.0, 0.8, 1.5, 3.5]

        for i in range(self.n_experts):
            scores[i] += phase_priors[i] if i < len(phase_priors) else 1.0

        # === Opponent-style adjustments ===
        if opp_model is not None and len(opp_model.offers) >= 8:
            features = opp_model.get_style_features()
            # When style is ambiguous, favor Pareto exploration.
            if (not features.get("is_hardheaded", False)
                    and not features.get("is_conceder", False)
                    and not features.get("is_tft_style", False)
                    and not features.get("is_micro_style", False)):
                scores[1] += 0.6

            if features.get("is_tft_style", False) or features.get("is_micro_style", False):
                # TFT/MiCRO opponents: boost NiceTFT significantly
                scores[2] += 1.0   # 修改：从 2.5 大幅砍到 1.0。让它有优势，但不至于无脑碾压
                scores[0] -= 1.0   # 保持不变
                scores[3] += 0.8   # 修改：把 Forecast 的加分从 0.5 稍微提高到 0.8，增加竞争性

            # Stalemate detection
            if features.get("is_stalemate", False):
                scores[2] += 0.8   # 修改：从 1.5 降到 0.8，NiceTFT 可以用来破局，但别给太多分
                scores[4] += 1.2   # 修改：从 1.5 降到 1.2，DealSeeker 破局能力也很强，让它保持微弱优势
                scores[0] -= 1.5   # 保持不变，强硬派确实不适合破局

            # Reciprocity: if opponent is reciprocal, reward NiceTFT
            reciprocity = features.get("reciprocity", 0.5)
            if reciprocity > 0.6:
                scores[2] += 0.4   # 修改：从 0.8 降到 0.4，作为锦上添花的微调即可

            cr = features.get("concession_rate", 0.0)
            if cr > 0.15:
                scores[0] += 0.5   # They're conceding, hold firm
            elif cr < -0.05:
                scores[3] += 0.5   # They're hardening, adapt

        # === Online performance (EMA rewards) ===
        for i in range(self.n_experts):
            scores[i] += self.expert_ema[i] * 0.5

        # === Bandit weights ===
        for i in range(self.n_experts):
            scores[i] *= self.weights[i]

        return scores

    def update_reward(self, expert_idx: int, reward: float):
        """Update the reward estimate for an expert."""
        if expert_idx < 0 or expert_idx >= self.n_experts:
            return

        self.expert_rewards[expert_idx] += reward
        self.expert_counts[expert_idx] += 1

        alpha = 0.3
        self.expert_ema[expert_idx] = (
            alpha * reward + (1.0 - alpha) * self.expert_ema[expert_idx]
        )

        avg_reward = reward
        if self.expert_counts[expert_idx] > 0:
            avg_reward = self.expert_rewards[expert_idx] / self.expert_counts[expert_idx]
        self.weights[expert_idx] = max(
            0.1, self.weights[expert_idx] * (1.0 + 0.1 * (avg_reward - 0.5))
        )

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
