from ast import List
from random import randint
from time import time
from typing import cast

from geniusweb.issuevalue.Bid import Bid


class Acceptance:
    """
    https://www.sciencedirect.com/science/article/abs/pii/S0167923613001693
    """
    alpha: float = 1.02
    beta: float = 0.0
    timeout_1st: float = 0.95
    timeout_2nd: float = 0.98
    timeout_last_offer: float = 0.999
    minimum_utility: float = 0.6

    utility = None
    bid_history = None

    def __init__(self, bid_history, utility, opponent_model) -> None:
        self.bid_history = bid_history
        self.utility = utility
        self.opponent_model = opponent_model
        self.max_utility = 0.0
        self.avg_utility = 0.0

    def set_utility(self, utility) -> None:
        self.utility = utility
    def set_model(self, model) -> None:
        self.opponent_model = model
    
    def get_utility(self, bid: Bid) -> float:
        if bid == None:
            return 0.0
        return float(self.utility(bid))

    def max_W(self, opponent_utility) -> float:
        """
        Returns the utility of the best bid.
        """
        self.max_utility = max(self.max_utility, opponent_utility)
        

    def avg_W(self, opponent_utility) -> float:
        """
        Returns the average utility of the previous W bids
        """
        self.avg_utility = (len(self.bid_history)-1)/len(self.bid_history) * self.avg_utility + opponent_utility/len(self.bid_history)

    def accept_condition(self, opponent_bid: Bid, next_bid: Bid, progress) -> bool:
        """
        We accept if the opponent sent us similar utility bid that we would offer 
        or
        we are running out of time and we deem the offer as sufficient
        """
        if opponent_bid == None or next_bid == None or self.opponent_model == None:
            return False
        if progress < 0.333:
            return False
        

        opponent_utility = self.get_utility(opponent_bid)
        opponent_model_utility = self.opponent_model.get_predicted_utility(opponent_bid)
        next_utility = self.get_utility(next_bid)
        next_model_utility = self.opponent_model.get_predicted_utility(next_bid)

        opponent_nash = opponent_utility * (0.2 * (1-progress)**2 + 0.2 + opponent_model_utility) 
        next_nash = next_utility * (0.2 * (1-progress)**2 + 0.2 + next_model_utility) 
        
        self.max_W(opponent_utility)
        self.avg_W(opponent_utility)


        if progress < self.timeout_last_offer:
            return self.alpha * opponent_nash + self.beta >= next_nash
        elif self.timeout_last_offer:
            return True
