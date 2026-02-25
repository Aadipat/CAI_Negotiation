"""
Evaluation script for GeniusWeb agents wrapped via negmas_geniusweb_bridge.

This script runs bilateral negotiations between wrapped GeniusWeb agents and
NegMAS built-in agents across multiple negotiation domains, collecting and
reporting performance metrics (utility, agreement rate, Pareto distance, etc.).

Based on the NegMAS SAOMechanism tutorial patterns.
"""

from __future__ import annotations

import csv
import io
import math
import os
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

    # forward attribute lookups so logging/etc. still work
    def __getattr__(self, name):
        return getattr(self._stream, name)

# ── NegMAS imports ──────────────────────────────────────────────────────────
from negmas import SAOMechanism, make_issue
from negmas.preferences import LinearAdditiveUtilityFunction as LUFun
from negmas.preferences.value_fun import LinearFun, IdentityFun, AffineFun
from negmas.sao import AspirationNegotiator

# For TimeBasedConcedingNegotiator (used as a built-in baseline)
from negmas import TimeBasedConcedingNegotiator

# ── Bridge imports ──────────────────────────────────────────────────────────
# Ensure the ExampleAgents source tree is importable
_bridge_src = Path(__file__).resolve().parent / "ExampleAgents" / "src"
if str(_bridge_src) not in sys.path:
    sys.path.insert(0, str(_bridge_src))

# Vendor dependencies (geniusweb, tudelft_utilities, etc.)
_vendor = Path(__file__).resolve().parent / "ExampleAgents" / "vendor"
for _sub in ("geniusweb-1.2.1", "others/tudelft_utilities", "others/tudelft_utilities_logging", "others/uri", "others/pyson"):
    _p = _vendor / _sub
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from negmas_geniusweb_bridge import ALL_AGENTS, BROKEN_AGENTS
from negmas_geniusweb_bridge.wrapper import make_geniusweb_negotiator
# ── Import HybridAgent and wrap it for NegMAS ──────────────────────────────
_feiyang_dir = Path(__file__).resolve().parent
if str(_feiyang_dir) not in sys.path:
    sys.path.insert(0, str(_feiyang_dir))
from feiyang.hybrid_agent import HybridAgent
WrappedHybridAgent = make_geniusweb_negotiator(HybridAgent)

# ── Configuration ───────────────────────────────────────────────────────────

SEED = 42
N_STEPS = 100  # negotiation rounds per session
N_DOMAINS = 3  # number of random domains to test on
MAX_AGENTS = None  # set to an int to limit how many agents are evaluated

# Agents to skip (known to be broken / extremely slow)
SKIP_AGENTS: set[str] = BROKEN_AGENTS.copy()


# ── Domain helpers ──────────────────────────────────────────────────────────

def make_domain_simple():
    """Simple single-issue domain (10 outcomes)."""
    issues = [make_issue(name="price", values=10)]
    return issues, "simple_1issue"


def make_domain_bilateral():
    """Three-issue buyer/seller domain from the NegMAS tutorial."""
    issues = [
        make_issue(name="price", values=10),
        make_issue(name="quantity", values=(1, 11)),
        make_issue(name="delivery_time", values=10),
    ]
    return issues, "buyer_seller"


def make_domain_random(rng: random.Random, n_issues: int = 3, max_values: int = 7):
    """Generate a random domain with *n_issues* issues."""
    issues = [make_issue(name=f"issue_{i}", values=rng.randint(3, max_values))
              for i in range(n_issues)]
    return issues, f"random_{n_issues}issues"


def random_ufun(issues, rng: random.Random) -> LUFun:
    """Create a random normalised LinearAdditiveUtilityFunction."""
    old_state = random.getstate()
    random.setstate(rng.getstate())
    ufun = LUFun.random(issues=issues, normalized=True)
    rng.setstate(random.getstate())
    random.setstate(old_state)
    return ufun


# ── Predefined domains (tutorial-style) ────────────────────────────────────

def make_tutorial_ufuns(session: SAOMechanism):
    """
    Return (buyer_ufun, seller_ufun) matching the NegMAS tutorial bilateral
    negotiation example.
    """
    seller_utility = LUFun(
        values=[IdentityFun(), LinearFun(0.2), AffineFun(-1, bias=9.0)],
        outcome_space=session.outcome_space,
    )
    buyer_utility = LUFun(
        values={
            "price": AffineFun(-1, bias=9.0),
            "quantity": LinearFun(0.2),
            "delivery_time": IdentityFun(),
        },
        outcome_space=session.outcome_space,
    )
    return buyer_utility.scale_max(1.0), seller_utility.scale_max(1.0)


