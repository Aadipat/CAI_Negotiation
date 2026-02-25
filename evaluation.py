"""
Evaluation script for GeniusWeb agents wrapped via negmas_geniusweb_bridge.

Uses NegMAS built-in metrics (Pareto optimality, Nash optimality, Kalai,
welfare, etc.) and diverse scenarios with controlled opposition levels
to properly differentiate agent quality.
"""

from __future__ import annotations

import csv
import math
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Output directory setup ──────────────────────────────────────────────────
_OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
_OUTPUT_ROOT.mkdir(exist_ok=True)
_RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = _OUTPUT_ROOT / _RUN_TIMESTAMP
OUTPUT_DIR.mkdir(exist_ok=True)


class _Tee:
    """Duplicate writes to both a file and the original stream."""

    def __init__(self, stream, filepath: Path):
        self._stream = stream
        self._file = open(filepath, "w", encoding="utf-8")

    def write(self, data):
        self._stream.write(data)
        self._file.write(data)
        self._file.flush()

    def flush(self):
        self._stream.flush()
        self._file.flush()

    def close(self):
        self._file.close()

    def __getattr__(self, name):
        return getattr(self._stream, name)


# ── NegMAS imports ──────────────────────────────────────────────────────────
from negmas import (
    SAOMechanism,
    Scenario,
    AspirationNegotiator,
    TimeBasedConcedingNegotiator,
    MiCRONegotiator,
    NaiveTitForTatNegotiator,
    make_issue,
    make_os,
    enumerate_issues,
    conflict_level,
    opposition_level,
    calc_scenario_stats,
    calc_outcome_distances,
    calc_outcome_optimality,
)
from negmas.preferences import LinearAdditiveUtilityFunction as LUFun
from negmas.preferences.value_fun import (
    AffineFun,
    IdentityFun,
    LinearFun,
    TableFun,
)

# ── Bridge imports ──────────────────────────────────────────────────────────
_bridge_src = Path(__file__).resolve().parent / "ExampleAgents" / "src"
if str(_bridge_src) not in sys.path:
    sys.path.insert(0, str(_bridge_src))

_vendor = Path(__file__).resolve().parent / "ExampleAgents" / "vendor"
for _sub in (
    "geniusweb-1.2.1",
    "others/tudelft_utilities",
    "others/tudelft_utilities_logging",
    "others/uri",
    "others/pyson",
):
    _p = _vendor / _sub
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from negmas_geniusweb_bridge import ALL_AGENTS, BROKEN_AGENTS

# ── Import HybridAgent ─────────────────────────────────────────────────────
_feiyang_dir = Path(__file__).resolve().parent
if str(_feiyang_dir) not in sys.path:
    sys.path.insert(0, str(_feiyang_dir))
from feiyang.hybrid_agent import HybridAgent

# HybridAgent already inherits from SAONegotiator — no wrapping needed.

# ── Configuration ───────────────────────────────────────────────────────────
SEED = 42
N_STEPS = 50           # negotiation rounds per session (reduced for speed)
MAX_AGENTS = None      # set to an int to limit evaluation size
SKIP_AGENTS: set[str] = BROKEN_AGENTS.copy()
PER_NEG_TIMEOUT = 2.0  # seconds per negotiation (kills slow agents)
MAX_DIST = math.sqrt(2.0)  # max Euclidean distance in 2-agent [0,1]² space


# ═══════════════════════════════════════════════════════════════════════════
#  SCENARIO GENERATION — diverse domains with controlled opposition
# ═══════════════════════════════════════════════════════════════════════════

def _random_weights(issues, rng: random.Random) -> dict[str, float]:
    """Generate random issue weights that sum to 1."""
    raw = [rng.uniform(0.1, 1.0) for _ in issues]
    s = sum(raw)
    return {iss.name: w / s for iss, w in zip(issues, raw)}


def _divergent_weight_pair(issues, rng: random.Random):
    """
    Generate TWO weight vectors with guaranteed different priority orderings.

    Strategy: generate random weights for A, then reverse the ordering for B
    (with noise) so the agents' most- and least- important issues are swapped.
    This prevents zero-sum even after per-issue normalization.
    """
    n = len(issues)
    raw_a = [rng.uniform(0.1, 1.0) for _ in range(n)]
    # Reverse A's weights for B, then add noise
    raw_b = list(reversed(raw_a))
    raw_b = [max(0.05, w + rng.uniform(-0.2, 0.2)) for w in raw_b]
    sum_a, sum_b = sum(raw_a), sum(raw_b)
    weights_a = {iss.name: w / sum_a for iss, w in zip(issues, raw_a)}
    weights_b = {iss.name: w / sum_b for iss, w in zip(issues, raw_b)}
    return weights_a, weights_b


def _make_opposed_ufuns(issues, os, rng: random.Random, opposition_target: float = 0.6):
    """
    Generate a pair of LinearAdditive ufuns with genuine opposition.

    Uses DIVERGENT weights for A and B so the game is NOT zero-sum
    even when per-issue values are inversely correlated.  This ensures
    welfare varies across outcomes → non-trivial Pareto frontier.
    """
    vals_a, vals_b = {}, {}
    weights_a, weights_b = _divergent_weight_pair(issues, rng)

    for issue in issues:
        slope_a = rng.uniform(0.5, 2.0) * rng.choice([-1, 1])
        # Mix of correlated and anti-correlated based on opposition target
        slope_b = (1 - opposition_target) * slope_a + opposition_target * (-slope_a)
        slope_b += rng.uniform(-0.3, 0.3)  # larger noise to break exact correlation
        bias_a, bias_b = rng.uniform(0, 3), rng.uniform(0, 3)

        # Compute raw values and normalize to [0, 1]
        raw_a = {v: slope_a * v + bias_a for v in range(issue.cardinality)}
        raw_b = {v: slope_b * v + bias_b for v in range(issue.cardinality)}
        for raw, vals_dict in [(raw_a, vals_a), (raw_b, vals_b)]:
            lo, hi = min(raw.values()), max(raw.values())
            rng_v = hi - lo
            if rng_v > 0:
                normed = {k: (v - lo) / rng_v for k, v in raw.items()}
            else:
                normed = {k: 0.5 for k in raw}
            vals_dict[issue.name] = TableFun(normed)

    ua = LUFun(values=vals_a, weights=weights_a, outcome_space=os).scale_max(1.0)
    ub = LUFun(values=vals_b, weights=weights_b, outcome_space=os).scale_max(1.0)
    return ua, ub


