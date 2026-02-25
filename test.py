from negmas import SAOMechanism, TimeBasedConcedingNegotiator, MappingUtilityFunction
import random  # for generating random ufuns

random.seed(0)  # for reproducibility
session = SAOMechanism(outcomes=10, n_steps=100)
negotiators = [TimeBasedConcedingNegotiator(name=f"a{_}") for _ in range(5)]
for negotiator in negotiators:
    session.add(
        negotiator,
        preferences=MappingUtilityFunction(
            lambda x: random.random() * x[0], outcome_space=session.outcome_space
        ),
    )
print(session.run())