# ── Pareto frontier helpers ─────────────────────────────────────────────────

def compute_pareto_frontier(ufun_a, ufun_b, issues):
    """Return the Pareto frontier as a list of (util_a, util_b) tuples."""
    from negmas import enumerate_issues
    points = []
    for outcome in enumerate_issues(issues):
        ua = float(ufun_a(outcome))
        ub = float(ufun_b(outcome))
        points.append((ua, ub))

    # Filter to Pareto-optimal points (no other point dominates in both dims)
    frontier = []
    for p in points:
        dominated = False
        for q in points:
            if q[0] >= p[0] and q[1] >= p[1] and (q[0] > p[0] or q[1] > p[1]):
                dominated = True
                break
        if not dominated:
            frontier.append(p)
    return frontier


def pareto_distance(ua: float, ub: float, frontier: list[tuple[float, float]]) -> float:
    """Euclidean distance from (ua, ub) to the nearest Pareto-optimal point."""
    if not frontier:
        return float('nan')
    return min(math.hypot(ua - pa, ub - pb) for pa, pb in frontier)


# ── Result container ───────────────────────────────────────────────────────

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
    welfare: float | None = None   # sum of utilities
    nash: float | None = None      # product of utilities
    pareto_dist: float | None = None  # distance to Pareto frontier
    wall_seconds: float = 0.0
    error: str = ""


# ── Core evaluation runner ─────────────────────────────────────────────────

def run_single_negotiation(
    agent_a_cls,
    agent_b_cls,
    ufun_a,
    ufun_b,
    issues,
    domain_name: str,
    n_steps: int = N_STEPS,
    agent_a_name: str = "",
    agent_b_name: str = "",
    pareto_frontier: list[tuple[float, float]] | None = None,
) -> NegotiationResult:
    """Run one bilateral negotiation and return a NegotiationResult."""
    mechanism = SAOMechanism(issues=issues, n_steps=n_steps)

    a_name = agent_a_name or agent_a_cls.__name__
    b_name = agent_b_name or agent_b_cls.__name__

    try:
        agent_a = agent_a_cls(ufun=ufun_a, name=a_name)
        agent_b = agent_b_cls(ufun=ufun_b, name=b_name)
        mechanism.add(agent_a)
        mechanism.add(agent_b)

        t0 = time.perf_counter()
        mechanism.run()
        elapsed = time.perf_counter() - t0

        state = mechanism.state
        agreement = state.agreement

        util_a = float(ufun_a(agreement)) if agreement is not None else None
        util_b = float(ufun_b(agreement)) if agreement is not None else None
        welfare = (util_a + util_b) if (util_a is not None and util_b is not None) else None
        nash = (util_a * util_b) if (util_a is not None and util_b is not None) else None

        # Pareto distance (only if agreement reached and frontier available)
        pdist = None
        if util_a is not None and util_b is not None and pareto_frontier:
            pdist = pareto_distance(util_a, util_b, pareto_frontier)

        return NegotiationResult(
            domain=domain_name,
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
            nash=nash,
            pareto_dist=pdist,
            wall_seconds=elapsed,
        )
    except Exception as exc:
        return NegotiationResult(
            domain=domain_name,
            agent_a_name=a_name,
            agent_b_name=b_name,
            agreement=None,
            n_steps_taken=0,
            n_steps_allowed=n_steps,
            timedout=False,
            broken=True,
            error=str(exc),
        )


# ── Reporting ──────────────────────────────────────────────────────────────

def print_header():
    print("=" * 130)
    print(f"{'Domain':<18} {'Agent A':<22} {'Agent B':<22} "
          f"{'Agreement':<16} {'U(A)':>6} {'U(B)':>6} {'Welfare':>8} {'PDist':>6} "
          f"{'Steps':>6} {'Time(s)':>8} {'Status':<10}")
    print("-" * 130)


def print_result(r: NegotiationResult):
    if r.error:
        status = f"ERROR"
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
    agr = str(r.agreement) if r.agreement is not None else "None"
    if len(agr) > 14:
        agr = agr[:11] + "..."

    print(f"{r.domain:<18} {r.agent_a_name:<22} {r.agent_b_name:<22} "
          f"{agr:<16} {ua:>6} {ub:>6} {w:>8} {pd:>6} "
          f"{r.n_steps_taken:>6} {r.wall_seconds:>8.3f} {status:<10}")
    if r.error:
        print(f"  └─ Error: {r.error[:90]}")


