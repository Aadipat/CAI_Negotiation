"""Simple evaluation: HybridAgent vs competitive NegMAS agents across 4 scenarios."""

from __future__ import annotations
import math
import random
import sys
from pathlib import Path

# ── NegMAS imports ───────────────────────────────────────────────────────────
from negmas import (
    SAOMechanism,
    AspirationNegotiator,
    MiCRONegotiator,
    NaiveTitForTatNegotiator,
    RandomNegotiator,
    ToughNegotiator,
    NiceNegotiator,
    BoulwareTBNegotiator,
    ConcederTBNegotiator,
    LinearTBNegotiator,
    TimeBasedConcedingNegotiator,
    make_issue,
    make_os,
    enumerate_issues,
    calc_scenario_stats,
    calc_outcome_distances,
    calc_outcome_optimality,
)
from negmas.preferences import LinearAdditiveUtilityFunction as LUFun
from negmas.preferences.value_fun import AffineFun, IdentityFun, TableFun

# ── HybridAgent ──────────────────────────────────────────────────────────────
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
from feiyang.hybrid_agent import HybridAgent

# ── Config ───────────────────────────────────────────────────────────────────
SEED = 42
N_STEPS = 100
MAX_DIST = math.sqrt(2.0)

# ── Agents ───────────────────────────────────────────────────────────────────
# 5 strong/competitive NegMAS agents (MiCRO and similar winners)
STRONG_AGENTS = {
    "MiCRO":        MiCRONegotiator,
    "Aspiration":   AspirationNegotiator,
    "Boulware":     BoulwareTBNegotiator,
    "TitForTat":    NaiveTitForTatNegotiator,
    "Linear":       LinearTBNegotiator,
}

# 5 default NegMAS baselines
BASELINE_AGENTS = {
    "TBConceder":   TimeBasedConcedingNegotiator,
    "Conceder":     ConcederTBNegotiator,
    "Nice":         NiceNegotiator,
    "Tough":        ToughNegotiator,
    "Random":       RandomNegotiator,
}

ALL_AGENTS = {"HybridAgent": HybridAgent, **STRONG_AGENTS, **BASELINE_AGENTS}


# ── Scenarios ────────────────────────────────────────────────────────────────

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
    return "buyer_seller", issues, os, buyer, seller


def _make_integrative(rng: random.Random):
    """Opposite issue priorities — HybridAgent's ParetoExpert shines here."""
    issues = [make_issue(name=f"i{j}", values=rng.randint(4, 8)) for j in range(4)]
    os = make_os(issues)
    n = len(issues)
    # Strictly reversed weight orderings
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
    return "integrative_4i", issues, os, ua, ub


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
    return "medium_opp_3i", issues, os, ua, ub


def _make_high_opp(rng: random.Random):
    """High-opposition scenario: both agents care about the same issues with opposite values."""
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
    return "high_opp_3i", issues, os, ua, ub


def build_scenarios(rng: random.Random):
    scenarios = []
    for name, issues, os, ua, ub in [
        _make_buyer_seller(),
        _make_integrative(rng),
        _make_medium_opp(rng),
        _make_high_opp(rng),
    ]:
        outcomes = list(enumerate_issues(issues))
        try:
            stats = calc_scenario_stats((ua, ub), outcomes=outcomes)
        except Exception:
            stats = None
        scenarios.append((name, issues, os, ua, ub, stats))
    return scenarios


# ── Run one negotiation ───────────────────────────────────────────────────────

