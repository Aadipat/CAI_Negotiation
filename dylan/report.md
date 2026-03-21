# 2 The Assignment

## 2.1 Negotiation Setup

We implemented and evaluated our agent in the NegMAS bilateral SAOP setup from the assignment:

- Two-party alternating-offers negotiation (SAOP).
- Multi-issue additive linear utility domains.
- Unknown opponent preferences and unknown opponent reservation value.
- No discounting.

Our implementation target is `feiyang/hybrid_agent.py` and its BOA-style components:

- Opponent model: `feiyang/opponent_model.py`
- Bidding experts: `feiyang/experts.py`
- Meta-controller: `feiyang/meta_controller.py`
- Acceptance: `feiyang/acceptance.py`

This section focuses on objectively improving the **bidding strategy** while keeping evaluation reproducible.

## 2.2 Method: Objective Bidding Strategy Improvement

### Baseline

We first measured the unmodified branch state with:

- `python eval_simple.py` (saved in `baseline_eval_simple_current.txt`)
- `python test_improvement.py` (saved in `baseline_test_improvement_current.txt`, plots in `improvement_output/20260319_175456`)

### Change Applied (Bidding Only)

We changed the bidding logic in two places:

1. `feiyang/experts.py`
- Added Nash/welfare blended candidate scoring (`_pick_balanced_nash`) instead of only linear self-opponent weighted scoring.
- Updated `ParetoExpert.propose()` to select bids using this Nash-oriented scoring.
- Updated `DealSeekerExpert.propose()` to use the same balanced Nash selection in late-game candidate choice.

2. `feiyang/meta_controller.py`
- Increased mid-phase prior weight for `ParetoExpert` so the agent explores more mutually efficient bids.
- Added a small Pareto boost when opponent style is ambiguous.

These changes are intentionally limited to offer generation/selection (bidding), not a broad architecture rewrite.

## 2.3 Experimental Protocol

We re-ran both evaluation scripts with the same codebase and seeds:

- Post-change `eval_simple.py` output: `improved_eval_simple_v1.txt`
- Post-change `test_improvement.py` output: `improved_test_improvement_v1.txt`
- Post-change plots: `improvement_output/20260319_175808`

The objective comparison is baseline vs post-change using identical metrics.

## 2.4 Analyzing the Performance of Our Agent

### A) `eval_simple.py` (Pareto + Nash focus)

HybridAgent aggregate metrics:

| Version | Pareto Optimality (POpt) | Nash Optimality (NOpt) | Composite Score | Rank |
|---|---:|---:|---:|---:|
| Baseline | 0.9882 | 0.8820 | 0.8748 | 8/18 |
| Improved bidding | 0.9915 | 0.8701 | 0.8816 | 3/18 |
| Delta | +0.0033 | -0.0119 | +0.0068 | +5 places |

Interpretation:

- Pareto efficiency improved.
- Nash optimality decreased slightly.
- Total score and ranking improved substantially (from 8th to 3rd), so the net effect is positive.

Because the total score improved, we include it as an additional indicator as requested.

### B) `test_improvement.py` (behavioral robustness across opponents/domains)

`v2_baseline` row (our actual agent config in this harness):

| Version | Agreement Rate | Avg Our Utility | Avg Opp Utility | Avg Welfare | Avg Rounds |
|---|---:|---:|---:|---:|---:|
| Baseline | 85.0% | 0.7001 | 0.6615 | 1.3615 | 47.7 |
| Improved bidding | 86.7% | 0.6991 | 0.6605 | 1.3596 | 48.4 |
| Delta | +1.7 pp | -0.0010 | -0.0010 | -0.0019 | +0.7 |

Interpretation:

- Agreement improved with almost unchanged utility/welfare.
- Trade-off: slightly longer negotiations on average.

Per-opponent highlights (`v2_baseline` in both runs):

- Random: agreement improved from 50.0% to 66.7%.
- MiCRO: agreement stayed 75.0%, with longer rounds.
- Tough: unchanged at 25.0% agreement (still hardest opponent type).

### C) Graph-supported observations

From `05_expert_usage_heatmap.png`:

- Baseline had near-zero Pareto usage across phases.
- Improved run shows non-zero Pareto activation (small, but present) in mid/late bins.

From `08_scenario_heatmap.png`:

- Better agreement/utility on easier and integrative scenarios.
- Lower agreement in the highest-opposition scenario (clear remaining weakness).

Overall, the plots match the numeric trend: broader deal-finding with a small quality trade-off in difficult domains.

## 2.5 Conclusion for This Iteration

This bidding-strategy iteration objectively improved the agent:

- Better Pareto metric in `eval_simple`.
- Stronger overall ranking and composite score.
- Higher agreement in `test_improvement` with minimal utility loss.

Main remaining gap:

- Nash metric dropped slightly, and high-opposition/Tough-style negotiations remain difficult.

Planned next step:

- Add a tougher late-phase, high-opposition bid filter that preserves Nash quality while keeping the agreement gains.

