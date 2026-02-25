from negmas import SAOMechanism, make_issue
from negmas.preferences import LinearAdditiveUtilityFunction
from negmas.sao import AspirationNegotiator

from negmas_geniusweb_bridge import BoulwareAgent

# Define a larger negotiation space for more interesting dynamics
issues = [make_issue(10, "price"), make_issue(7, "quality"), make_issue(5, "delivery")]

# Create opposing utility functions so agents must negotiate harder
# Agent A prefers high price, low quality, low delivery
# Agent B prefers low price, high quality, high delivery
ufun_a = LinearAdditiveUtilityFunction(
    values=[
        dict(zip(range(10), [i / 9 for i in range(10)])),        # price: higher is better
        dict(zip(range(7), [(6 - i) / 6 for i in range(7)])),    # quality: lower is better
        dict(zip(range(5), [(4 - i) / 4 for i in range(5)])),    # delivery: lower is better
    ],
    weights=[0.5, 0.3, 0.2],
    issues=issues,
)
ufun_b = LinearAdditiveUtilityFunction(
    values=[
        dict(zip(range(10), [(9 - i) / 9 for i in range(10)])),  # price: lower is better
        dict(zip(range(7), [i / 6 for i in range(7)])),           # quality: higher is better
        dict(zip(range(5), [i / 4 for i in range(5)])),           # delivery: higher is better
    ],
    weights=[0.5, 0.3, 0.2],
    issues=issues,
)

# Create the negotiation mechanism
mechanism = SAOMechanism(issues=issues, n_steps=100)

# Create a GeniusWeb agent (Boulware strategy)
gw_agent = BoulwareAgent(ufun=ufun_a, name="geniusweb_boulware")

# Create a NegMAS agent (Aspiration strategy)
negmas_agent = AspirationNegotiator(ufun=ufun_b, name="aspiration")

# Add agents to the mechanism
mechanism.add(gw_agent)
mechanism.add(negmas_agent)

# Run the negotiation
mechanism.run()

# Check results
state = mechanism.state
print(f"Agreement: {state.agreement}")
print(f"Steps: {state.step}")
if state.agreement:
    print(f"Utility for A: {ufun_a(state.agreement):.3f}")
    print(f"Utility for B: {ufun_b(state.agreement):.3f}")
else:
    print("No agreement reached!")
