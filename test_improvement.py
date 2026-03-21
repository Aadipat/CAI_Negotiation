"""
test_improvement.py — HybridAgent improvement analysis harness.

Runs multiple manually-defined agent configurations head-to-head against
a fixed set of opponents and generates detailed graphs so you can see
exactly which parameter changes help or hurt.

Usage:
    python test_improvement.py

All graphs are saved to ./improvement_output/<timestamp>/ and also
displayed interactively.

What you can tweak (see CONFIGURATIONS at the bottom):
  OpponentModel:   time_segments, stalemate threshold, reciprocity alpha
  AcceptanceController: initial_threshold, final_threshold, emergency_time,
                        emergency_floor, no_accept_rounds
  MetaController:  initial weights, phase_priors, switch thresholds
  BoulwareExpert:  e (concession exponent)
  ParetoExpert:    e, alpha
  ForecastExpert:  base_e
  HybridAgent:     min_util floor multiplier (hard_floor fraction)
"""

from __future__ import annotations

import copy
import math
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")   # non-interactive backend; swap to "TkAgg" for live windows
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import numpy as np

# ── Output directory ────────────────────────────────────────────────────────
_OUTPUT_ROOT = Path(__file__).resolve().parent / "improvement_output"
_OUTPUT_ROOT.mkdir(exist_ok=True)
_RUN_TS = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = _OUTPUT_ROOT / _RUN_TS
OUTPUT_DIR.mkdir(exist_ok=True)
print(f"[test_improvement] Saving results to {OUTPUT_DIR}")

# ── NegMAS imports ──────────────────────────────────────────────────────────
from negmas import (
    SAOMechanism,
    make_issue,
    make_os,
    enumerate_issues,
    conflict_level,
    opposition_level,
    calc_scenario_stats,
    AspirationNegotiator,
    TimeBasedConcedingNegotiator,
    MiCRONegotiator,
    NaiveTitForTatNegotiator,
    RandomNegotiator,
    ToughNegotiator,
    NiceNegotiator,
    BoulwareTBNegotiator,
    ConcederTBNegotiator,
    LinearTBNegotiator,
)
from negmas.preferences import LinearAdditiveUtilityFunction as LUFun
from negmas.preferences.value_fun import AffineFun, IdentityFun, TableFun
from negmas.sao import SAONegotiator, SAOState, ResponseType
from negmas import Outcome

# ── Import feiyang components ────────────────────────────────────────────────
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from feiyang.opponent_model import OpponentModel, IssueEstimator, ValueEstimator
from feiyang.experts import (
    ExpertBase, BoulwareExpert, ParetoExpert,
    NiceTFTExpert, ForecastExpert, DealSeekerExpert,
)
from feiyang.meta_controller import MetaController
from feiyang.acceptance import AcceptanceController
from feiyang.hybrid_agent import HybridAgent


# ════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION DATACLASS — tweak these to test improvements
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class AgentConfig:
    """
    All tuneable parameters for HybridAgent and its sub-components.
    Create multiple instances (one per variant you want to compare).
    """
    name: str

    # ── HybridAgent core ─────────────────────────────────────────────────
    min_util_floor_fraction: float = 0.35   # hard_floor = fraction * max_util
    initial_threshold: float = 0.92
    final_threshold: float = 0.50
    no_accept_rounds: int = 2
    emergency_time: float = 0.88
    max_outcomes_enumerated: int = 10_000

    # ── BoulwareExpert ───────────────────────────────────────────────────
    boulware_e: float = 0.08

    # ── ParetoExpert ─────────────────────────────────────────────────────
    pareto_e: float = 0.10
    pareto_alpha: float = 0.30

    # ── ForecastExpert ───────────────────────────────────────────────────
    forecast_base_e: float = 0.10

    # ── MetaController ───────────────────────────────────────────────────
    meta_boulware_init_weight: float = 2.0
    meta_nicetft_init_weight: float = 2.0
    meta_dealseeker_threshold: float = 0.93   # t >= this → force DealSeeker
    meta_min_switches_apart: int = 2

    # ── OpponentModel ────────────────────────────────────────────────────
    opp_time_segments: int = 40
    opp_stalemate_repeats: int = 3   # consecutive_repeats >= this → stalemate

    color: str = "#1f77b4"   # for plots


# ════════════════════════════════════════════════════════════════════════════
#  INSTRUMENTED HybridAgent — records per-round trace data
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class RoundTrace:
    """Data recorded each round for analysis."""
    t: float
    my_utility: float
    opp_est_utility: float
    expert_idx: int
    expert_name: str
    accepted: bool
    stalemate: bool
    opp_style: dict