def print_summary(results: list[NegotiationResult]):
    total = len(results)
    agreed = sum(1 for r in results if r.agreement is not None and not r.error)
    errors = sum(1 for r in results if r.error)
    timeouts = sum(1 for r in results if r.timedout)
    broken = sum(1 for r in results if r.broken and not r.error)

    # Average welfare for agreed negotiations
    welfares = [r.welfare for r in results if r.welfare is not None]
    avg_welfare = sum(welfares) / len(welfares) if welfares else 0.0

    utils_a = [r.util_a for r in results if r.util_a is not None]
    utils_b = [r.util_b for r in results if r.util_b is not None]
    avg_ua = sum(utils_a) / len(utils_a) if utils_a else 0.0
    avg_ub = sum(utils_b) / len(utils_b) if utils_b else 0.0

    print("\n" + "=" * 120)
    print("SUMMARY")
    print("=" * 120)
    print(f"  Total negotiations : {total}")
    print(f"  Agreements         : {agreed}  ({agreed/total*100:.1f}%)" if total else "  Agreements: 0")
    print(f"  Timeouts           : {timeouts}")
    print(f"  Broken             : {broken}")
    print(f"  Errors             : {errors}")
    print(f"  Avg welfare (agreed): {avg_welfare:.4f}")
    print(f"  Avg U(A) (agreed)  : {avg_ua:.4f}")
    print(f"  Avg U(B) (agreed)  : {avg_ub:.4f}")
    print("=" * 120)


# ── Main evaluation ───────────────────────────────────────────────────────