def _make_table_ufuns(issues, os, rng: random.Random):
    """
    Generate pair of ufuns using per-value tables (non-linear).
    Produces richer, non-monotone preference landscapes.
    Uses divergent weights to avoid zero-sum.
    """
    vals_a, vals_b = {}, {}
    weights_a, weights_b = _divergent_weight_pair(issues, rng)

    for issue in issues:
        n = issue.cardinality
        table_a = {i: rng.random() for i in range(n)}
        table_b = {i: max(0.0, 1.0 - table_a[i] + rng.uniform(-0.3, 0.3)) for i in range(n)}
        vals_a[issue.name] = TableFun(table_a)
        vals_b[issue.name] = TableFun(table_b)

    ua = LUFun(values=vals_a, weights=weights_a, outcome_space=os).scale_max(1.0)
    ub = LUFun(values=vals_b, weights=weights_b, outcome_space=os).scale_max(1.0)
    return ua, ub


def _buyer_seller_ufuns(issues, os):
    """Classic buyer/seller: opposing on price & delivery, aligned on quantity."""
    buyer = LUFun(
        values={
            "price": AffineFun(-1, bias=9.0),
            "quantity": LinearFun(0.2),
            "delivery_time": IdentityFun(),
        },
        outcome_space=os,
    ).scale_max(1.0)
    seller = LUFun(
        values={
            "price": IdentityFun(),
            "quantity": LinearFun(0.2),
            "delivery_time": AffineFun(-1, bias=9.0),
        },
        outcome_space=os,
    ).scale_max(1.0)
    return buyer, seller


@dataclass
class ScenarioDef:
    """A pre-built negotiation scenario with metadata."""
    name: str
    issues: list
    os: Any
    ufun_a: Any
    ufun_b: Any
    stats: Any          # ScenarioStats from NegMAS
    opposition: float
    conflict: float
    n_pareto: int
    task_type: str = ""      # "buyer_seller", "linear", "table", "large"
    difficulty: str = ""     # "easy", "medium", "hard"
    n_outcomes: int = 0


def _classify_difficulty(opp: float) -> str:
    """Classify scenario difficulty based on measured opposition."""
    if opp < 0.3:
        return "easy"
    elif opp < 0.6:
        return "medium"
    return "hard"


def build_scenarios(rng: random.Random) -> list[ScenarioDef]:
    """
    Build a diverse set of scenarios covering:
      - Different issue counts (2, 3, 4, 5)
      - Different issue value ranges
      - Different opposition levels (low, medium, high)
      - Linear vs non-linear (table) value functions
      - A fixed buyer/seller domain
    """
    scenarios: list[ScenarioDef] = []

    # ── 1. Fixed buyer/seller domain ────────────────────────────────────
    bs_issues = [
        make_issue(name="price", values=10),
        make_issue(name="quantity", values=(1, 11)),
        make_issue(name="delivery_time", values=10),
    ]
    bs_os = make_os(bs_issues)
    buyer, seller = _buyer_seller_ufuns(bs_issues, bs_os)
    outcomes = list(enumerate_issues(bs_issues))
    stats = calc_scenario_stats((buyer, seller), outcomes=outcomes)
    cl = conflict_level(buyer, seller, outcomes=outcomes)
    opp = opposition_level([buyer, seller], outcomes=outcomes)
    scenarios.append(ScenarioDef(
        name="buyer_seller_3i",
        issues=bs_issues, os=bs_os,
        ufun_a=buyer, ufun_b=seller,
        stats=stats, opposition=opp, conflict=cl,
        n_pareto=len(stats.pareto_utils),
        task_type="buyer_seller",
        difficulty=_classify_difficulty(opp),
        n_outcomes=len(outcomes),
    ))

    # ── 2. Parametric scenarios with varied opposition ──────────────────
    configs = [
        # (label, n_issues, max_values, opposition_target, use_table)
        ("low_opp_2i",    2, 8,  0.3, False),
        ("high_opp_2i",   2, 8,  0.9, False),
        ("low_opp_3i",    3, 7,  0.3, False),
        ("high_opp_3i",   3, 7,  0.9, False),
        ("med_opp_4i",    4, 6,  0.6, False),
        ("high_opp_4i",   4, 6,  0.9, False),
        ("high_opp_5i",   5, 5,  0.9, False),
        # Table (non-linear) value functions
        ("table_3i",      3, 7,  0.0, True),
        # Large outcome spaces
        ("large_3i",      3, 15, 0.6, False),
        ("large_4i",      4, 10, 0.7, False),
    ]

    for label, n_issues, max_vals, opp_target, use_table in configs:
        issues = [
            make_issue(name=f"issue_{j}", values=rng.randint(3, max_vals))
            for j in range(n_issues)
        ]
        os = make_os(issues)
        if use_table:
            ua, ub = _make_table_ufuns(issues, os, rng)
        else:
            ua, ub = _make_opposed_ufuns(issues, os, rng, opposition_target=opp_target)

        outcomes = list(enumerate_issues(issues))
        try:
            stats = calc_scenario_stats((ua, ub), outcomes=outcomes)
            cl = conflict_level(ua, ub, outcomes=outcomes)
            opp = opposition_level([ua, ub], outcomes=outcomes)
        except Exception:
            continue

        _tt = "table" if label.startswith("table") else ("large" if label.startswith("large") else "linear")
        scenarios.append(ScenarioDef(
            name=label, issues=issues, os=os,
            ufun_a=ua, ufun_b=ub,
            stats=stats, opposition=opp, conflict=cl,
            n_pareto=len(stats.pareto_utils),
            task_type=_tt,
            difficulty=_classify_difficulty(opp),
            n_outcomes=len(outcomes),
        ))

    return scenarios