class InstrumentedHybridAgent(SAONegotiator):
    """
    HybridAgent variant that accepts an AgentConfig and records trace data
    each round so we can plot what's happening inside.
    """

    def __init__(self, cfg: AgentConfig, **kwargs):
        super().__init__(**kwargs)
        self.cfg = cfg
        self.trace: list[RoundTrace] = []
        self.expert_selection_history: list[int] = []
        self.proposed_utilities: list[float] = []
        self.received_utilities: list[float] = []
        self.opp_estimated_utilities: list[float] = []

    def _init_agent(self):
        if hasattr(self, "_is_initialized"):
            return

        cfg = self.cfg
        self._reservation: float = 0.0
        if self.ufun is not None and self.ufun.reserved_value is not None:
            self._reservation = float(self.ufun.reserved_value)

        self._all_outcomes: list[Outcome] = list(
            self.nmi.outcome_space.enumerate_or_sample(
                max_cardinality=cfg.max_outcomes_enumerated
            )
        )
        self._my_utilities: dict[Outcome, float] = {
            o: float(self.ufun(o)) for o in self._all_outcomes
        }
        self._sorted_outcomes: list[Outcome] = sorted(
            self._all_outcomes,
            key=lambda o: self._my_utilities[o],
            reverse=True,
        )

        if self._sorted_outcomes:
            self._max_util = self._my_utilities[self._sorted_outcomes[0]]
            raw_min = self._my_utilities[self._sorted_outcomes[-1]]
        else:
            self._max_util = 1.0
            raw_min = 0.0

        hard_floor = max(
            cfg.min_util_floor_fraction * self._max_util,
            self._reservation,
            raw_min,
        )
        self._min_util = hard_floor

        n_issues = len(self._all_outcomes[0]) if self._all_outcomes else 0
        values_per_issue: list[int] = []
        for i in range(n_issues):
            unique_vals = set(o[i] for o in self._all_outcomes)
            values_per_issue.append(len(unique_vals))

        # Build opponent model with configurable parameters
        self._opp_model = OpponentModel(n_issues, values_per_issue)
        self._opp_model.time_segments = cfg.opp_time_segments
        self._opp_model.segment_sums = [0.0] * cfg.opp_time_segments
        self._opp_model.segment_counts = [0] * cfg.opp_time_segments
        self._opp_model.segment_unique = [0] * cfg.opp_time_segments

        # Build experts with configurable parameters
        experts = [
            BoulwareExpert(e=cfg.boulware_e),
            ParetoExpert(e=cfg.pareto_e, alpha=cfg.pareto_alpha),
            NiceTFTExpert(),
            ForecastExpert(base_e=cfg.forecast_base_e),
            DealSeekerExpert(),
        ]
        self._meta = MetaController(experts=experts)
        self._meta.weights[0] = cfg.meta_boulware_init_weight
        self._meta.weights[2] = cfg.meta_nicetft_init_weight
        self._meta._min_switches_apart = cfg.meta_min_switches_apart

        self._acceptance = AcceptanceController(
            reservation=self._reservation,
            min_util=self._min_util,
            initial_threshold=cfg.initial_threshold,
            final_threshold=max(cfg.final_threshold, self._min_util),
            no_accept_rounds=cfg.no_accept_rounds,
            emergency_time=cfg.emergency_time,
            emergency_floor=max(self._reservation, self._min_util),
        )

        self._last_received_offer: Outcome | None = None
        self._last_received_util: float = 0.0
        self._best_received_offer: Outcome | None = None
        self._best_received_util: float = 0.0
        self._round: int = 0
        self._last_proposed_util: float = self._max_util
        self._proposal_history: list[float] = []
        self._is_initialized = True

    def respond(self, state: SAOState, source: str | None = None) -> ResponseType:
        self._init_agent()
        offer = state.current_offer
        if offer is None:
            return ResponseType.REJECT_OFFER

        t = state.relative_time
        offer_util = self._my_utilities.get(offer, float(self.ufun(offer)))
        self._last_received_offer = offer
        self._last_received_util = offer_util
        if offer_util > self._best_received_util:
            self._best_received_util = offer_util
            self._best_received_offer = offer

        self._opp_model.update(offer, t)
        self._round += 1

        state_dict = self._build_state(t)
        expert_idx = self._meta.select_expert(self._opp_model, t, self._round)
        expert = self._meta.get_expert(expert_idx)

        proposed = expert.propose(
            self._sorted_outcomes, self.ufun, self._opp_model, t, state_dict
        )
        proposed = self._verify_proposal(proposed)
        state_dict["planned_counter"] = proposed

        should_accept = self._acceptance.should_accept(
            offer, self.ufun, self._opp_model, expert, t, state_dict,
        )

        # Record trace
        opp_est = self._opp_model.get_predicted_utility(offer)
        self.received_utilities.append(offer_util)
        self.opp_estimated_utilities.append(opp_est)
        self.expert_selection_history.append(expert_idx)
        self.trace.append(RoundTrace(
            t=t,
            my_utility=offer_util,
            opp_est_utility=opp_est,
            expert_idx=expert_idx,
            expert_name=expert.name,
            accepted=should_accept and offer_util >= self._min_util,
            stalemate=self._opp_model.is_stalemate,
            opp_style=self._opp_model.get_style_features(),
        ))

        if should_accept and offer_util >= self._min_util:
            self._meta.update_reward(expert_idx, offer_util)
            return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER

    def propose(self, state: SAOState, dest: str | None = None) -> Outcome:
        self._init_agent()
        t = state.relative_time
        state_dict = self._build_state(t)

        expert_idx = self._meta.select_expert(self._opp_model, t, self._round)
        expert = self._meta.get_expert(expert_idx)

        proposed = expert.propose(
            self._sorted_outcomes, self.ufun, self._opp_model, t, state_dict
        )
        proposed = self._verify_proposal(proposed)

        u_proposed = self._my_utilities.get(proposed, float(self.ufun(proposed)))
        opp_util_est = (
            self._opp_model.get_predicted_utility(proposed)
            if len(self._opp_model.offers) > 0 else 0.0
        )
        self._opp_model.track_our_offer(u_proposed, opp_util_est)
        self._last_proposed_util = u_proposed
        self._proposal_history.append(u_proposed)
        self.proposed_utilities.append(u_proposed)

        self._meta.update_reward(expert_idx, u_proposed)
        return proposed

    def _verify_proposal(self, proposed: Outcome | None) -> Outcome:
        if proposed is None:
            return self._sorted_outcomes[0]
        u_proposed = self._my_utilities.get(proposed, float(self.ufun(proposed)))
        if proposed not in self._my_utilities:
            u_proposed = float(self.ufun(proposed))
            self._my_utilities[proposed] = u_proposed
        if u_proposed < self._min_util:
            for outcome in reversed(self._sorted_outcomes):
                u = self._my_utilities[outcome]
                if u >= self._min_util:
                    return outcome
            return self._sorted_outcomes[0]
        return proposed

    def _build_state(self, t: float) -> dict[str, Any]:
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
            "is_stalemate": self._opp_model.is_stalemate,
        }


# ════════════════════════════════════════════════════════════════════════════
#  SCENARIO GENERATION (mirrors eval_simple.py)
# ════════════════════════════════════════════════════════════════════════════

def _make_buyer_seller():
    """Classic buyer/seller: opposing on price & delivery, aligned on quantity."""
    issues = [
        make_issue(name="price", values=10),
        make_issue(name="quantity", values=(1, 11)),
        make_issue(name="delivery_time", values=10),
    ]
    os = make_os(issues)
    buyer = LUFun(
        values={"price": AffineFun(-1, bias=9.0), "quantity": IdentityFun(),
                "delivery_time": IdentityFun()},
        outcome_space=os,
    ).scale_max(1.0)
    seller = LUFun(
        values={"price": IdentityFun(), "quantity": IdentityFun(),
                "delivery_time": AffineFun(-1, bias=9.0)},
        outcome_space=os,
    ).scale_max(1.0)
    return issues, os, buyer, seller


def _make_integrative(rng: random.Random):
    """Opposite issue priorities — HybridAgent's ParetoExpert shines here."""
    issues = [make_issue(name=f"i{j}", values=rng.randint(4, 8)) for j in range(4)]
    os = make_os(issues)
    n = len(issues)
    raw_a = [float(n - i) for i in range(n)]
    raw_b = [float(i + 1) for i in range(n)]
    sum_a, sum_b = sum(raw_a), sum(raw_b)
    w_a = {iss.name: w / sum_a for iss, w in zip(issues, raw_a)}
    w_b = {iss.name: w / sum_b for iss, w in zip(issues, raw_b)}
    vals_a, vals_b = {}, {}
    for issue in issues:
        nv = issue.cardinality
        ta = {i: i / max(nv - 1, 1) for i in range(nv)}
        tb = {i: max(0.0, 1.0 - i / max(nv - 1, 1) + rng.uniform(-0.1, 0.1)) for i in range(nv)}
        vals_a[issue.name] = TableFun(ta)
        vals_b[issue.name] = TableFun(tb)
    ua = LUFun(values=vals_a, weights=w_a, outcome_space=os).scale_max(1.0)
    ub = LUFun(values=vals_b, weights=w_b, outcome_space=os).scale_max(1.0)
    return issues, os, ua, ub