def evaluate():
    rng = random.Random(SEED)

    # ── 1. Collect agents to test ──────────────────────────────────────────
    gw_agents: dict[str, Any] = {}
    for name, cls in ALL_AGENTS.items():
        if name in SKIP_AGENTS:
            print(f"  [SKIP] {name} (known broken)")
            continue
        gw_agents[name] = cls
        if MAX_AGENTS and len(gw_agents) >= MAX_AGENTS:
            break

    # ── Add HybridAgent (our Strategy B agent) ──────────────────────────
    gw_agents["HybridAgent"] = WrappedHybridAgent

    print(f"\nEvaluating {len(gw_agents)} GeniusWeb agents (including HybridAgent)")
    print(f"Skipped {len(SKIP_AGENTS)} known-broken agents: {', '.join(sorted(SKIP_AGENTS))}\n")

    # ── 2. Build domains ───────────────────────────────────────────────────
    domains: list[tuple[list, str]] = []
    # Fixed domains
    domains.append(make_domain_simple())
    domains.append(make_domain_bilateral())
    # Random domains
    for _ in range(N_DOMAINS):
        domains.append(make_domain_random(rng))

    # ── 3. Baselines (NegMAS built-in opponents) ──────────────────────────
    baselines = {
        "Aspiration": AspirationNegotiator,
        "TBConceder": TimeBasedConcedingNegotiator,
    }

    results: list[NegotiationResult] = []

    # ── 4. Pre-generate scenarios (same for every agent) ──────────────────
    # Each scenario = (domain_issues, domain_name, baseline_name, baseline_cls,
    #                  ufun_a, ufun_b, pareto_frontier)
    scenarios: list[tuple] = []
    for domain_issues, domain_name in domains:
        for bl_name, bl_cls in baselines.items():
            ufun_a = random_ufun(domain_issues, rng)
            ufun_b = random_ufun(domain_issues, rng)
            frontier = compute_pareto_frontier(ufun_a, ufun_b, domain_issues)
            scenarios.append((domain_issues, domain_name, bl_name, bl_cls,
                              ufun_a, ufun_b, frontier))

    print(f"Generated {len(scenarios)} shared scenarios "
          f"({len(domains)} domains x {len(baselines)} baselines)\n")

    # ── 5. Run: Each GW agent on every shared scenario ────────────────────
    print_header()

    for gw_name, gw_cls in gw_agents.items():
        for (domain_issues, domain_name, bl_name, bl_cls,
             ufun_a, ufun_b, frontier) in scenarios:
            res = run_single_negotiation(
                agent_a_cls=gw_cls,
                agent_b_cls=bl_cls,
                ufun_a=ufun_a,
                ufun_b=ufun_b,
                issues=domain_issues,
                domain_name=domain_name,
                n_steps=N_STEPS,
                agent_a_name=gw_name,
                agent_b_name=bl_name,
                pareto_frontier=frontier,
            )
            results.append(res)
            print_result(res)

    # ── 6. GW agent vs GW agent (round-robin sample) ─────────────────────
    gw_names = list(gw_agents.keys())
    if len(gw_names) >= 2:
        print("\n--- GeniusWeb vs GeniusWeb (sample matchups) ---")
        print_header()
        # Pick a subset of pairings to keep runtime reasonable
        pairs_seen: set[tuple[str, str]] = set()
        for _ in range(min(20, len(gw_names) * (len(gw_names) - 1) // 2)):
            a_name = rng.choice(gw_names)
            b_name = rng.choice(gw_names)
            if a_name == b_name:
                continue
            key = tuple(sorted([a_name, b_name]))
            if key in pairs_seen:
                continue
            pairs_seen.add(key)

            domain_issues, domain_name = rng.choice(domains)
            ufun_a = random_ufun(domain_issues, rng)
            ufun_b = random_ufun(domain_issues, rng)

            frontier = compute_pareto_frontier(ufun_a, ufun_b, domain_issues)

            res = run_single_negotiation(
                agent_a_cls=gw_agents[a_name],
                agent_b_cls=gw_agents[b_name],
                ufun_a=ufun_a,
                ufun_b=ufun_b,
                issues=domain_issues,
                domain_name=domain_name,
                n_steps=N_STEPS,
                agent_a_name=a_name,
                agent_b_name=b_name,
                pareto_frontier=frontier,
            )
            results.append(res)
            print_result(res)

    # ── 7. Tutorial-style fixed domain test ──────────────────────────────
    print("\n--- Tutorial buyer/seller domain ---")
    print_header()
    tut_issues = [
        make_issue(name="price", values=10),
        make_issue(name="quantity", values=(1, 11)),
        make_issue(name="delivery_time", values=10),
    ]
    tut_session = SAOMechanism(issues=tut_issues, n_steps=N_STEPS)
    buyer_ufun, seller_ufun = make_tutorial_ufuns(tut_session)

    tut_frontier = compute_pareto_frontier(buyer_ufun, seller_ufun, tut_issues)

    for gw_name, gw_cls in gw_agents.items():
        # GW agent as buyer vs TimeBasedConcedingNegotiator as seller
        res = run_single_negotiation(
            agent_a_cls=gw_cls,
            agent_b_cls=TimeBasedConcedingNegotiator,
            ufun_a=buyer_ufun,
            ufun_b=seller_ufun,
            issues=tut_issues,
            domain_name="tutorial_buysell",
            n_steps=N_STEPS,
            agent_a_name=gw_name,
            agent_b_name="TBConceder",
            pareto_frontier=tut_frontier,
        )
        results.append(res)
        print_result(res)

    # ── 8. Summary ────────────────────────────────────────────────────────
    print_summary(results)

    # ── 8b. Write per-negotiation CSV ─────────────────────────────────────
    csv_path = OUTPUT_DIR / "results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "domain", "agent_a", "agent_b", "agreement",
            "util_a", "util_b", "welfare", "nash", "pareto_dist",
            "steps", "max_steps", "wall_sec", "status", "error",
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
                r.domain, r.agent_a_name, r.agent_b_name,
                r.agreement is not None,
                f"{r.util_a:.4f}" if r.util_a is not None else "",
                f"{r.util_b:.4f}" if r.util_b is not None else "",
                f"{r.welfare:.4f}" if r.welfare is not None else "",
                f"{r.nash:.4f}" if r.nash is not None else "",
                f"{r.pareto_dist:.4f}" if r.pareto_dist is not None else "",
                r.n_steps_taken, r.n_steps_allowed, f"{r.wall_seconds:.3f}",
                status, r.error,
            ])
    print(f"\n[LOG] Per-negotiation results written to {csv_path}")

    # ── 9. Per-agent summary with ranking ────────────────────────────────
    agent_results: dict[str, list[NegotiationResult]] = {}
    for r in results:
        agent_results.setdefault(r.agent_a_name, []).append(r)

    # Build stats per agent
    agent_stats: list[dict[str, Any]] = []
    for name, rs in agent_results.items():
        n = len(rs)
        n_agreed = sum(1 for r in rs if r.agreement is not None and not r.error)
        n_errors = sum(1 for r in rs if r.error)
        agree_rate = n_agreed / n if n > 0 else 0.0

        # ── Utility over ALL runs (disagreement / error → 0) ──────────
        all_u = [r.util_a if r.util_a is not None else 0.0 for r in rs]
        avg_u = sum(all_u) / len(all_u) if all_u else 0.0

        # ── Utility ONLY under agreement ──────────────────────────────
        agreed_u = [r.util_a for r in rs if r.util_a is not None]
        util_under_agree = sum(agreed_u) / len(agreed_u) if agreed_u else 0.0

        # ── Welfare & Nash over ALL runs (disagreement → 0) ──────────
        all_w = [r.welfare if r.welfare is not None else 0.0 for r in rs]
        all_n = [r.nash if r.nash is not None else 0.0 for r in rs]
        avg_w = sum(all_w) / len(all_w) if all_w else 0.0
        avg_nash = sum(all_n) / len(all_n) if all_n else 0.0

        # ── Pareto optimality (avg distance; lower = better) ─────────
        pdists = [r.pareto_dist for r in rs if r.pareto_dist is not None]
        avg_pdist = sum(pdists) / len(pdists) if pdists else float('nan')
        # Convert distance to a 0-1 score (1 = on frontier, decays with dist)
        pareto_score = (1.0 / (1.0 + avg_pdist)) if not math.isnan(avg_pdist) else 0.0

        # ── Composite score ───────────────────────────────────────────
        # Weights: 40% util-under-agreement (deal quality is key),
        #          30% avg utility over all runs (penalises no-deals),
        #          15% agreement rate, 10% Pareto optimality, 5% welfare
        composite = (
            0.40 * util_under_agree
            + 0.30 * avg_u
            + 0.15 * agree_rate
            + 0.10 * pareto_score
            + 0.05 * avg_w
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
            "pareto_score": pareto_score,
            "composite": composite,
        })

    # Sort by composite score descending
    agent_stats.sort(key=lambda x: x["composite"], reverse=True)

    print("\n" + "=" * 140)
    print("AGENT RANKING (sorted by composite score)")
    print("  Composite = 0.40*UtilUnderAgree + 0.30*AvgUtil + 0.15*AgreeRate + 0.10*ParetoScore + 0.05*Welfare")
    print("  NOTE: AvgUtil/Welfare averaged over ALL runs (disagreement counts as 0)")
    print("=" * 140)
    print(f"{'Rank':<6} {'Agent':<25} {'#Runs':>6} {'Agreed':>7} {'Rate%':>6} "
          f"{'AvgUtil':>8} {'U|Agree':>8} {'Welfare':>8} {'PDist':>7} "
          f"{'PScore':>7} {'Score':>8}")
    print("-" * 110)
    for rank, s in enumerate(agent_stats, 1):
        marker = " <--" if s["name"] == "HybridAgent" else ""
        pdist_str = f"{s['avg_pdist']:.4f}" if not math.isnan(s['avg_pdist']) else "   N/A"
        print(f"{rank:<6} {s['name']:<25} {s['runs']:>6} {s['agreed']:>7} "
              f"{s['agree_rate']*100:>5.1f}% {s['avg_u']:>8.4f} {s['util_under_agree']:>8.4f} "
              f"{s['avg_welfare']:>8.4f} {pdist_str:>7} "
              f"{s['pareto_score']:>7.4f} {s['composite']:>8.4f}{marker}")

    print("=" * 140)
    # Highlight HybridAgent rank
    for rank, s in enumerate(agent_stats, 1):
        if s["name"] == "HybridAgent":
            print(f"\n>>> HybridAgent ranked #{rank} out of {len(agent_stats)} agents <<<")
            break

    # ── 10. Write ranking CSV ─────────────────────────────────────────────
    ranking_csv = OUTPUT_DIR / "ranking.csv"
    with open(ranking_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "agent", "runs", "agreed", "agree_rate",
                         "avg_util", "util_under_agree", "avg_welfare", "avg_nash",
                         "avg_pareto_dist", "pareto_score", "composite"])
        for rank, s in enumerate(agent_stats, 1):
            pdist_str = f"{s['avg_pdist']:.4f}" if not math.isnan(s['avg_pdist']) else ""
            writer.writerow([
                rank, s["name"], s["runs"], s["agreed"],
                f"{s['agree_rate']:.4f}", f"{s['avg_u']:.4f}",
                f"{s['util_under_agree']:.4f}",
                f"{s['avg_welfare']:.4f}", f"{s['avg_nash']:.4f}",
                pdist_str, f"{s['pareto_score']:.4f}",
                f"{s['composite']:.4f}",
            ])
    print(f"[LOG] Agent ranking written to {ranking_csv}")
    print(f"[LOG] Full console log at {OUTPUT_DIR / 'evaluation.log'}")

    print()
    return results


if __name__ == "__main__":
    # Tee all stdout/stderr to output/<timestamp>/evaluation.log
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
