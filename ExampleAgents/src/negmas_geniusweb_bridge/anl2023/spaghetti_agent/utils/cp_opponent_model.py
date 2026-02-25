from collections import defaultdict
import numpy as np
import cpmpy as cp

from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.DiscreteValueSet import DiscreteValueSet
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value

class CPOpponentModel:
    _model: cp.Model = None
    # Since the calculations are done in integer values, the base determines the accuracy of the calculation
    _base: int = 100
    # Target utility
    _target = 0.7
    # All the issues inside the domain
    _issues = None
    # The utilities, which the model calculated
    _utilities: [[int]] = None
    # The weights, which the model calculated
    _weights: [int] = None
    # All previous constraints
    _constraints = []
    def __init__(self, domain: Domain):
        self.offers = []
        self.domain = domain
        self._issues = domain.getIssuesValues()
        self._model = self.create_model()

    def create_model(self) -> cp.Model:
        # Record the number of issues in the domain
        n_issues = len(self._issues)
        # Get the maximum number of values for a single issue
        max_issues = max([values.size() for values in self._issues.values()])

        # Create a initialize all the weights as -1
        unknown_weight = -1
        weights = np.array([unknown_weight for _ in range(n_issues)])

        # We need to account for the different number of values per issue. For that, we create a 2D array (issues, value)
        # where each value represents a possible utility. If the issue has less values than the max_values, the others are set to 0.

        # create all utilities as 0s
        given = np.zeros((n_issues, max_issues))
        # fill out the places where utility matters
        unknown_utility = -1
        for s, issue in enumerate(self._issues.values()):
            for t, value in enumerate(issue):
                given[s][t] = unknown_utility

        # VARIABLES
        self._weights = cp.intvar(0, self._base, shape=weights.shape, name="weights")
        self._utilities = cp.intvar(0, self._base, shape=given.shape, name="utilities")

        # MODEL
        model = cp.Model(
            # If the value is not default_utility, the value is hardcoded
            (self._utilities[given != unknown_utility] == given[given != unknown_utility])
        )

        return model

    def update(self, bid: Bid) -> bool:
        # keep track of all bids received
        self.offers.append(bid)

        # retrieve the indexes of each issue
        issues_idx = [list(self._issues.keys()).index(issue) for issue in bid.getIssues()]
        # retrieve the indexes of each value
        values_idx = [list(self._issues.get(issue)).index(bid.getValue(issue))
                        for issue in bid.getIssues()]

        # produce an equation from the ids of issues and values
        equation = cp.sum([self._weights[weight] * self._utilities[weight][utility]
                        for (weight, utility) in zip(issues_idx, values_idx)])
        # add the equation as a constraint
        self._model += (equation >= 70)
        # keep a record of all constraints and change the maximize optimal function
        self._constraints.append(equation)
        self._model.maximize(sum(self._constraints))

        # solve the equation
        if len(self.offers) > 30:
            return self._model.solve()
        return True

    def get_predicted_utility(self, bid: Bid):
        if len(self.offers) <= 40 or bid is None:
            return 0

        # initiate
        total_issue_weight = 0.0
        value_utilities = []
        issue_weights = []

        # For each issue inside the bid
        for issue in bid.getIssueValues():
            # find the id of the issue
            issue_idx = list(self._issues.keys()).index(issue)
            # find the id of the value
            value_idx = list(self._issues.get(issue)).index(bid.getValue(issue))
            # append the predicted weight to the result arrays
            issue_weights.append(self._weights[issue_idx])
            # gather all utilities
            utilities = self._utilities.value()[issue_idx]
            # If utility is none, make it a zero
            utilities[utilities is None] = 0

            utility = utilities[value_idx]
            # calculate the sum of all utilities for that issue
            utilities_sum = sum(utilities)
            # make sure the sum is not 0, otherwise
            if utilities_sum == 0:
                utilities_sum = 1
            if utility is None:
                utility = 0
            # normalize the utility and append it to the array
            utility_n = utility / utilities_sum
            value_utilities.append(utility_n)

            total_issue_weight += self._weights[issue_idx]


        # normalise the issue weights such that the sum is 1.0
        if total_issue_weight == 0.0:
            issue_weights = [1 / len(issue_weights) for _ in issue_weights]
        else:
            issue_weights = [iw / total_issue_weight for iw in issue_weights]

        # calculate predicted utility by multiplying all value utilities with their issue weight
        predicted_utility = sum(
            [iw * vu for iw, vu in zip(issue_weights, value_utilities)]
        )

        return predicted_utility