def _make_medium_opp(rng: random.Random):
    """3-issue medium-opposition scenario."""
    issues = [make_issue(name=f"i{j}", values=rng.randint(4, 7)) for j in range(3)]
    os = make_os(issues)
    vals_a, vals_b = {}, {}
    raw_wa = [rng.uniform(0.1, 1.0) for _ in issues]
    raw_wb = list(reversed(raw_wa))
    sum_a, sum_b = sum(raw_wa), sum(raw_wb)
    w_a = {iss.name: w / sum_a for iss, w in zip(issues, raw_wa)}
    w_b = {iss.name: w / sum_b for iss, w in zip(issues, raw_wb)}
    for issue in issues:
        nv = issue.cardinality
        ta = {i: rng.random() for i in range(nv)}
        tb = {i: max(0.0, min(1.0, 0.5 * ta[i] + 0.5 * (1 - ta[i]) + rng.uniform(-0.1, 0.1)))
              for i in range(nv)}
        vals_a[issue.name] = TableFun(ta)
        vals_b[issue.name] = TableFun(tb)
    ua = LUFun(values=vals_a, weights=w_a, outcome_space=os).scale_max(1.0)
    ub = LUFun(values=vals_b, weights=w_b, outcome_space=os).scale_max(1.0)
    return issues, os, ua, ub


def _make_high_opp(rng: random.Random):
    """High-opposition: both agents care about same issues with opposite values."""
    issues = [make_issue(name=f"i{j}", values=rng.randint(4, 7)) for j in range(3)]
    os = make_os(issues)
    raw = [rng.uniform(0.7, 1.0) for _ in issues]
    s = sum(raw)
    w_shared = {iss.name: w / s for iss, w in zip(issues, raw)}
    vals_a, vals_b = {}, {}
    for issue in issues:
        nv = issue.cardinality
        ta = {i: i / max(nv - 1, 1) for i in range(nv)}
        tb = {i: max(0.0, 1.0 - i / max(nv - 1, 1) + rng.uniform(-0.03, 0.03)) for i in range(nv)}
        lo, hi = min(tb.values()), max(tb.values())
        if hi > lo:
            tb = {k: (v - lo) / (hi - lo) for k, v in tb.items()}
        vals_a[issue.name] = TableFun(ta)
        vals_b[issue.name] = TableFun(tb)
    ua = LUFun(values=vals_a, weights=w_shared, outcome_space=os).scale_max(1.0)
    ub = LUFun(values=vals_b, weights=w_shared, outcome_space=os).scale_max(1.0)
    return issues, os, ua, ub


@dataclass
class Scenario:
    name: str
    issues: list
    os: Any
    ufun_a: Any
    ufun_b: Any
    opposition: float
    task_type: str


def build_scenarios(rng: random.Random) -> list[Scenario]:
    scenarios = []

    for name, make_fn, task_type in [
        ("buyer_seller",   lambda: _make_buyer_seller(),    "buyer_seller"),
        ("integrative_4i", lambda: _make_integrative(rng),  "integrative"),
        ("medium_opp_3i",  lambda: _make_medium_opp(rng),   "medium_opp"),
        ("high_opp_3i",    lambda: _make_high_opp(rng),     "high_opp"),
    ]:
        issues, os_, ua, ub = make_fn()
        outs = list(enumerate_issues(issues))
        try:
            opp = opposition_level([ua, ub], outcomes=outs)
        except Exception:
            opp = 0.0
        scenarios.append(Scenario(name, issues, os_, ua, ub, opp, task_type))

    return scenarios


# ════════════════════════════════════════════════════════════════════════════
#  OPPONENT ROSTER
# ════════════════════════════════════════════════════════════════════════════

OPPONENT_CLASSES = [
    ("MiCRO",       MiCRONegotiator),
    ("Aspiration",  AspirationNegotiator),
    ("Boulware",    BoulwareTBNegotiator),
    ("TitForTat",   NaiveTitForTatNegotiator),
    ("Linear",      LinearTBNegotiator),
    ("TBConceder",  TimeBasedConcedingNegotiator),
    ("Conceder",    ConcederTBNegotiator),
    ("Nice",        NiceNegotiator),
    ("Tough",       ToughNegotiator),
    ("Random",      RandomNegotiator),
]


# ════════════════════════════════════════════════════════════════════════════
#  RESULT DATACLASSES
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class NegotiationResult:
    config_name: str
    opponent_name: str
    scenario_name: str
    agreed: bool
    our_utility: float
    opp_utility: float
    welfare: float
    n_rounds: int
    trace: list[RoundTrace]
    proposed_utilities: list[float]
    received_utilities: list[float]
    opp_estimated_utilities: list[float]
    expert_selection: list[int]
    final_expert_weights: list[float]
    final_expert_ema: list[float]
    opp_style_final: dict


@dataclass
class ConfigSummary:
    config_name: str
    color: str
    agreement_rate: float
    avg_our_utility: float
    avg_opp_utility: float
    avg_welfare: float
    avg_rounds: float
    results_by_opponent: dict[str, list[NegotiationResult]] = field(default_factory=dict)
    results_by_scenario: dict[str, list[NegotiationResult]] = field(default_factory=dict)
    all_results: list[NegotiationResult] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════════════
#  RUNNER
# ════════════════════════════════════════════════════════════════════════════

N_STEPS = 100
SEED_BASE = 42


def run_negotiation(
    cfg: AgentConfig,
    ufun_a: Any,
    ufun_b: Any,
    opponent_cls,
    scenario_name: str,
    opponent_name: str,
    n_steps: int = N_STEPS,
    seed: int = 0,
) -> NegotiationResult:
    """Run one negotiation; our agent is party A."""
    random.seed(seed)
    our_agent = InstrumentedHybridAgent(cfg=cfg)

    mech = SAOMechanism(
        issues=ufun_a.outcome_space.issues,
        n_steps=n_steps,
        time_limit=None,
        seed=seed,
    )

    try:
        opp = opponent_cls()
    except Exception:
        opp = opponent_cls(name=opponent_name)

    mech.add(our_agent, preferences=ufun_a)
    mech.add(opp, preferences=ufun_b)

    mech.run()

    state = mech.state
    agreement = state.agreement
    agreed = agreement is not None

    our_utility = float(ufun_a(agreement)) if agreed else 0.0
    opp_utility = float(ufun_b(agreement)) if agreed else 0.0
    welfare = our_utility + opp_utility if agreed else 0.0

    n_rounds = state.step if state.step else 0

    return NegotiationResult(
        config_name=cfg.name,
        opponent_name=opponent_name,
        scenario_name=scenario_name,
        agreed=agreed,
        our_utility=our_utility,
        opp_utility=opp_utility,
        welfare=welfare,
        n_rounds=n_rounds,
        trace=list(our_agent.trace),
        proposed_utilities=list(our_agent.proposed_utilities),
        received_utilities=list(our_agent.received_utilities),
        opp_estimated_utilities=list(our_agent.opp_estimated_utilities),
        expert_selection=list(our_agent.expert_selection_history),
        final_expert_weights=list(our_agent._meta.weights) if hasattr(our_agent, "_meta") else [],
        final_expert_ema=list(our_agent._meta.expert_ema) if hasattr(our_agent, "_meta") else [],
        opp_style_final=our_agent._opp_model.get_style_features() if hasattr(our_agent, "_opp_model") else {},
    )