# ═══════════════════════════════════════════════════════════════════════════
#  RESULT CONTAINER
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class NegotiationResult:
    domain: str
    agent_a_name: str
    agent_b_name: str
    agreement: Any
    n_steps_taken: int
    n_steps_allowed: int
    timedout: bool
    broken: bool
    util_a: float | None = None
    util_b: float | None = None
    welfare: float | None = None
    nash_product: float | None = None
    pareto_dist: float | None = None
    pareto_optimality: float | None = None
    nash_optimality: float | None = None
    kalai_optimality: float | None = None
    max_welfare_opt: float | None = None
    opposition: float = 0.0
    wall_seconds: float = 0.0
    error: str = ""
    task_type: str = ""
    difficulty: str = ""
    n_outcomes: int = 0


# ═══════════════════════════════════════════════════════════════════════════
#  CORE EVALUATION RUNNER
# ═══════════════════════════════════════════════════════════════════════════

def run_single_negotiation(
    agent_a_cls,
    agent_b_cls,
    scenario: ScenarioDef,
    n_steps: int = N_STEPS,
    agent_a_name: str = "",
    agent_b_name: str = "",
    timeout: float = PER_NEG_TIMEOUT,
) -> NegotiationResult:
    """Run one bilateral negotiation and return a NegotiationResult."""
    a_name = agent_a_name or agent_a_cls.__name__
    b_name = agent_b_name or agent_b_cls.__name__

    try:
        mechanism = SAOMechanism(
            issues=scenario.issues, n_steps=n_steps,
            time_limit=timeout,
        )
        agent_a = agent_a_cls(ufun=scenario.ufun_a, name=a_name)
        agent_b = agent_b_cls(ufun=scenario.ufun_b, name=b_name)
        mechanism.add(agent_a)
        mechanism.add(agent_b)

        t0 = time.perf_counter()
        mechanism.run()
        elapsed = time.perf_counter() - t0

        state = mechanism.state
        agreement = state.agreement

        util_a = float(scenario.ufun_a(agreement)) if agreement is not None else None
        util_b = float(scenario.ufun_b(agreement)) if agreement is not None else None
        welfare = (util_a + util_b) if (util_a is not None and util_b is not None) else None
        nash_prod = (util_a * util_b) if (util_a is not None and util_b is not None) else None

        # ── NegMAS built-in optimality metrics ──────────────────────────
        p_dist = p_opt = n_opt = k_opt = mw_opt = None
        if util_a is not None and util_b is not None and scenario.stats is not None:
            try:
                dists = calc_outcome_distances((util_a, util_b), scenario.stats)
                p_dist = float(dists.pareto_dist) if not math.isnan(dists.pareto_dist) else None
                opt = calc_outcome_optimality(dists, scenario.stats, max_dist=MAX_DIST)
                p_opt = float(opt.pareto_optimality) if not math.isnan(opt.pareto_optimality) else None
                n_opt = float(opt.nash_optimality) if not math.isnan(opt.nash_optimality) else None
                k_opt = float(opt.kalai_optimality) if not math.isnan(opt.kalai_optimality) else None
                mw_opt = float(opt.max_welfare_optimality) if not math.isnan(opt.max_welfare_optimality) else None
            except Exception:
                pass

        return NegotiationResult(
            domain=scenario.name,
            agent_a_name=a_name,
            agent_b_name=b_name,
            agreement=agreement,
            n_steps_taken=state.step,
            n_steps_allowed=n_steps,
            timedout=state.timedout,
            broken=state.broken,
            util_a=util_a,
            util_b=util_b,
            welfare=welfare,
            nash_product=nash_prod,
            pareto_dist=p_dist,
            pareto_optimality=p_opt,
            nash_optimality=n_opt,
            kalai_optimality=k_opt,
            max_welfare_opt=mw_opt,
            opposition=scenario.opposition,
            wall_seconds=elapsed,
            task_type=scenario.task_type,
            difficulty=scenario.difficulty,
            n_outcomes=scenario.n_outcomes,
        )
    except Exception as exc:
        return NegotiationResult(
            domain=scenario.name,
            agent_a_name=a_name,
            agent_b_name=b_name,
            agreement=None,
            n_steps_taken=0,
            n_steps_allowed=n_steps,
            timedout=False,
            broken=True,
            opposition=scenario.opposition,
            error=str(exc),
            task_type=scenario.task_type,
            difficulty=scenario.difficulty,
            n_outcomes=scenario.n_outcomes,
        )


# ═══════════════════════════════════════════════════════════════════════════
#  REPORTING
# ═══════════════════════════════════════════════════════════════════════════

def print_header():
    print("=" * 150)
    print(f"{'Domain':<18} {'Agent A':<22} {'Agent B':<22} "
          f"{'Agree?':<7} {'U(A)':>6} {'U(B)':>6} {'Welfare':>8} "
          f"{'PDist':>6} {'POpt':>6} {'NOpt':>6} {'KOpt':>6} "
          f"{'Steps':>6} {'Time(s)':>8} {'Status':<10}")
    print("-" * 150)


def print_result(r: NegotiationResult):
    if r.error:
        status = "ERROR"
    elif r.broken:
        status = "BROKEN"
    elif r.timedout:
        status = "TIMEOUT"
    elif r.agreement is not None:
        status = "AGREED"
    else:
        status = "NO DEAL"

    ua = f"{r.util_a:.3f}" if r.util_a is not None else "  N/A"
    ub = f"{r.util_b:.3f}" if r.util_b is not None else "  N/A"
    w = f"{r.welfare:.3f}" if r.welfare is not None else "    N/A"
    pd = f"{r.pareto_dist:.3f}" if r.pareto_dist is not None else "  N/A"
    po = f"{r.pareto_optimality:.3f}" if r.pareto_optimality is not None else "  N/A"
    no = f"{r.nash_optimality:.3f}" if r.nash_optimality is not None else "  N/A"
    ko = f"{r.kalai_optimality:.3f}" if r.kalai_optimality is not None else "  N/A"
    agr = "Yes" if r.agreement is not None else "No"

    print(f"{r.domain:<18} {r.agent_a_name:<22} {r.agent_b_name:<22} "
          f"{agr:<7} {ua:>6} {ub:>6} {w:>8} "
          f"{pd:>6} {po:>6} {no:>6} {ko:>6} "
          f"{r.n_steps_taken:>6} {r.wall_seconds:>8.3f} {status:<10}")
    if r.error:
        print(f"  └─ Error: {r.error[:100]}")


