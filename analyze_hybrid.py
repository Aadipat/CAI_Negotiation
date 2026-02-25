"""Quick analysis of HybridAgent results."""
import csv

print("=" * 100)
print("HYBRIDAGENT DETAILED RESULTS")
print("=" * 100)
print(f"{'domain':<18} {'opponent':<16} {'agreed':>6} {'util_a':>8} {'util_b':>8} {'welfare':>8} {'steps':>6} {'status':<10}")
print("-" * 100)

with open('output/results.csv', 'r') as f:
    reader = csv.DictReader(f)
    hybrid_rows = [r for r in reader if r['agent_a'] == 'HybridAgent']

for r in hybrid_rows:
    print(f"{r['domain']:<18} {r['agent_b']:<16} {r['agreement']:>6} {r['util_a']:>8} {r['util_b']:>8} {r['welfare']:>8} {r['steps']:>6} {r['status']:<10}")

# Analyze patterns
agreed = [r for r in hybrid_rows if r['status'] == 'AGREED']
not_agreed = [r for r in hybrid_rows if r['status'] != 'AGREED']

print(f"\nAgreed: {len(agreed)}/{len(hybrid_rows)}")
if agreed:
    utils = [float(r['util_a']) for r in agreed]
    opp_utils = [float(r['util_b']) for r in agreed]
    print(f"Avg self utility: {sum(utils)/len(utils):.4f}")
    print(f"Avg opp utility:  {sum(opp_utils)/len(opp_utils):.4f}")
    print(f"Min self utility: {min(utils):.4f}")
    print(f"Max self utility: {max(utils):.4f}")
    
    print("\nPer-opponent breakdown:")
    from collections import defaultdict
    by_opp = defaultdict(list)
    for r in agreed:
        by_opp[r['agent_b']].append(float(r['util_a']))
    for opp, us in sorted(by_opp.items()):
        print(f"  vs {opp:<16}: avg_util={sum(us)/len(us):.4f}  games={len(us)}")

# Compare with top agents
print("\n" + "=" * 100)
print("TOP 10 vs HYBRIDAGENT comparison")
print("=" * 100)

with open('output/ranking.csv', 'r') as f:
    reader = csv.DictReader(f)
    rankings = list(reader)

for r in rankings[:10]:
    print(f"#{r['rank']:>2} {r['agent']:<25} util={r['avg_util']:>7} agree={r['agree_rate']:>7} welfare={r['avg_welfare']:>7} score={r['composite']:>7}")

hybrid = [r for r in rankings if r['agent'] == 'HybridAgent'][0]
print(f"#{hybrid['rank']:>2} {hybrid['agent']:<25} util={hybrid['avg_util']:>7} agree={hybrid['agree_rate']:>7} welfare={hybrid['avg_welfare']:>7} score={hybrid['composite']:>7}")

print("\nKey insight: HybridAgent has TOP agreement rate (0.8182) but LOWEST avg utility (0.3979)")
print("=> The agent concedes too much. It accepts poor offers too easily.")
print("=> Fix: raise aspiration levels, tighten acceptance thresholds, be less generous")