def _trial_seed(cfg_name: str, scenario_name: str, opp_name: str, rep: int) -> int:
    """Deterministic seed per (config, scenario, opponent, rep) — stable across runs."""
    return SEED_BASE ^ hash(f"{cfg_name}|{scenario_name}|{opp_name}|{rep}") & 0xFFFFFFFF


def run_all(
    configs: list[AgentConfig],
    scenarios: list[Scenario],
    opponents: list[tuple[str, type]],
    reps_per_pair: int = 3,
) -> dict[str, ConfigSummary]:
    """Run all config × scenario × opponent combinations and collect results."""
    summaries: dict[str, ConfigSummary] = {}

    total = len(configs) * len(scenarios) * len(opponents) * reps_per_pair
    done = 0
    t0 = time.time()

    for cfg in configs:
        all_results: list[NegotiationResult] = []
        results_by_opp: dict[str, list[NegotiationResult]] = {o[0]: [] for o in opponents}
        results_by_scen: dict[str, list[NegotiationResult]] = {s.name: [] for s in scenarios}

        for scenario in scenarios:
            for opp_name, opp_cls in opponents:
                for rep in range(reps_per_pair):
                    seed = _trial_seed(cfg.name, scenario.name, opp_name, rep)
                    try:
                        result = run_negotiation(
                            cfg=cfg,
                            ufun_a=scenario.ufun_a,
                            ufun_b=scenario.ufun_b,
                            opponent_cls=opp_cls,
                            scenario_name=scenario.name,
                            opponent_name=opp_name,
                            seed=seed,
                        )
                    except Exception as e:
                        print(f"  [WARN] {cfg.name} vs {opp_name} on {scenario.name}: {e}")
                        result = NegotiationResult(
                            config_name=cfg.name, opponent_name=opp_name,
                            scenario_name=scenario.name, agreed=False,
                            our_utility=0.0, opp_utility=0.0, welfare=0.0,
                            n_rounds=0, trace=[], proposed_utilities=[],
                            received_utilities=[], opp_estimated_utilities=[],
                            expert_selection=[], final_expert_weights=[],
                            final_expert_ema=[], opp_style_final={},
                        )

                    all_results.append(result)
                    results_by_opp[opp_name].append(result)
                    results_by_scen[scenario.name].append(result)

                    done += 1
                    if done % 20 == 0:
                        elapsed = time.time() - t0
                        rate = done / elapsed if elapsed > 0 else 1
                        eta = (total - done) / rate
                        print(f"  [{done}/{total}] {cfg.name} vs {opp_name} on {scenario.name} | ETA {eta:.0f}s")

        # Compute aggregate stats
        n = len(all_results)
        n_agreed = sum(r.agreed for r in all_results)
        agreement_rate = n_agreed / n if n > 0 else 0.0
        agreed_results = [r for r in all_results if r.agreed]
        avg_our = sum(r.our_utility for r in agreed_results) / len(agreed_results) if agreed_results else 0.0
        avg_opp = sum(r.opp_utility for r in agreed_results) / len(agreed_results) if agreed_results else 0.0
        avg_welfare = sum(r.welfare for r in agreed_results) / len(agreed_results) if agreed_results else 0.0
        avg_rounds = sum(r.n_rounds for r in all_results) / n if n > 0 else 0.0

        summaries[cfg.name] = ConfigSummary(
            config_name=cfg.name,
            color=cfg.color,
            agreement_rate=agreement_rate,
            avg_our_utility=avg_our,
            avg_opp_utility=avg_opp,
            avg_welfare=avg_welfare,
            avg_rounds=avg_rounds,
            results_by_opponent=results_by_opp,
            results_by_scenario=results_by_scen,
            all_results=all_results,
        )
        print(f"\n[{cfg.name}] agree={agreement_rate:.1%} | our={avg_our:.3f} | "
              f"opp={avg_opp:.3f} | welfare={avg_welfare:.3f}\n")

    return summaries


# ════════════════════════════════════════════════════════════════════════════
#  PLOTTING
# ════════════════════════════════════════════════════════════════════════════

EXPERT_NAMES = ["Boulware", "Pareto", "NiceTFT", "Forecast", "DealSeeker"]
EXPERT_COLORS = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6"]


def _save(fig, name: str):
    path = OUTPUT_DIR / f"{name}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Saved {path.name}")
    plt.close(fig)


# ── 1. Overall performance bar chart ────────────────────────────────────────
def plot_overall_performance(summaries: dict[str, ConfigSummary]):
    """Bar chart comparing key metrics across configs."""
    names = list(summaries.keys())
    colors = [summaries[n].color for n in names]
    metrics = {
        "Agreement Rate": [summaries[n].agreement_rate for n in names],
        "Avg Our Utility\n(agreed only)": [summaries[n].avg_our_utility for n in names],
        "Avg Welfare\n(agreed only)": [summaries[n].avg_welfare for n in names],
        "Avg Opp Utility\n(agreed only)": [summaries[n].avg_opp_utility for n in names],
    }

    fig, axes = plt.subplots(1, len(metrics), figsize=(5 * len(metrics), 5))
    fig.suptitle("Overall Performance Comparison", fontsize=14, fontweight="bold")

    for ax, (metric, vals) in zip(axes, metrics.items()):
        bars = ax.bar(names, vals, color=colors, edgecolor="black", linewidth=0.8)
        ax.set_title(metric, fontsize=11)
        ax.set_ylim(0, max(vals) * 1.15 if max(vals) > 0 else 1.0)
        ax.set_xticklabels(names, rotation=20, ha="right", fontsize=9)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{val:.3f}", ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    _save(fig, "01_overall_performance")