def print_summary(results: list[NegotiationResult]):
    total = len(results)
    agreed = sum(1 for r in results if r.agreement is not None and not r.error)
    errors = sum(1 for r in results if r.error)
    timeouts = sum(1 for r in results if r.timedout)
    broken = sum(1 for r in results if r.broken and not r.error)

    welfares = [r.welfare for r in results if r.welfare is not None]
    avg_welfare = sum(welfares) / len(welfares) if welfares else 0.0

    p_opts = [r.pareto_optimality for r in results if r.pareto_optimality is not None]
    avg_popt = sum(p_opts) / len(p_opts) if p_opts else 0.0

    print("\n" + "=" * 120)
    print("SUMMARY")
    print("=" * 120)
    print(f"  Total negotiations    : {total}")
    print(f"  Agreements            : {agreed}  ({agreed / total * 100:.1f}%)" if total else "  Agreements: 0")
    print(f"  Timeouts              : {timeouts}")
    print(f"  Broken                : {broken}")
    print(f"  Errors                : {errors}")
    print(f"  Avg welfare (agreed)  : {avg_welfare:.4f}")
    print(f"  Avg Pareto optimality : {avg_popt:.4f}")
    print("=" * 120)


# ═══════════════════════════════════════════════════════════════════════════
#  ANALYSIS & CALIBRATION
# ═══════════════════════════════════════════════════════════════════════════

def _stdev(values: list[float]) -> float:
    """Sample standard deviation."""
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _avg_of(values: list[float]) -> float:
    """Safe average, returns 0 for empty list."""
    return sum(values) / len(values) if values else 0.0


def print_calibration_analysis(
    results: list[NegotiationResult],
    agent_stats: list[dict[str, Any]],
):
    """Score distributions by task type, difficulty, and outcome-space size."""
    print("\n" + "=" * 130)
    print("CALIBRATION ANALYSIS — Score Distributions by Scenario Bucket")
    print("=" * 130)

    # ── By Task Type ───────────────────────────────────────────────────
    print("\n  By Task Type:")
    print(f"    {'Type':<14} {'#Negs':>6} {'Agree%':>7} {'AvgU(A)':>8} "
          f"{'POpt':>7} {'NOpt':>7} {'Welfare':>8} {'sigma(U)':>9}")
    print("    " + "-" * 74)
    for tt in sorted(set(r.task_type for r in results if r.task_type)):
        sub = [r for r in results if r.task_type == tt]
        n = len(sub)
        agr = sum(1 for r in sub if r.agreement is not None and not r.error)
        us = [r.util_a for r in sub if r.util_a is not None]
        pos = [r.pareto_optimality for r in sub if r.pareto_optimality is not None]
        nos = [r.nash_optimality for r in sub if r.nash_optimality is not None]
        ws = [r.welfare for r in sub if r.welfare is not None]
        print(f"    {tt:<14} {n:>6} {agr / n * 100 if n else 0:>6.1f}% "
              f"{_avg_of(us):>8.4f} {_avg_of(pos):>7.4f} "
              f"{_avg_of(nos):>7.4f} {_avg_of(ws):>8.4f} "
              f"{_stdev(us):>9.4f}")

    # ── By Difficulty ──────────────────────────────────────────────────
    print("\n  By Difficulty:")
    print(f"    {'Level':<10} {'#Negs':>6} {'Agree%':>7} {'AvgU(A)':>8} "
          f"{'POpt':>7} {'sigma(U)':>9}")
    print("    " + "-" * 54)
    for diff in ["easy", "medium", "hard"]:
        sub = [r for r in results if r.difficulty == diff]
        if not sub:
            continue
        n = len(sub)
        agr = sum(1 for r in sub if r.agreement is not None and not r.error)
        us = [r.util_a for r in sub if r.util_a is not None]
        pos = [r.pareto_optimality for r in sub if r.pareto_optimality is not None]
        print(f"    {diff:<10} {n:>6} {agr / n * 100 if n else 0:>6.1f}% "
              f"{_avg_of(us):>8.4f} {_avg_of(pos):>7.4f} "
              f"{_stdev(us):>9.4f}")

    # ── By Outcome Space Size ──────────────────────────────────────────
    print("\n  By Outcome Space Size:")
    print(f"    {'Bucket':<16} {'#Negs':>6} {'Agree%':>7} {'AvgU(A)':>8} "
          f"{'POpt':>7} {'sigma(U)':>9}")
    print("    " + "-" * 58)
    for lbl, lo, hi in [("small (<=50)", 0, 50),
                         ("medium (<=200)", 51, 200),
                         ("large (>200)", 201, 999999)]:
        sub = [r for r in results if lo <= r.n_outcomes <= hi]
        if not sub:
            continue
        n = len(sub)
        agr = sum(1 for r in sub if r.agreement is not None and not r.error)
        us = [r.util_a for r in sub if r.util_a is not None]
        pos = [r.pareto_optimality for r in sub if r.pareto_optimality is not None]
        print(f"    {lbl:<16} {n:>6} {agr / n * 100 if n else 0:>6.1f}% "
              f"{_avg_of(us):>8.4f} {_avg_of(pos):>7.4f} "
              f"{_stdev(us):>9.4f}")

    # ── Per-Agent by Difficulty ────────────────────────────────────────
    print("\n  Per-Agent Utility by Difficulty (top agents + HybridAgent):")
    print(f"    {'Agent':<25} {'Easy':>8} {'Medium':>8} {'Hard':>8} {'Drop':>8}")
    print("    " + "-" * 62)
    abd: dict[str, dict[str, list[float]]] = {}
    for r in results:
        if not r.difficulty:
            continue
        abd.setdefault(r.agent_a_name, {}).setdefault(r.difficulty, []).append(
            r.util_a if r.util_a is not None else 0.0
        )
    name_rank = {s["name"]: i for i, s in enumerate(agent_stats)}
    ordered = sorted(abd.keys(), key=lambda n: name_rank.get(n, 9999))
    shown = 0
    for aname in ordered:
        is_h = aname == "HybridAgent"
        if shown >= 15 and not is_h:
            continue
        shown += 1
        d = abd[aname]
        eu = _avg_of(d.get("easy", []))
        mu = _avg_of(d.get("medium", []))
        hu = _avg_of(d.get("hard", []))
        drop = eu - hu
        mark = " <--" if is_h else ""
        print(f"    {aname:<25} {eu:>8.4f} {mu:>8.4f} {hu:>8.4f} {drop:>8.4f}{mark}")

    print("=" * 130)