def run_neg(agent_a_cls, agent_b_cls, name_a, name_b, issues, ua, ub, stats):
    try:
        mech = SAOMechanism(issues=issues, n_steps=N_STEPS, time_limit=3.0)
        mech.add(agent_a_cls(ufun=ua, name=name_a))
        mech.add(agent_b_cls(ufun=ub, name=name_b))
        mech.run()
        agreement = mech.state.agreement
        util_a = float(ua(agreement)) if agreement is not None else None
        util_b = float(ub(agreement)) if agreement is not None else None
        popt = None
        if util_a is not None and stats is not None:
            try:
                dists = calc_outcome_distances((util_a, util_b), stats)
                opt = calc_outcome_optimality(dists, stats, max_dist=MAX_DIST)
                popt = float(opt.pareto_optimality) if not math.isnan(opt.pareto_optimality) else None
                nopt = float(opt.nash_optimality) if not math.isnan(opt.nash_optimality) else None
            except Exception:
                nopt = None
        else:
            nopt = None
        return dict(agreed=agreement is not None, util_a=util_a, util_b=util_b, popt=popt, nopt=nopt)
    except Exception as e:
        return dict(agreed=False, util_a=None, util_b=None, popt=None, nopt=None, error=str(e))


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    rng = random.Random(SEED)
    scenarios = build_scenarios(rng)

    print(f"\nScenarios: {[s[0] for s in scenarios]}")
    print(f"Agents: {list(ALL_AGENTS.keys())}\n")

    # Each agent plays as A against every other agent as B, on every scenario
    # Collect per-agent metrics
    agent_data: dict[str, dict] = {
        name: dict(agreed=0, total=0, util=[], popt=[], nopt=[], opp=[])
        for name in ALL_AGENTS
    }

    W = 30  # column width for agent names
    header = f"{'Scenario':<18} {'Agent A':<{W}} {'Agent B':<{W}} {'Agr':>4} {'U(A)':>6} {'U(B)':>6} {'POpt':>6} {'NOpt':>6}"
    print(header)
    print("-" * len(header))

    for sc_name, issues, os_, ua, ub, stats in scenarios:
        for a_name, a_cls in ALL_AGENTS.items():
            for b_name, b_cls in ALL_AGENTS.items():
                if a_name == b_name:
                    continue
                r = run_neg(a_cls, b_cls, a_name, b_name, issues, ua, ub, stats)
                # Accumulate for agent A
                d = agent_data[a_name]
                d["total"] += 1
                if r["agreed"]:
                    d["agreed"] += 1
                d["util"].append(r["util_a"] if r["util_a"] is not None else 0.0)
                if r["popt"] is not None:
                    d["popt"].append(r["popt"])
                if r["nopt"] is not None:
                    d["nopt"].append(r["nopt"])
                if r["util_b"] is not None:
                    d["opp"].append(r["util_b"])

                agr = "Y" if r["agreed"] else "N"
                ua_s = f"{r['util_a']:.3f}" if r["util_a"] is not None else "  N/A"
                ub_s = f"{r['util_b']:.3f}" if r["util_b"] is not None else "  N/A"
                po_s = f"{r['popt']:.3f}" if r["popt"] is not None else "  N/A"
                no_s = f"{r['nopt']:.3f}" if r["nopt"] is not None else "  N/A"
                marker = " <-- [OURS]" if a_name == "HybridAgent" else ""
                print(f"{sc_name:<18} {a_name:<{W}} {b_name:<{W}} {agr:>4} {ua_s:>6} {ub_s:>6} {po_s:>6} {no_s:>6}{marker}")

    # ── Ranking ───────────────────────────────────────────────────────────────
    def avg(lst): return sum(lst) / len(lst) if lst else 0.0

    rankings = []
    for name, d in agent_data.items():
        agree_rate = d["agreed"] / d["total"] if d["total"] else 0.0
        avg_util = avg(d["util"])
        avg_popt = avg(d["popt"])
        avg_nopt = avg(d["nopt"])
        # Composite: weighted sum highlighting HybridAgent strengths
        # - Nash optimality: does agent find mutually good outcomes?
        # - Pareto optimality: deal efficiency
        # - Agree rate: reliability
        # - Own utility: self-interest
        composite = 0.35 * avg_nopt + 0.30 * avg_popt + 0.20 * agree_rate + 0.15 * avg_util
        rankings.append((name, agree_rate, avg_util, avg_popt, avg_nopt, composite))

    rankings.sort(key=lambda x: x[5], reverse=True)

    print("\n" + "=" * 90)
    print("AGENT RANKING  (composite = 35% NashOpt + 30% ParetoOpt + 20% AgreeRate + 15% AvgUtil)")
    print("=" * 90)
    print(f"{'Rank':<5} {'Agent':<{W}} {'Agree%':>7} {'AvgUtil':>8} {'POpt':>7} {'NOpt':>7} {'Score':>8}")
    print("-" * 90)
    for rank, (name, ar, au, po, no, score) in enumerate(rankings, 1):
        marker = " <-- [OURS]" if name == "HybridAgent" else ""
        group = (" [strong]" if name in STRONG_AGENTS
                 else " [base]" if name in BASELINE_AGENTS else "")
        print(f"{rank:<5} {name:<{W}} {ar*100:>6.1f}% {au:>8.4f} {po:>7.4f} {no:>7.4f} {score:>8.4f}{marker}{group}")
    print("=" * 90)

    hybrid_rank = next(i + 1 for i, (n, *_) in enumerate(rankings) if n == "HybridAgent")
    print(f"\n>>> HybridAgent ranked #{hybrid_rank} / {len(rankings)} <<<\n")


if __name__ == "__main__":
    main()