# ── 2. Agreement rate by opponent ────────────────────────────────────────────
def plot_agreement_by_opponent(summaries: dict[str, ConfigSummary]):
    """Grouped bar chart of agreement rate per opponent type."""
    cfg_names = list(summaries.keys())
    opponents = list(next(iter(summaries.values())).results_by_opponent.keys())

    x = np.arange(len(opponents))
    width = 0.8 / len(cfg_names)

    fig, ax = plt.subplots(figsize=(max(12, len(opponents) * 1.4), 5))
    fig.suptitle("Agreement Rate by Opponent", fontsize=14, fontweight="bold")

    for i, cfg_name in enumerate(cfg_names):
        s = summaries[cfg_name]
        rates = []
        for opp in opponents:
            results = s.results_by_opponent[opp]
            n = len(results)
            rate = sum(r.agreed for r in results) / n if n > 0 else 0.0
            rates.append(rate)
        offset = (i - len(cfg_names) / 2 + 0.5) * width
        bars = ax.bar(x + offset, rates, width * 0.9, label=cfg_name,
                      color=s.color, edgecolor="black", linewidth=0.6)

    ax.set_xticks(x)
    ax.set_xticklabels(opponents, rotation=30, ha="right")
    ax.set_ylabel("Agreement Rate")
    ax.set_ylim(0, 1.1)
    ax.axhline(y=1.0, color="grey", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.legend(loc="upper right")
    fig.tight_layout()
    _save(fig, "02_agreement_by_opponent")


# ── 3. Utility by opponent ────────────────────────────────────────────────────
def plot_utility_by_opponent(summaries: dict[str, ConfigSummary]):
    """Our average utility on agreed deals per opponent."""
    cfg_names = list(summaries.keys())
    opponents = list(next(iter(summaries.values())).results_by_opponent.keys())

    x = np.arange(len(opponents))
    width = 0.8 / len(cfg_names)

    fig, ax = plt.subplots(figsize=(max(12, len(opponents) * 1.4), 5))
    fig.suptitle("Avg Our Utility per Opponent (agreed deals only)", fontsize=14, fontweight="bold")

    for i, cfg_name in enumerate(cfg_names):
        s = summaries[cfg_name]
        utils = []
        for opp in opponents:
            results = [r for r in s.results_by_opponent[opp] if r.agreed]
            u = sum(r.our_utility for r in results) / len(results) if results else 0.0
            utils.append(u)
        offset = (i - len(cfg_names) / 2 + 0.5) * width
        ax.bar(x + offset, utils, width * 0.9, label=cfg_name,
               color=s.color, edgecolor="black", linewidth=0.6)

    ax.set_xticks(x)
    ax.set_xticklabels(opponents, rotation=30, ha="right")
    ax.set_ylabel("Average Our Utility")
    ax.set_ylim(0, 1.05)
    ax.legend(loc="upper right")
    fig.tight_layout()
    _save(fig, "03_utility_by_opponent")


# ── 4. Concession curves (mean proposed & received utilities over time) ───────
def plot_concession_curves(summaries: dict[str, ConfigSummary]):
    """
    Show how our proposed utility changes over relative time for each config.
    Averaged across all negotiations.
    """
    N_BINS = 20
    bins = np.linspace(0, 1, N_BINS + 1)
    bin_centers = (bins[:-1] + bins[1:]) / 2

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Concession Curves (time-binned averages)", fontsize=14, fontweight="bold")

    for cfg_name, s in summaries.items():
        # Proposed utility curve
        proposed_by_bin = [[] for _ in range(N_BINS)]
        received_by_bin = [[] for _ in range(N_BINS)]

        for result in s.all_results:
            for trace_pt in result.trace:
                b = min(int(trace_pt.t * N_BINS), N_BINS - 1)
                received_by_bin[b].append(trace_pt.my_utility)

        for result in s.all_results:
            n = len(result.proposed_utilities)
            for idx, u in enumerate(result.proposed_utilities):
                t_approx = idx / max(n - 1, 1)
                b = min(int(t_approx * N_BINS), N_BINS - 1)
                proposed_by_bin[b].append(u)

        prop_means = [np.mean(b) if b else np.nan for b in proposed_by_bin]
        recv_means = [np.mean(b) if b else np.nan for b in received_by_bin]

        axes[0].plot(bin_centers, prop_means, marker="o", markersize=3,
                     label=cfg_name, color=s.color)
        axes[1].plot(bin_centers, recv_means, marker="o", markersize=3,
                     label=cfg_name, color=s.color)

    for ax, title in zip(axes, ["Our Proposed Utility", "Received Offer Utility (our ufun)"]):
        ax.set_xlabel("Relative Time")
        ax.set_ylabel("Utility")
        ax.set_title(title)
        ax.legend()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.05)
        ax.grid(alpha=0.3)

    fig.tight_layout()
    _save(fig, "04_concession_curves")


# ── 5. Expert usage heatmap per config ───────────────────────────────────────
def plot_expert_usage_heatmap(summaries: dict[str, ConfigSummary]):
    """
    Heatmap: rows = configs, cols = time phases, cells = fraction using each expert.
    One figure per expert (5 total) + one combined figure.
    """
    N_PHASES = 5
    phase_labels = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"]
    cfg_names = list(summaries.keys())
    n_experts = len(EXPERT_NAMES)

    # Build matrices: shape (n_configs, n_phases, n_experts)
    # usage_matrix[c][p][e] = fraction of time in phase p config c uses expert e
    usage = np.zeros((len(cfg_names), N_PHASES, n_experts))

    for c_idx, cfg_name in enumerate(cfg_names):
        s = summaries[cfg_name]
        phase_counts = np.zeros((N_PHASES, n_experts))
        for result in s.all_results:
            for tr in result.trace:
                p = min(int(tr.t * N_PHASES), N_PHASES - 1)
                e = tr.expert_idx
                if 0 <= e < n_experts:
                    phase_counts[p][e] += 1
        phase_totals = phase_counts.sum(axis=1, keepdims=True)
        usage[c_idx] = phase_counts / np.where(phase_totals > 0, phase_totals, 1)

    # One subplot per config showing phase × expert usage
    fig, axes = plt.subplots(1, len(cfg_names), figsize=(5 * len(cfg_names), 5))
    if len(cfg_names) == 1:
        axes = [axes]
    fig.suptitle("Expert Usage by Phase (fraction of rounds)", fontsize=14, fontweight="bold")

    for c_idx, (ax, cfg_name) in enumerate(zip(axes, cfg_names)):
        data = usage[c_idx].T   # (n_experts, N_PHASES)
        im = ax.imshow(data, aspect="auto", vmin=0, vmax=1, cmap="YlOrRd")
        ax.set_xticks(range(N_PHASES))
        ax.set_xticklabels(phase_labels, rotation=30, ha="right", fontsize=8)
        ax.set_yticks(range(n_experts))
        ax.set_yticklabels(EXPERT_NAMES, fontsize=9)
        ax.set_title(cfg_name, fontsize=10)
        for e in range(n_experts):
            for p in range(N_PHASES):
                val = data[e, p]
                ax.text(p, e, f"{val:.2f}", ha="center", va="center",
                        fontsize=7, color="black" if val < 0.6 else "white")

    plt.colorbar(im, ax=axes[-1], label="Fraction")
    fig.tight_layout()
    _save(fig, "05_expert_usage_heatmap")