def print_pairwise_analysis(results: list[NegotiationResult]):
    """Pairwise win/loss/draw from head-to-head matchups."""
    a_names = set(r.agent_a_name for r in results)
    h2h = [r for r in results
           if r.agent_b_name in a_names and r.agent_a_name != r.agent_b_name]
    if not h2h:
        return

    print("\n" + "=" * 100)
    print("PAIRWISE HEAD-TO-HEAD ANALYSIS")
    print("=" * 100)

    wins: dict[str, int] = {}
    losses: dict[str, int] = {}
    draws: dict[str, int] = {}
    games: dict[str, int] = {}
    h2h_util: dict[str, list[float]] = {}

    for r in h2h:
        a, b = r.agent_a_name, r.agent_b_name
        for nm in (a, b):
            wins.setdefault(nm, 0)
            losses.setdefault(nm, 0)
            draws.setdefault(nm, 0)
            games.setdefault(nm, 0)
            h2h_util.setdefault(nm, [])
        games[a] += 1
        games[b] += 1
        if r.util_a is not None and r.util_b is not None:
            h2h_util[a].append(r.util_a)
            h2h_util[b].append(r.util_b)
            if r.util_a > r.util_b + 0.01:
                wins[a] += 1
                losses[b] += 1
            elif r.util_b > r.util_a + 0.01:
                wins[b] += 1
                losses[a] += 1
            else:
                draws[a] += 1
                draws[b] += 1
        else:
            draws[a] += 1
            draws[b] += 1

    print(f"\n  {'Agent':<25} {'Games':>6} {'W':>5} {'L':>5} {'D':>5} "
          f"{'Win%':>7} {'AvgU':>7}")
    print("  " + "-" * 68)
    ranked = sorted(wins.keys(),
                    key=lambda n: wins[n] / max(games[n], 1), reverse=True)
    for nm in ranked:
        g = games[nm]
        w, l, d = wins[nm], losses[nm], draws[nm]
        avg = _avg_of(h2h_util.get(nm, []))
        wr = w / g * 100 if g else 0
        mark = " <--" if nm == "HybridAgent" else ""
        print(f"  {nm:<25} {g:>6} {w:>5} {l:>5} {d:>5} "
              f"{wr:>6.1f}% {avg:>7.4f}{mark}")
    print("=" * 100)


