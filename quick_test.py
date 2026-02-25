"""Quick intermediate test: HybridAgent vs NegMAS built-in opponents."""
import sys
from pathlib import Path

_base = Path(__file__).resolve().parent
_bridge_src = _base / "ExampleAgents" / "src"
sys.path.insert(0, str(_bridge_src))

_vendor = _base / "ExampleAgents" / "vendor"
for _sub in ("geniusweb-1.2.1", "others/tudelft_utilities", "others/tudelft_utilities_logging", "others/uri", "others/pyson"):
    _p = _vendor / _sub
    if _p.exists():
        sys.path.insert(0, str(_p))

sys.path.insert(0, str(_base))

from negmas import SAOMechanism, make_issue, TimeBasedConcedingNegotiator
from negmas.sao import AspirationNegotiator
from negmas.preferences import LinearAdditiveUtilityFunction as LUFun
from negmas.preferences.value_fun import LinearFun, IdentityFun, AffineFun
from negmas_geniusweb_bridge.wrapper import make_geniusweb_negotiator
from feiyang.hybrid_agent import HybridAgent

print("=" * 80)
print("INTERMEDIATE TEST: HybridAgent (tuned v2)")
print("=" * 80)

WrappedHybrid = make_geniusweb_negotiator(HybridAgent)

results = []

for opp_cls, opp_name in [(TimeBasedConcedingNegotiator, "TBConceder"), (AspirationNegotiator, "Aspiration")]:
    for trial in range(5):
        issues = [
            make_issue(name="price", values=10),
            make_issue(name="quantity", values=(1, 11)),
            make_issue(name="delivery_time", values=10),
        ]
        m = SAOMechanism(issues=issues, n_steps=100)

        buyer_ufun = LUFun(
            values={"price": AffineFun(-1, bias=9.0), "quantity": LinearFun(0.2), "delivery_time": IdentityFun()},
            outcome_space=m.outcome_space,
        ).scale_max(1.0)
        seller_ufun = LUFun(
            values=[IdentityFun(), LinearFun(0.2), AffineFun(-1, bias=9.0)],
            outcome_space=m.outcome_space,
        ).scale_max(1.0)

        n1 = WrappedHybrid(ufun=buyer_ufun, name="HybridAgent")
        n2 = opp_cls(ufun=seller_ufun, name=opp_name)
        m.add(n1)
        m.add(n2)
        m.run()

        agreed = m.agreement is not None
        u1 = float(buyer_ufun(m.agreement)) if agreed else None
        u2 = float(seller_ufun(m.agreement)) if agreed else None
        results.append({"trial": trial, "opp": opp_name, "agreed": agreed, "u_hybrid": u1, "u_opp": u2})
        status = f"u_self={u1:.3f} u_opp={u2:.3f}" if agreed else "NO DEAL"
        print(f"  vs {opp_name} trial={trial}: {status}")

# Summary
print("\n" + "=" * 80)
agreed_r = [r for r in results if r["agreed"]]
n_agreed = len(agreed_r)
n_total = len(results)
if agreed_r:
    avg_u = sum(r["u_hybrid"] for r in agreed_r) / n_agreed
    print(f"Agreed: {n_agreed}/{n_total}")
    print(f"Avg self utility: {avg_u:.4f}")
    print(f"Min self utility: {min(r['u_hybrid'] for r in agreed_r):.4f}")
    print(f"Max self utility: {max(r['u_hybrid'] for r in agreed_r):.4f}")
    for opp in ["TBConceder", "Aspiration"]:
        opp_r = [r for r in agreed_r if r["opp"] == opp]
        if opp_r:
            avg = sum(r["u_hybrid"] for r in opp_r) / len(opp_r)
            print(f"  vs {opp}: avg={avg:.4f} agreed={len(opp_r)}/5")
        else:
            print(f"  vs {opp}: no agreements")
else:
    print(f"No agreements in {n_total} negotiations")