# ── 6. Opponent model accuracy ──────────────────────────────────────────────
def plot_opponent_model_accuracy(summaries: dict[str, ConfigSummary]):
    """
    Scatter: estimated opp utility vs actual opp utility on agreed outcomes.
    Shows how accurate the frequency-based opponent model is.
    Note: 'actual' here means the opponent's ufun evaluated on the agreement.
    Since we don't have a direct per-round ground truth, we use the
    time-averaged estimated utility vs final agreement utility.
    """
    fig, axes = plt.subplots(1, len(summaries), figsize=(5 * len(summaries), 5))
    if len(summaries) == 1:
        axes = [axes]
    fig.suptitle("Opponent Model: Estimated vs Actual Utility at Agreement", fontsize=13, fontweight="bold")

    for ax, (cfg_name, s) in zip(axes, summaries.items()):
        estimated = []
        actual = []
        for result in s.all_results:
            if result.agreed and result.opp_estimated_utilities:
                # Use last 5 rounds' average estimate
                last_est = np.mean(result.opp_estimated_utilities[-5:])
                estimated.append(last_est)
                actual.append(result.opp_utility)

        if estimated:
            ax.scatter(estimated, actual, alpha=0.5, s=20, color=s.color)
            lo, hi = 0, 1
            ax.plot([lo, hi], [lo, hi], "k--", linewidth=1, label="perfect")
            # Correlation
            if len(estimated) > 2:
                corr = np.corrcoef(estimated, actual)[0, 1]
                ax.set_title(f"{cfg_name}\n(r={corr:.3f})", fontsize=10)
            else:
                ax.set_title(cfg_name, fontsize=10)
        ax.set_xlabel("Estimated Opp Utility (freq model)")
        ax.set_ylabel("Actual Opp Utility")
        ax.set_xlim(0, 1.05)
        ax.set_ylim(0, 1.05)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)

    fig.tight_layout()
    _save(fig, "06_opponent_model_accuracy")


# ── 7. Distribution of final utilities (violin + box) ────────────────────────
def plot_utility_distributions(summaries: dict[str, ConfigSummary]):
    """Violin/box plot of our utility on agreed negotiations."""
    cfg_names = list(summaries.keys())
    data = [
        [r.our_utility for r in summaries[n].all_results if r.agreed]
        for n in cfg_names
    ]
    data_all = [
        [r.our_utility for r in summaries[n].all_results]
        for n in cfg_names
    ]
    colors = [summaries[n].color for n in cfg_names]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Our Utility Distribution", fontsize=14, fontweight="bold")

    for ax, d, title in zip(axes, [data, data_all], ["Agreed Negotiations Only", "All Negotiations (0 if no deal)"]):
        parts = ax.violinplot(d, showmedians=True, showextrema=True)
        for i, (pc, c) in enumerate(zip(parts["bodies"], colors)):
            pc.set_facecolor(c)
            pc.set_alpha(0.7)
        ax.set_xticks(range(1, len(cfg_names) + 1))
        ax.set_xticklabels(cfg_names, rotation=20, ha="right")
        ax.set_ylabel("Our Utility")
        ax.set_title(title)
        ax.set_ylim(-0.05, 1.1)
        ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    _save(fig, "07_utility_distributions")


# ── 8. Per-scenario performance heatmap ─────────────────────────────────────
def plot_scenario_heatmap(summaries: dict[str, ConfigSummary]):
    """Heatmap: config × scenario → agreement rate."""
    cfg_names = list(summaries.keys())
    scenario_names = list(next(iter(summaries.values())).results_by_scenario.keys())

    agreement_matrix = np.zeros((len(cfg_names), len(scenario_names)))
    utility_matrix = np.zeros((len(cfg_names), len(scenario_names)))

    for c_idx, cfg_name in enumerate(cfg_names):
        s = summaries[cfg_name]
        for s_idx, scen_name in enumerate(scenario_names):
            results = s.results_by_scenario[scen_name]
            n = len(results)
            agreement_matrix[c_idx, s_idx] = sum(r.agreed for r in results) / n if n > 0 else 0.0
            agreed = [r for r in results if r.agreed]
            utility_matrix[c_idx, s_idx] = (
                sum(r.our_utility for r in agreed) / len(agreed) if agreed else 0.0
            )

    fig, axes = plt.subplots(1, 2, figsize=(14, max(4, len(cfg_names) * 0.8 + 2)))
    fig.suptitle("Performance per Scenario", fontsize=14, fontweight="bold")

    for ax, matrix, title, fmt in zip(
        axes,
        [agreement_matrix, utility_matrix],
        ["Agreement Rate", "Avg Our Utility (agreed)"],
        [".2f", ".2f"],
    ):
        im = ax.imshow(matrix, aspect="auto", vmin=0, vmax=1, cmap="RdYlGn")
        ax.set_xticks(range(len(scenario_names)))
        ax.set_xticklabels(scenario_names, rotation=40, ha="right", fontsize=9)
        ax.set_yticks(range(len(cfg_names)))
        ax.set_yticklabels(cfg_names, fontsize=10)
        ax.set_title(title, fontsize=11)
        for c in range(len(cfg_names)):
            for s_ in range(len(scenario_names)):
                val = matrix[c, s_]
                ax.text(s_, c, format(val, fmt), ha="center", va="center",
                        fontsize=8, color="black" if val < 0.7 else "white")
        plt.colorbar(im, ax=ax)

    fig.tight_layout()
    _save(fig, "08_scenario_heatmap")


# ── 9. Expert EMA reward trajectory (sample negotiations) ────────────────────
def plot_expert_reward_trace(summaries: dict[str, ConfigSummary], n_sample: int = 3):
    """
    For a sample of negotiations, plot which expert was selected each round
    and the cumulative reward.
    """
    cfg_names = list(summaries.keys())
    n_configs = len(cfg_names)

    fig, axes = plt.subplots(n_configs, n_sample, figsize=(5 * n_sample, 3 * n_configs),
                              squeeze=False)
    fig.suptitle("Expert Selection Trace (sample negotiations)", fontsize=14, fontweight="bold")

    for c_idx, cfg_name in enumerate(cfg_names):
        s = summaries[cfg_name]
        # Pick negotiations with traces
        candidates = [r for r in s.all_results if len(r.trace) >= 5]
        samples = candidates[:n_sample] if len(candidates) >= n_sample else candidates

        for s_idx in range(n_sample):
            ax = axes[c_idx][s_idx]
            if s_idx >= len(samples):
                ax.axis("off")
                continue
            result = samples[s_idx]

            ts = [tr.t for tr in result.trace]
            expert_idxs = [tr.expert_idx for tr in result.trace]
            my_utils = [tr.my_utility for tr in result.trace]

            # Color strip for expert selection
            for j, (t_val, eidx) in enumerate(zip(ts, expert_idxs)):
                if 0 <= eidx < len(EXPERT_COLORS):
                    ax.axvline(t_val, color=EXPERT_COLORS[eidx], alpha=0.3, linewidth=2)

            ax.plot(ts, my_utils, "k-", linewidth=1.5, label="recv util", zorder=5)
            ax.set_ylim(0, 1.1)
            ax.set_xlim(0, 1)
            title = f"{cfg_name}\nvs {result.opponent_name} / {result.scenario_name}"
            title += f"\n{'AGREED' if result.agreed else 'NO DEAL'}"
            if result.agreed:
                title += f" u={result.our_utility:.2f}"
            ax.set_title(title, fontsize=7)
            ax.set_xlabel("t", fontsize=7)
            ax.set_ylabel("utility", fontsize=7)
            ax.tick_params(labelsize=6)

    # Legend for experts
    patches = [mpatches.Patch(color=EXPERT_COLORS[i], label=EXPERT_NAMES[i])
               for i in range(len(EXPERT_NAMES))]
    fig.legend(handles=patches, loc="lower center", ncol=len(EXPERT_NAMES),
               fontsize=9, title="Expert (background color)")
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    _save(fig, "09_expert_selection_trace")