def print_critical_discussion(agent_stats: list[dict[str, Any]]):
    """Print critical analysis of HybridAgent vs field."""
    hybrid = next((s for s in agent_stats if s["name"] == "HybridAgent"), None)
    if not hybrid:
        return

    rank = next(i + 1 for i, s in enumerate(agent_stats) if s["name"] == "HybridAgent")
    total = len(agent_stats)
    top = agent_stats[0]

    # Compute medians for each signal
    medians: dict[str, float] = {}
    for key in ["avg_u", "avg_popt", "avg_nopt", "avg_kopt",
                "agree_rate", "speed", "opp_sat", "hard_u"]:
        vals = sorted(s[key] for s in agent_stats)
        medians[key] = vals[len(vals) // 2]

    print("\n" + "=" * 120)
    print("CRITICAL DISCUSSION — HybridAgent Performance Analysis")
    print("=" * 120)

    print(f"\n  Overall Ranking: #{rank} / {total} (composite = {hybrid['composite']:.4f})")
    if top["name"] != "HybridAgent":
        print(f"  Top Agent: {top['name']} (composite = {top['composite']:.4f}, "
              f"gap = {top['composite'] - hybrid['composite']:+.4f})")

    # Strengths
    print("\n  STRENGTHS:")
    strengths = []
    if hybrid["avg_u"] >= medians["avg_u"]:
        strengths.append(f"Above-median self-interest "
                         f"(AvgUtil={hybrid['avg_u']:.4f} vs median={medians['avg_u']:.4f})")
    if hybrid["avg_popt"] >= medians["avg_popt"]:
        strengths.append(f"Strong Pareto efficiency "
                         f"(POpt={hybrid['avg_popt']:.4f} vs median={medians['avg_popt']:.4f})")
    if hybrid["agree_rate"] >= medians["agree_rate"]:
        strengths.append(f"Good agreement rate "
                         f"({hybrid['agree_rate']*100:.1f}% vs median={medians['agree_rate']*100:.1f}%)")
    if hybrid["speed"] >= medians["speed"]:
        strengths.append(f"Fast negotiator "
                         f"(speed={hybrid['speed']:.4f} vs median={medians['speed']:.4f})")
    if hybrid["hard_u"] >= medians["hard_u"]:
        strengths.append(f"Handles hard scenarios well "
                         f"(HardU={hybrid['hard_u']:.4f} vs median={medians['hard_u']:.4f})")
    if hybrid["opp_sat"] >= medians["opp_sat"]:
        strengths.append(f"Cooperative — good opponent satisfaction "
                         f"(OppSat={hybrid['opp_sat']:.4f})")
    for s in strengths:
        print(f"    + {s}")
    if not strengths:
        print("    (none identified — below median on all signals)")

    # Weaknesses
    print("\n  WEAKNESSES:")
    weaknesses = []
    if hybrid["avg_u"] < medians["avg_u"]:
        weaknesses.append(f"Below-median utility "
                          f"(AvgUtil={hybrid['avg_u']:.4f} vs median={medians['avg_u']:.4f})")
    if hybrid["agree_rate"] < medians["agree_rate"]:
        weaknesses.append(f"Low agreement rate "
                          f"({hybrid['agree_rate']*100:.1f}% vs median={medians['agree_rate']*100:.1f}%)")
    if hybrid["speed"] < medians["speed"]:
        weaknesses.append(f"Slow to agree "
                          f"(speed={hybrid['speed']:.4f} vs median={medians['speed']:.4f})")
    if hybrid["hard_u"] < medians["hard_u"]:
        weaknesses.append(f"Struggles on hard scenarios "
                          f"(HardU={hybrid['hard_u']:.4f} vs median={medians['hard_u']:.4f})")
    if hybrid["opp_sat"] < medians["opp_sat"]:
        weaknesses.append(f"Low opponent satisfaction "
                          f"(OppSat={hybrid['opp_sat']:.4f} vs median={medians['opp_sat']:.4f})")
    for w in weaknesses:
        print(f"    - {w}")

    # Improvement suggestions
    print("\n  IMPROVEMENT SUGGESTIONS:")
    suggestions = []
    if hybrid["agree_rate"] < 0.8:
        suggestions.append(
            "Increase concession willingness — too many negotiations end without a deal.\n"
            "       Consider lowering the acceptance threshold or using time-based concession.")
    if hybrid["hard_u"] < hybrid["avg_u"] * 0.7:
        suggestions.append(
            "Hard-scenario robustness — utility drops significantly under high opposition.\n"
            "       Consider opponent modelling to identify what the opponent cares about most.")
    if hybrid["speed"] < 0.3:
        suggestions.append(
            "Speed — agent takes too long to reach agreement.\n"
            "       Consider more aggressive early bids or faster convergence strategies.")
    if hybrid["opp_sat"] < 0.4:
        suggestions.append(
            "Cooperativeness — opponent gets very low utility, risking counter-exploitation.\n"
            "       Consider offering better deals to incentivise the opponent to accept sooner.")
    if hybrid["avg_popt"] < 0.85:
        suggestions.append(
            "Deal quality — agreed outcomes are often far from the Pareto frontier.\n"
            "       Consider enumerating outcomes near the frontier and proposing them directly.")
    if not suggestions:
        suggestions.append("Agent performs well across all signals — focus on edge cases.")
    for i, sug in enumerate(suggestions, 1):
        print(f"    {i}. {sug}")

    print("=" * 120)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN EVALUATION
# ═══════════════════════════════════════════════════════════════════════════

def evaluate():
    rng = random.Random(SEED)

    # ── 1. Collect agents ──────────────────────────────────────────────────
    gw_agents: dict[str, Any] = {}
    for name, cls in ALL_AGENTS.items():
        if name in SKIP_AGENTS:
            print(f"  [SKIP] {name} (known broken)")
            continue
        gw_agents[name] = cls
        if MAX_AGENTS and len(gw_agents) >= MAX_AGENTS:
            break

    gw_agents["HybridAgent"] = HybridAgent
    print(f"\nEvaluating {len(gw_agents)} agents (including HybridAgent)")
    print(f"Skipped {len(SKIP_AGENTS)} known-broken agents\n")

    # ── 2. Build diverse scenarios ─────────────────────────────────────────
    scenarios = build_scenarios(rng)
    print(f"Generated {len(scenarios)} diverse scenarios:")
    for sc in scenarios:
        n_out = 1
        for iss in sc.issues:
            n_out *= iss.cardinality
        print(f"  {sc.name:<20}  issues={len(sc.issues)}  outcomes={n_out:>6}  "
              f"opposition={sc.opposition:.3f}  conflict={sc.conflict:.3f}  "
              f"pareto_pts={sc.n_pareto}")
    print()

    # ── 3. Baseline opponents ──────────────────────────────────────────────
    baselines = {
        "Aspiration": AspirationNegotiator,
        "TBConceder": TimeBasedConcedingNegotiator,
        "MiCRO": MiCRONegotiator,
        "TitForTat": NaiveTitForTatNegotiator,
    }

    results: list[NegotiationResult] = []

    # ── 4. Run each agent on every (scenario × baseline) ──────────────────
    print_header()
    total_matchups = len(gw_agents) * len(scenarios) * len(baselines)
    done = 0
    for gw_name, gw_cls in gw_agents.items():
        for sc in scenarios:
            for bl_name, bl_cls in baselines.items():
                res = run_single_negotiation(
                    agent_a_cls=gw_cls,
                    agent_b_cls=bl_cls,
                    scenario=sc,
                    n_steps=N_STEPS,
                    agent_a_name=gw_name,
                    agent_b_name=bl_name,
                )
                results.append(res)
                done += 1
                print_result(res)
        pct = done / total_matchups * 100
        print(f"  ... [{gw_name} done — {pct:.0f}% complete]")

    # ── 5. GW vs GW round-robin (sample) ──────────────────────────────────
    gw_names = list(gw_agents.keys())
    if len(gw_names) >= 2:
        print("\n--- GeniusWeb vs GeniusWeb (sample matchups) ---")
        print_header()
        pairs_seen: set[tuple[str, str]] = set()
        max_pairs = min(15, len(gw_names) * (len(gw_names) - 1) // 2)
        attempts = 0
        while len(pairs_seen) < max_pairs and attempts < max_pairs * 5:
            attempts += 1
            a_name = rng.choice(gw_names)
            b_name = rng.choice(gw_names)
            if a_name == b_name:
                continue
            key = tuple(sorted([a_name, b_name]))
            if key in pairs_seen:
                continue
            pairs_seen.add(key)

            sc = rng.choice(scenarios)
            res = run_single_negotiation(
                agent_a_cls=gw_agents[a_name],
                agent_b_cls=gw_agents[b_name],
                scenario=sc,
                n_steps=N_STEPS,
                agent_a_name=a_name,
                agent_b_name=b_name,
            )
            results.append(res)
            print_result(res)

    # ── 6. Summary ────────────────────────────────────────────────────────
    print_summary(results)

    # ── 7. Write per-negotiation CSV ──────────────────────────────────────
    csv_path = OUTPUT_DIR / "results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "domain", "task_type", "difficulty", "n_outcomes",
            "agent_a", "agent_b", "agreement",
            "util_a", "util_b", "welfare", "nash_product",
            "pareto_dist", "pareto_opt", "nash_opt", "kalai_opt", "welfare_opt",
            "opposition", "steps", "max_steps", "wall_sec", "status", "error",
        ])
        for r in results:
            status = "ERROR" if r.error else (
                "BROKEN" if r.broken else (
                    "TIMEOUT" if r.timedout else (
                        "AGREED" if r.agreement is not None else "NO_DEAL"
                    )
                )
            )
            writer.writerow([
                r.domain, r.task_type, r.difficulty, r.n_outcomes,
                r.agent_a_name, r.agent_b_name,
                r.agreement is not None,
                f"{r.util_a:.4f}" if r.util_a is not None else "",
                f"{r.util_b:.4f}" if r.util_b is not None else "",
                f"{r.welfare:.4f}" if r.welfare is not None else "",
                f"{r.nash_product:.4f}" if r.nash_product is not None else "",
                f"{r.pareto_dist:.4f}" if r.pareto_dist is not None else "",
                f"{r.pareto_optimality:.4f}" if r.pareto_optimality is not None else "",
                f"{r.nash_optimality:.4f}" if r.nash_optimality is not None else "",
                f"{r.kalai_optimality:.4f}" if r.kalai_optimality is not None else "",
                f"{r.max_welfare_opt:.4f}" if r.max_welfare_opt is not None else "",
                f"{r.opposition:.4f}",
                r.n_steps_taken, r.n_steps_allowed, f"{r.wall_seconds:.3f}",
                status, r.error,
            ])
    print(f"\n[LOG] Per-negotiation results written to {csv_path}")

    # ── 8. Per-agent ranking ──────────────────────────────────────────────
    agent_results: dict[str, list[NegotiationResult]] = {}
    for r in results:
        agent_results.setdefault(r.agent_a_name, []).append(r)

    agent_stats: list[dict[str, Any]] = []
    for name, rs in agent_results.items():
        n = len(rs)
        n_agreed = sum(1 for r in rs if r.agreement is not None and not r.error)
        n_errors = sum(1 for r in rs if r.error)
        agree_rate = n_agreed / n if n > 0 else 0.0

        # Utility over ALL runs (disagreement → 0)
        all_u = [r.util_a if r.util_a is not None else 0.0 for r in rs]
        avg_u = sum(all_u) / len(all_u) if all_u else 0.0

        # Utility ONLY under agreement
        agreed_u = [r.util_a for r in rs if r.util_a is not None]
        util_under_agree = sum(agreed_u) / len(agreed_u) if agreed_u else 0.0

        # Welfare & Nash over ALL runs (disagreement → 0)
        all_w = [r.welfare if r.welfare is not None else 0.0 for r in rs]
        avg_w = sum(all_w) / len(all_w) if all_w else 0.0

        all_nash = [r.nash_product if r.nash_product is not None else 0.0 for r in rs]
        avg_nash = sum(all_nash) / len(all_nash) if all_nash else 0.0

        # NegMAS optimality metrics (only from agreed runs)
        p_opts = [r.pareto_optimality for r in rs if r.pareto_optimality is not None]
        avg_popt = sum(p_opts) / len(p_opts) if p_opts else 0.0

        n_opts = [r.nash_optimality for r in rs if r.nash_optimality is not None]
        avg_nopt = sum(n_opts) / len(n_opts) if n_opts else 0.0

        k_opts = [r.kalai_optimality for r in rs if r.kalai_optimality is not None]
        avg_kopt = sum(k_opts) / len(k_opts) if k_opts else 0.0

        mw_opts = [r.max_welfare_opt for r in rs if r.max_welfare_opt is not None]
        avg_mwopt = sum(mw_opts) / len(mw_opts) if mw_opts else 0.0

        p_dists = [r.pareto_dist for r in rs if r.pareto_dist is not None]
        avg_pdist = sum(p_dists) / len(p_dists) if p_dists else float('nan')

        # ── Additional signals ─────────────────────────────────────────
        # Speed: how quickly does the agent reach agreement? (1=instant)
        speed_vals = [1.0 - r.n_steps_taken / r.n_steps_allowed
                      for r in rs if r.agreement is not None and not r.error]
        speed = sum(speed_vals) / len(speed_vals) if speed_vals else 0.0

        # Opponent satisfaction: cooperative quality
        opp_utils = [r.util_b for r in rs if r.util_b is not None]
        opp_sat = sum(opp_utils) / len(opp_utils) if opp_utils else 0.0

        # Robustness: no crashes/errors
        error_rate = n_errors / n if n > 0 else 0.0
        robustness = 1.0 - error_rate

        # Difficulty-weighted utility: performance on hard scenarios
        hard_utils = [r.util_a if r.util_a is not None else 0.0
                      for r in rs if r.difficulty == "hard"]
        hard_u = sum(hard_utils) / len(hard_utils) if hard_utils else avg_u

        # ── Composite score (multi-signal) ────────────────────────────
        # Optimality metrics are scaled by agreement rate to prevent
        # agents with few lucky agreements from getting inflated scores.
        # Speed and opp_sat are de-weighted to penalise pushovers.
        #   30% avg utility  (core self-interest, penalises no-deals)
        #   10% Pareto opt * agree_rate  (effective Pareto)
        #   10% Nash opt * agree_rate    (effective Nash)
        #   10% agreement rate
        #    5% Kalai opt * agree_rate   (effective Kalai)
        #    3% negotiation speed
        #    2% opponent satisfaction
        #    5% robustness (no errors/crashes)
        #   15% difficulty-weighted utility
        #   10% utility under agreement  (deal quality)
        composite = (
            0.30 * avg_u
            + 0.10 * avg_popt * agree_rate
            + 0.10 * avg_nopt * agree_rate
            + 0.10 * agree_rate
            + 0.05 * avg_kopt * agree_rate
            + 0.03 * speed
            + 0.02 * opp_sat
            + 0.05 * robustness
            + 0.15 * hard_u
            + 0.10 * util_under_agree
        )

        agent_stats.append({
            "name": name,
            "runs": n,
            "agreed": n_agreed,
            "errors": n_errors,
            "agree_rate": agree_rate,
            "avg_u": avg_u,
            "util_under_agree": util_under_agree,
            "avg_welfare": avg_w,
            "avg_nash": avg_nash,
            "avg_pdist": avg_pdist,
            "avg_popt": avg_popt,
            "avg_nopt": avg_nopt,
            "avg_kopt": avg_kopt,
            "avg_mwopt": avg_mwopt,
            "speed": speed,
            "opp_sat": opp_sat,
            "robustness": robustness,
            "hard_u": hard_u,
            "composite": composite,
        })

    agent_stats.sort(key=lambda x: x["composite"], reverse=True)

    print("\n" + "=" * 170)
    print("AGENT RANKING (sorted by composite score)")
    print("  Composite = 0.30*AvgUtil + 0.10*POpt*Agree + 0.10*NOpt*Agree + 0.10*AgreeRate + 0.05*KOpt*Agree")
    print("             + 0.03*Speed + 0.02*OppSat + 0.05*Robust + 0.15*HardU + 0.10*U|Agree")
    print("  NOTE: AvgUtil averaged over ALL runs (disagreement -> 0); optimality metrics from NegMAS")
    print("=" * 170)
    print(f"{'Rank':<6} {'Agent':<25} {'#Runs':>6} {'Agreed':>7} {'Rate%':>6} "
          f"{'AvgUtil':>8} {'U|Agree':>8} {'Welfare':>8} "
          f"{'POpt':>7} {'NOpt':>7} {'KOpt':>7} "
          f"{'Speed':>6} {'OppSat':>7} {'HardU':>7} "
          f"{'Score':>8}")
    print("-" * 170)
    for rank, s in enumerate(agent_stats, 1):
        marker = " <--" if s["name"] == "HybridAgent" else ""
        print(f"{rank:<6} {s['name']:<25} {s['runs']:>6} {s['agreed']:>7} "
              f"{s['agree_rate'] * 100:>5.1f}% {s['avg_u']:>8.4f} {s['util_under_agree']:>8.4f} "
              f"{s['avg_welfare']:>8.4f} "
              f"{s['avg_popt']:>7.4f} {s['avg_nopt']:>7.4f} {s['avg_kopt']:>7.4f} "
              f"{s['speed']:>6.3f} {s['opp_sat']:>7.4f} {s['hard_u']:>7.4f} "
              f"{s['composite']:>8.4f}{marker}")

    print("=" * 170)
    for rank, s in enumerate(agent_stats, 1):
        if s["name"] == "HybridAgent":
            print(f"\n>>> HybridAgent ranked #{rank} out of {len(agent_stats)} agents <<<")
            break

    # ── 8b. Calibration, pairwise, and critical analysis ──────────────
    print_calibration_analysis(results, agent_stats)
    print_pairwise_analysis(results)
    print_critical_discussion(agent_stats)

    # ── 9. Write ranking CSV ──────────────────────────────────────────────
    ranking_csv = OUTPUT_DIR / "ranking.csv"
    with open(ranking_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank", "agent", "runs", "agreed", "agree_rate",
            "avg_util", "util_under_agree", "avg_welfare", "avg_nash",
            "avg_pareto_dist", "avg_pareto_opt", "avg_nash_opt",
            "avg_kalai_opt", "avg_max_welfare_opt",
            "speed", "opp_satisfaction", "robustness", "hard_util",
            "composite",
        ])
        for rank, s in enumerate(agent_stats, 1):
            pdist_str = f"{s['avg_pdist']:.4f}" if not math.isnan(s['avg_pdist']) else ""
            writer.writerow([
                rank, s["name"], s["runs"], s["agreed"],
                f"{s['agree_rate']:.4f}", f"{s['avg_u']:.4f}",
                f"{s['util_under_agree']:.4f}",
                f"{s['avg_welfare']:.4f}", f"{s['avg_nash']:.4f}",
                pdist_str, f"{s['avg_popt']:.4f}",
                f"{s['avg_nopt']:.4f}", f"{s['avg_kopt']:.4f}",
                f"{s['avg_mwopt']:.4f}",
                f"{s['speed']:.4f}", f"{s['opp_sat']:.4f}",
                f"{s['robustness']:.4f}", f"{s['hard_u']:.4f}",
                f"{s['composite']:.4f}",
            ])
    print(f"[LOG] Agent ranking written to {ranking_csv}")

    # Also copy to output root for easy access
    import shutil
    for fname in ("results.csv", "ranking.csv"):
        shutil.copy2(OUTPUT_DIR / fname, _OUTPUT_ROOT / fname)
    print(f"[LOG] Copies also at {_OUTPUT_ROOT / 'ranking.csv'}")
    print(f"[LOG] Full console log at {OUTPUT_DIR / 'evaluation.log'}")
    print()
    return results


if __name__ == "__main__":
    _log_path = OUTPUT_DIR / "evaluation.log"
    _tee_out = _Tee(sys.stdout, _log_path)
    _tee_err = _Tee(sys.stderr, OUTPUT_DIR / "evaluation_err.log")
    sys.stdout = _tee_out  # type: ignore[assignment]
    sys.stderr = _tee_err  # type: ignore[assignment]
    try:
        evaluate()
    finally:
        sys.stdout = _tee_out._stream
        sys.stderr = _tee_err._stream
        _tee_out.close()
        _tee_err.close()
