# file: test_tournament.py
import random
import csv
import math
from collections import defaultdict
from statistics import mean
from pathlib import Path

from negmas import make_issue, SAOMechanism
from negmas.preferences import LinearAdditiveUtilityFunction as LUFun
from negmas.preferences.value_fun import LinearFun, IdentityFun, AffineFun

# import your agent
from agent import Group56_Negotiator
from main import SmartAspirationNegotiator

OUTPUT_DIR = Path("results")
OUTPUT_DIR.mkdir(exist_ok=True)

def outcome_to_vector(o):
    if o is None:
        return None
    # common cases
    if isinstance(o, (list, tuple)):
        try:
            return tuple(float(x) for x in o)
        except Exception:
            pass
    # dict-like
    try:
        vals = tuple(o.values())
        return tuple(float(x) for x in vals)
    except Exception:
        pass
    # try to_tuple
    try:
        t = tuple(o.to_tuple())
        return tuple(float(x) for x in t)
    except Exception:
        pass
    # fallback: attempt to iterate and cast
    try:
        return tuple(float(x) for x in list(o))
    except Exception:
        return tuple()  # empty -> treat special

def euclidean(a, b):
    if a is None or b is None:
        return float("inf")
    if len(a) != len(b):
        # try pad/truncate
        L = min(len(a), len(b))
        return math.sqrt(sum((a[i] - b[i])**2 for i in range(L)))
    return math.sqrt(sum((x - y)**2 for x,y in zip(a,b)))

def build_domain(n_steps=30):
    issues = [
        make_issue(name="price", values=10),
        make_issue(name="quantity", values=(1, 11)),
        make_issue(name="delivery_time", values=10),
    ]
    mech = SAOMechanism(issues=issues, n_steps=n_steps)
    seller_utility = LUFun(
        values={
            "price": IdentityFun(),
            "quantity": LinearFun(0.2),
            "delivery_time": AffineFun(-1, bias=9),
        },
        weights={"price": 1.0, "quantity": 1.0, "delivery_time": 10.0},
        outcome_space=mech.outcome_space,
        reserved_value=15.0,
    ).scale_max(1.0)
    buyer_utility = LUFun(
        values={
            "price": AffineFun(-1, bias=9.0),
            "quantity": LinearFun(0.2),
            "delivery_time": IdentityFun(),
        },
        outcome_space=mech.outcome_space,
        reserved_value=10.0,
    ).scale_max(1.0)
    return mech, buyer_utility, seller_utility

def run_once(
    agent_cls,
    seed=0,
    n_steps=30,
    replace_buyer=False,
    replace_seller=True,
):
    random.seed(seed)
    mech, buy_uf, sell_uf = build_domain(n_steps=n_steps)
    buyer_cls = agent_cls if replace_buyer else SmartAspirationNegotiator
    seller_cls = agent_cls if replace_seller else SmartAspirationNegotiator

    buyer = buyer_cls(name=f"buyer_{seed}")
    seller = seller_cls(name=f"seller_{seed}")

    mech.add(buyer, ufun=buy_uf)
    mech.add(seller, ufun=sell_uf)

    res = mech.run()
    # collect metrics
    agreement = res.agreement
    # utilities
    u_b = buy_uf(agreement) if agreement is not None else None
    u_s = sell_uf(agreement) if agreement is not None else None
    # rounds to agreement; if no agreement, n_steps
    rounds = res.steps if hasattr(res, "steps") else mech.n_steps
    return {
        "agreement": agreement,
        "u_b": u_b,
        "u_s": u_s,
        "rounds": rounds,
        "mechanism": mech,
        "result": res,
    }

def evaluate(agent_cls, n_runs=50, seed_offset=0):
    scenarios = [
        {
            "name": "agent_as_seller_vs_smart_buyer",
            "replace_buyer": False,
            "replace_seller": True,
        },
        {
            "name": "agent_as_buyer_vs_smart_seller",
            "replace_buyer": True,
            "replace_seller": False,
        },
        {
            "name": "self_play",
            "replace_buyer": True,
            "replace_seller": True,
        },
    ]

    rows = []
    for scenario in scenarios:
        for seed in range(seed_offset, seed_offset + n_runs):
            r = run_once(
                agent_cls,
                seed=seed,
                replace_buyer=scenario["replace_buyer"],
                replace_seller=scenario["replace_seller"],
            )
            # compute pareto/nash points from the mechanism used (compute once and reuse if you want)
            mech = r["mechanism"]
            # try to get pareto frontier and nash
            try:
                frontier_utils, frontier_outcomes = mech.pareto_frontier()
                nash_utils, nash_outcome = mech.nash_points()[0]
                nash_welfare = sum(nash_utils)
            except Exception:
                frontier_outcomes = []
                nash_welfare = None

            agreement = r["agreement"]
            if agreement is None:
                pdist = None
                ndiff = None
            else:
                vec_ag = outcome_to_vector(agreement)
                if frontier_outcomes:
                    frontier_vecs = [outcome_to_vector(o) for o in frontier_outcomes]
                    # compute minimal euclidean distance to any frontier point (in util-space or outcome space)
                    pdist = min(euclidean(vec_ag, fv) for fv in frontier_vecs if fv)
                else:
                    pdist = None
                # nash difference (welfare difference)
                if nash_welfare is not None:
                    utilities = [
                        n.ufun(agreement)
                        for n in mech.negotiators
                        if getattr(n, "ufun", None) is not None
                    ]
                    ndiff = nash_welfare - sum(utilities)
                else:
                    ndiff = None

            rows.append({
                "scenario": scenario["name"],
                "seed": seed,
                "agreement": str(agreement),
                "u_b": r["u_b"],
                "u_s": r["u_s"],
                "rounds": r["rounds"],
                "pareto_dist": pdist,
                "nash_diff": ndiff,
            })
    # write CSV
    out = OUTPUT_DIR / f"eval_{agent_cls.__name__}.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {out}")
    return rows

if __name__ == "__main__":
    # evaluate baseline agent vs your agent (replace seller)
    evaluate(Group56_Negotiator, n_runs=30)