# ── 10. Radar / spider chart — multi-metric summary ──────────────────────────
def plot_radar(summaries: dict[str, ConfigSummary]):
    """Radar chart comparing configs on 5 axes."""
    metrics = ["Agreement\nRate", "Avg Our\nUtility", "Avg\nWelfare",
               "Opp\nFriendliness", "Deal\nQuality"]

    cfg_names = list(summaries.keys())
    n_metrics = len(metrics)
    angles = np.linspace(0, 2 * np.pi, n_metrics, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
    fig.suptitle("Multi-Metric Radar Comparison", fontsize=14, fontweight="bold")

    for cfg_name in cfg_names:
        s = summaries[cfg_name]
        # deal_quality = our_utility / max_possible (proxy: our_utility * agreement_rate)
        deal_quality = s.avg_our_utility * s.agreement_rate
        opp_friendliness = s.avg_opp_utility

        vals = [
            s.agreement_rate,
            s.avg_our_utility,
            min(s.avg_welfare / 2.0, 1.0),  # normalise welfare (max=2)
            opp_friendliness,
            deal_quality,
        ]
        vals += vals[:1]  # close the polygon

        ax.plot(angles, vals, linewidth=2, label=cfg_name, color=s.color)
        ax.fill(angles, vals, alpha=0.12, color=s.color)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(metrics, fontsize=10)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"], fontsize=7)
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.15))
    _save(fig, "10_radar_comparison")


# ── 11. Stalemate & style detection accuracy ─────────────────────────────────
def plot_opponent_style_detection(summaries: dict[str, ConfigSummary]):
    """
    Show how often the opponent model detects each opponent style correctly.
    Since we can't verify ground truth from outside, we show the fraction of
    negotiations where each style flag was set at end.
    """
    cfg_names = list(summaries.keys())
    opponents = list(next(iter(summaries.values())).results_by_opponent.keys())
    style_keys = ["is_hardheaded", "is_conceder", "is_micro_style", "is_tft_style", "is_stalemate"]
    style_labels = ["Hardheaded", "Conceder", "MiCRO", "TFT", "Stalemate"]

    fig, axes = plt.subplots(len(cfg_names), 1,
                              figsize=(max(12, len(opponents) * 1.2), 4 * len(cfg_names)))
    if len(cfg_names) == 1:
        axes = [axes]
    fig.suptitle("Opponent Style Detection Flags by Opponent Type", fontsize=13, fontweight="bold")

    x = np.arange(len(opponents))
    width = 0.15

    for c_idx, (ax, cfg_name) in enumerate(zip(axes, cfg_names)):
        s = summaries[cfg_name]
        for sk_idx, (sk, sl) in enumerate(zip(style_keys, style_labels)):
            rates = []
            for opp in opponents:
                results = s.results_by_opponent[opp]
                n = len(results)
                rate = sum(r.opp_style_final.get(sk, False) for r in results) / n if n > 0 else 0.0
                rates.append(rate)
            offset = (sk_idx - len(style_keys) / 2 + 0.5) * width
            ax.bar(x + offset, rates, width * 0.9, label=sl)

        ax.set_xticks(x)
        ax.set_xticklabels(opponents, rotation=30, ha="right")
        ax.set_ylabel("Detection Rate")
        ax.set_ylim(0, 1.1)
        ax.set_title(f"Config: {cfg_name}", fontsize=10)
        ax.legend(loc="upper right", fontsize=8, ncol=3)

    fig.tight_layout()
    _save(fig, "11_style_detection")


# ── 12. Welfare Pareto scatter ────────────────────────────────────────────────
def plot_pareto_scatter(summaries: dict[str, ConfigSummary]):
    """
    Scatter plot of (our_utility, opp_utility) for all agreed negotiations.
    Shows where outcomes land relative to social optimum.
    """
    fig, ax = plt.subplots(figsize=(7, 7))
    fig.suptitle("Outcome Space (agreed negotiations)", fontsize=14, fontweight="bold")

    for cfg_name, s in summaries.items():
        agreed = [r for r in s.all_results if r.agreed]
        if not agreed:
            continue
        xs = [r.opp_utility for r in agreed]
        ys = [r.our_utility for r in agreed]
        ax.scatter(xs, ys, alpha=0.4, s=25, color=s.color, label=cfg_name)
        # Mark centroid
        ax.scatter([np.mean(xs)], [np.mean(ys)], marker="*", s=200,
                   color=s.color, edgecolors="black", zorder=5)

    ax.set_xlabel("Opponent Utility")
    ax.set_ylabel("Our Utility")
    ax.set_xlim(-0.05, 1.1)
    ax.set_ylim(-0.05, 1.1)
    ax.plot([0, 1], [1, 0], "k--", linewidth=1, alpha=0.4, label="welfare=1 line")
    ax.legend()
    ax.grid(alpha=0.3)
    _save(fig, "12_pareto_scatter")


# ── MASTER REPORT ─────────────────────────────────────────────────────────────
def print_report(summaries: dict[str, ConfigSummary]):
    """Print tabular summary to console."""
    print("\n" + "=" * 80)
    print("IMPROVEMENT ANALYSIS REPORT")
    print("=" * 80)
    header = f"{'Config':<25} {'Agree%':>7} {'OurUtil':>8} {'OppUtil':>8} {'Welfare':>8} {'Rounds':>7}"
    print(header)
    print("-" * 80)
    for name, s in summaries.items():
        print(f"{name:<25} {s.agreement_rate:>7.1%} {s.avg_our_utility:>8.4f} "
              f"{s.avg_opp_utility:>8.4f} {s.avg_welfare:>8.4f} {s.avg_rounds:>7.1f}")
    print("=" * 80)

    # Per-opponent breakdown for each config
    for name, s in summaries.items():
        print(f"\n[{name}] Per-Opponent Breakdown:")
        print(f"  {'Opponent':<20} {'Agree':>6} {'OurUtil':>8} {'Rounds':>7}")
        for opp, results in s.results_by_opponent.items():
            n = len(results)
            ar = sum(r.agreed for r in results) / n if n > 0 else 0.0
            agreed = [r for r in results if r.agreed]
            ou = sum(r.our_utility for r in agreed) / len(agreed) if agreed else 0.0
            nr = sum(r.n_rounds for r in results) / n if n > 0 else 0.0
            print(f"  {opp:<20} {ar:>6.1%} {ou:>8.4f} {nr:>7.1f}")
    print()


