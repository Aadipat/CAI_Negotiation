import numpy as np

from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain


class OpponentModel:
    def __init__(self, domain: Domain):
        self.domain = domain
        self.issues = self.domain.getIssues()
        self.offers = [[] for _ in self.issues]

    def update(self, bid: Bid):
        # keep track of all bids received
        for i, (_, value) in enumerate(bid.getIssueValues().items()):
            self.offers[i].append(str(value))
    
    def __call__(self, bid: Bid):
        util = self.get_utility(bid)
        return util
    
    def get_utility(self, bid: Bid):
        ws = self.get_weights()
        es = self.get_evaluations(bid)
        util = ws @ es
        return util
    
    def get_weights(self):
        weights = []
        for i in range(len(self.issues)):
            weights.append(self.get_weight(self.offers[i]))
        weights = [w / sum(weights) for w in weights]
        return np.array(weights)
    
    def get_weight(self, offer):
        _, counts = np.unique(offer, return_counts=True)
        if len(counts) == 0:
            return 1
        return max(counts) / sum(counts)
    
    def get_evaluations(self, bid: Bid):
        evals = []
        for i, (_, value) in enumerate(bid.getIssueValues().items()):
            evals.append(self.get_eval(value, self.offers[i]))
        return np.array(evals)
    
    def get_eval(self, value, offer):
        o_count = offer.count(value)
        _, counts = np.unique(offer, return_counts=True)
        if len(counts) == 0:
            return 1
        return o_count / sum(counts)