def generate_all_plots(summaries: dict[str, ConfigSummary]):
    """Run all plot functions."""
    print("\n[Plotting] Generating graphs...")
    plot_overall_performance(summaries)
    plot_agreement_by_opponent(summaries)
    plot_utility_by_opponent(summaries)
    plot_concession_curves(summaries)
    plot_expert_usage_heatmap(summaries)
    plot_opponent_model_accuracy(summaries)
    plot_utility_distributions(summaries)
    plot_scenario_heatmap(summaries)
    plot_expert_reward_trace(summaries)
    plot_radar(summaries)
    plot_opponent_style_detection(summaries)
    plot_pareto_scatter(summaries)
    print(f"\n[Plotting] All graphs saved to {OUTPUT_DIR}")


# ════════════════════════════════════════════════════════════════════════════
#  CONFIGURATIONS — EDIT THIS SECTION TO TEST YOUR IMPROVEMENTS
# ════════════════════════════════════════════════════════════════════════════
#
#  Each AgentConfig entry is one "version" of HybridAgent you want to compare.
#
#  The BASELINE matches the current HybridAgent v2 defaults exactly.
#  Add more entries below to test hypotheses.
#
#  Example hypotheses to test:
#    - "What if we lower the min_util_floor_fraction from 0.35 to 0.25?"
#      → More deals but lower utility per deal
#    - "What if boulware_e is 0.15 instead of 0.08?"
#      → Faster concession → more agreements vs tough opponents
#    - "What if emergency_time is 0.80 instead of 0.88?"
#      → Earlier panic → more deals but cheaper
#    - "What if meta_dealseeker_threshold is 0.85?"
#      → DealSeeker kicks in earlier in endgame
#    - "What if pareto_alpha is 0.50?"
#      → More cooperative Pareto bidding → better welfare
#    - "What if opp_stalemate_repeats is 2 instead of 3?"
#      → Faster stalemate detection → breaks deadlocks earlier
#
# ════════════════════════════════════════════════════════════════════════════

CONFIGURATIONS: list[AgentConfig] = [
    # ── Baseline (current v2 defaults) ──────────────────────────────────────
    AgentConfig(
        name="v2_baseline",
        min_util_floor_fraction=0.35,
        initial_threshold=0.92,
        final_threshold=0.50,
        no_accept_rounds=2,
        emergency_time=0.88,
        boulware_e=0.08,
        pareto_e=0.10,
        pareto_alpha=0.30,
        forecast_base_e=0.10,
        meta_boulware_init_weight=2.0,
        meta_nicetft_init_weight=2.0,
        meta_dealseeker_threshold=0.93,
        meta_min_switches_apart=2,
        opp_time_segments=40,
        opp_stalemate_repeats=3,
        color="#2c7bb6",
    ),

    # ── Variant A: Lower utility floor → more deals ─────────────────────────
    AgentConfig(
        name="A_lower_floor",
        min_util_floor_fraction=0.25,      # was 0.35 — accept cheaper deals
        initial_threshold=0.92,
        final_threshold=0.40,              # was 0.50
        no_accept_rounds=2,
        emergency_time=0.85,               # was 0.88 — earlier emergency
        boulware_e=0.08,
        pareto_e=0.10,
        pareto_alpha=0.30,
        forecast_base_e=0.10,
        meta_boulware_init_weight=2.0,
        meta_nicetft_init_weight=2.0,
        meta_dealseeker_threshold=0.90,    # was 0.93 — earlier DealSeeker
        meta_min_switches_apart=2,
        opp_time_segments=40,
        opp_stalemate_repeats=3,
        color="#d7191c",
    ),

    # ── Variant B: More aggressive concession ────────────────────────────────
    AgentConfig(
        name="B_faster_concede",
        min_util_floor_fraction=0.35,
        initial_threshold=0.90,            # was 0.92
        final_threshold=0.50,
        no_accept_rounds=2,
        emergency_time=0.88,
        boulware_e=0.15,                   # was 0.08 — concede faster
        pareto_e=0.15,                     # was 0.10
        pareto_alpha=0.35,                 # was 0.30 — more cooperative
        forecast_base_e=0.15,              # was 0.10
        meta_boulware_init_weight=1.5,     # was 2.0 — less Boulware dominance
        meta_nicetft_init_weight=2.5,      # was 2.0 — more TFT early
        meta_dealseeker_threshold=0.90,    # earlier DealSeeker
        meta_min_switches_apart=1,         # was 2 — faster expert switching
        opp_time_segments=40,
        opp_stalemate_repeats=2,           # was 3 — detect stalemate faster
        color="#1a9641",
    ),

    # ── Variant C: High-utility hold (tighter) ───────────────────────────────
    AgentConfig(
        name="C_hold_ground",
        min_util_floor_fraction=0.45,      # was 0.35 — never accept cheap deals
        initial_threshold=0.95,            # was 0.92 — very tight opening
        final_threshold=0.60,              # was 0.50 — keep floor high
        no_accept_rounds=3,                # was 2 — more patience
        emergency_time=0.92,               # was 0.88 — panic late
        boulware_e=0.05,                   # was 0.08 — ultra slow concession
        pareto_e=0.08,
        pareto_alpha=0.25,                 # was 0.30 — less cooperative
        forecast_base_e=0.08,
        meta_boulware_init_weight=3.0,     # was 2.0 — Boulware strongly preferred
        meta_nicetft_init_weight=1.0,      # was 2.0 — less TFT
        meta_dealseeker_threshold=0.95,    # was 0.93 — delay DealSeeker
        meta_min_switches_apart=3,         # was 2 — less switching
        opp_time_segments=40,
        opp_stalemate_repeats=4,           # was 3 — less sensitive to stalemate
        color="#fdae61",
    ),
]


# ════════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("  HybridAgent Improvement Analysis")
    print(f"  Configs: {[c.name for c in CONFIGURATIONS]}")
    print(f"  Output:  {OUTPUT_DIR}")
    print(f"{'='*60}\n")

    rng = random.Random(SEED_BASE)
    scenarios = build_scenarios(rng)
    print(f"Built {len(scenarios)} scenarios: {[s.name for s in scenarios]}")
    print(f"Running against {len(OPPONENT_CLASSES)} opponents: {[o[0] for o in OPPONENT_CLASSES]}")
    print(f"Configurations to test: {len(CONFIGURATIONS)}")

    REPS = 3  # negotiations per (config, scenario, opponent) triple
    print(f"Repetitions per pair: {REPS}")
    total = len(CONFIGURATIONS) * len(scenarios) * len(OPPONENT_CLASSES) * REPS
    print(f"Total negotiations: {total}\n")

    summaries = run_all(CONFIGURATIONS, scenarios, OPPONENT_CLASSES, reps_per_pair=REPS)
    print_report(summaries)
    generate_all_plots(summaries)

    print(f"\nDone! All output in: {OUTPUT_DIR}")
    print("Open the PNG files to compare configurations.")
    print("\nTo test a new improvement, edit the CONFIGURATIONS list at the")
    print("bottom of test_improvement.py and re-run the script.")
