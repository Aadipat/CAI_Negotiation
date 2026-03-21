from negmas.sao import SAONegotiator, ResponseType

import numpy as np


class TimeBasedAspirationConceder(SAONegotiator):
    def __init__(self, alpha=1.0, beta=0.1, gamma=1.0, **kwargs):
        super().__init__(**kwargs)
        self.alpha = alpha  # Starting aspiration
        self.beta = beta    # Minimum utility (reserve)
        self.gamma = gamma  # > 1 is Boulware (Stubborn), < 1 is Conceder (Quick)
        self.utility_history = []

    # def get_aspiration(self, state):
    #     """Standard Power-law: beta + (alpha - beta) * (1 - t^gamma)"""
    #     t = state.step / (self.nmi.n_steps - 1)
    #     return self.beta + (self.alpha - self.beta) * (1.0 - pow(t, self.gamma))

    def get_aspiration(self, state):
        """
        Implements the exponential aspiration function:
        lambda(t) = (alpha - beta) * [(1 - gamma^(1 - t/T)) / (1 - gamma)] + beta
        """
        # t_rel represents t/T (current step / total steps)
        t_rel = state.step / (self.nmi.n_steps - 1)
        
        # Handle the linear case (gamma=1) to avoid division by zero
        if self.gamma == 1.0:
            return self.beta + (self.alpha - self.beta) * (1.0 - t_rel)
            
        # Calculation based on the requested formula
        numerator = 1.0 - pow(self.gamma, (1.0 - t_rel))
        denominator = 1.0 - self.gamma
        
        return (self.alpha - self.beta) * (numerator / denominator) + self.beta

    def propose(self, state):
        target_asp = self.get_aspiration(state)
        # Use a large sample to find a discrete outcome closest to the mathematical curve
        outcomes = self.nmi.random_outcomes(1000) 
        best_bid = min(outcomes, key=lambda o: abs(self.ufun(o) - target_asp))
        
        # Record utility for plotting
        self.utility_history.append(self.ufun(best_bid))
        return best_bid

    def respond(self, state, source=None):
        offer = state.current_offer
        if not offer or self.ufun(offer) < self.get_aspiration(state):
            return ResponseType.REJECT_OFFER
        return ResponseType.ACCEPT_OFFER


class UniqueArgmaxTimeBasedConceder(SAONegotiator):
    def __init__(self, alpha=1.0, beta=0.1, gamma=1.0, **kwargs):
        super().__init__(**kwargs)
        self.alpha, self.beta, self.gamma = alpha, beta, gamma
        self.utility_history = []
        self.sent_offers = set()
        self.all_outcomes = None
        self.all_utils = None

    def on_negotiation_start(self, state):
        """Pre-calculate the entire space once to enable 'argmax' logic."""
        # Enumerate every possible combination of issues
        self.all_outcomes = list(self.nmi.outcome_space.enumerate()) #
        # Pre-calculate utilities for all outcomes
        self.all_utils = np.array([float(self.ufun(o)) for o in self.all_outcomes])

    # def get_aspiration(self, state):
    #     """Standard Power-law: beta + (alpha - beta) * (1 - t^gamma)"""
    #     t = state.step / (self.nmi.n_steps - 1)
    #     return self.beta + (self.alpha - self.beta) * (1.0 - pow(t, self.gamma))

    def get_aspiration(self, state):
        """
        Implements the exponential aspiration function:
        lambda(t) = (alpha - beta) * [(1 - gamma^(1 - t/T)) / (1 - gamma)] + beta
        """
        # t_rel represents t/T (current step / total steps)
        t_rel = state.step / (self.nmi.n_steps - 1)
        
        # Handle the linear case (gamma=1) to avoid division by zero
        if self.gamma == 1.0:
            return self.beta + (self.alpha - self.beta) * (1.0 - t_rel)
            
        # Calculation based on the requested formula
        numerator = 1.0 - pow(self.gamma, (1.0 - t_rel))
        denominator = 1.0 - self.gamma
        
        return (self.alpha - self.beta) * (numerator / denominator) + self.beta

    def propose(self, state):
        target_asp = self.get_aspiration(state)
        
        # 1. Create a mask to exclude already sent offers
        # We find indices of outcomes not in our sent_offers set
        available_indices = [
            i for i, o in enumerate(self.all_outcomes) 
            if o not in self.sent_offers
        ]

        if not available_indices:
            return None # Space exhausted

        # 2. Perform 'argmax' (finding the minimum distance) only on available outcomes
        available_utils = self.all_utils[available_indices]
        # Find index within the 'available' subset that is closest to target
        relative_idx = np.argmin(np.abs(available_utils - target_asp))
        
        # 3. Map back to the original outcome
        best_idx = available_indices[relative_idx]
        best_bid = self.all_outcomes[best_idx]
        
        # 4. Update trackers
        self.sent_offers.add(best_bid)
        self.utility_history.append(self.all_utils[best_idx])
        
        return best_bid

    def respond(self, state, source=None):
        offer = state.current_offer
        if not offer or self.ufun(offer) < self.get_aspiration(state):
            return ResponseType.REJECT_OFFER
        return ResponseType.ACCEPT_OFFER


class AdaptiveUniqueArgmaxConceder(SAONegotiator):
    def __init__(self, alpha=1.0, beta_start=0.5, beta_backstop=0.1, gamma=1.0, window_size=5, **kwargs):
        super().__init__(**kwargs)
        self.alpha = alpha
        self.beta = beta_start        # Current target reserve
        self.beta_backstop = beta_backstop  # Hard floor
        self.gamma = gamma
        self.window_size = window_size
        
        self.utility_history = []
        self.sent_offers = set()
        self.opponent_utilities = []
        self.all_outcomes = None
        self.all_utils = None

    def on_negotiation_start(self, state):
        # Pre-calculate once for Argmax efficiency
        self.all_outcomes = list(self.nmi.outcome_space.enumerate())
        self.all_utils = np.array([float(self.ufun(o)) for o in self.all_outcomes])

    def update_beta(self, state):
        """Adjusts beta based on opponent concession rate."""
        if len(self.opponent_utilities) < self.window_size:
            return

        # Calculate opponent's recent concession rate
        recent_opp_utils = self.opponent_utilities[-self.window_size:]
        concession = recent_opp_utils[-1] - recent_opp_utils[0]

        # Adaptive logic:
        # If opponent is conceding (concession > 0), we can slowly lower beta 
        # to meet them, but never below the backstop.
        if concession > 0.01:
            self.beta = max(self.beta - 0.05, self.beta_backstop)
        # If opponent is stagnant or toughening, we stay firm or increase beta
        elif concession <= 0:
            self.beta = min(self.beta + 0.02, self.alpha)

    # def get_aspiration(self, state):
    #     t = state.step / (self.nmi.n_steps - 1)
    #     # Uses the current adapted beta
    #     return self.beta + (self.alpha - self.beta) * (1.0 - pow(t, self.gamma))

    def get_aspiration(self, state):
        """
        Implements the exponential aspiration function:
        lambda(t) = (alpha - beta) * [(1 - gamma^(1 - t/T)) / (1 - gamma)] + beta
        """
        # t_rel represents t/T (current step / total steps)
        t_rel = state.step / (self.nmi.n_steps - 1)
        
        # Handle the linear case (gamma=1) to avoid division by zero
        if self.gamma == 1.0:
            return self.beta + (self.alpha - self.beta) * (1.0 - t_rel)
            
        # Calculation based on the requested formula
        numerator = 1.0 - pow(self.gamma, (1.0 - t_rel))
        denominator = 1.0 - self.gamma
        
        return (self.alpha - self.beta) * (numerator / denominator) + self.beta

    def propose(self, state):
        self.update_beta(state)
        target_asp = self.get_aspiration(state)
        
        # Filter unique offers
        available_indices = [i for i, o in enumerate(self.all_outcomes) if o not in self.sent_offers]
        if not available_indices: return None

        # Argmax selection
        available_utils = self.all_utils[available_indices]
        relative_idx = np.argmin(np.abs(available_utils - target_asp))
        best_idx = available_indices[relative_idx]
        best_bid = self.all_outcomes[best_idx]
        
        self.sent_offers.add(best_bid)
        self.utility_history.append(self.all_utils[best_idx])
        return best_bid

    def respond(self, state, source=None):
        offer = state.current_offer
        if offer:
            # Track what the opponent offers us (from our perspective)
            self.opponent_utilities.append(self.ufun(offer))
            
            if self.ufun(offer) >= self.get_aspiration(state):
                return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


import numpy as np
import itertools
from negmas import *

class NaiveBayesianTimeBasedNegotiator(SAONegotiator):
    def __init__(self, alpha=1.0, beta=0.1, gamma=1.0, **kwargs):
        super().__init__(**kwargs)
        self.alpha, self.beta, self.gamma = alpha, beta, gamma
        self.utility_history = []
        self.sent_offers = set()

    def on_negotiation_start(self, state):
        # 1. Vectorized Hypothesis Space
        # Create a grid of weights that sum to 1
        steps = [0.1, 0.5, 0.9] 
        grid = np.array(list(itertools.product(steps, repeat=3)))
        self.hypotheses = grid / grid.sum(axis=1)[:, None] # Normalize rows to sum to 1
        self.probs = np.ones(len(self.hypotheses)) / len(self.hypotheses)

        # 2. Pre-calculate Outcome Matrix (Normalized 0-1)
        self.all_outcomes = list(self.nmi.outcome_space.enumerate())
        # Matrix shape: (n_outcomes, 3)
        self.outcome_matrix = np.array([
            [(o[0]-10)/20, (o[1]-1)/19, (o[2]-1)/14] for o in self.all_outcomes
        ])
        self.all_utils = np.array([float(self.ufun(o)) for o in self.all_outcomes])

    def update_beliefs(self, offer):
        # Normalized offer vector
        v = np.array([(offer[0]-10)/20, (offer[1]-1)/19, (offer[2]-1)/14])
        
        # Vectorized Likelihood: P(O|H)
        # u is the utility of this offer for every hypothesis
        u = self.hypotheses @ v 
        likelihoods = np.exp(5 * u)
        
        # Bayesian Update
        self.probs *= likelihoods
        self.probs /= self.probs.sum()

    def propose(self, state):
        t = state.step / (self.nmi.n_steps - 1)
        target_asp = self.beta + (self.alpha - self.beta) * (1.0 - pow(t, self.gamma))
        
        # Find indices of unsent offers
        indices = [i for i, o in enumerate(self.all_outcomes) if o not in self.sent_offers]
        if not indices: return None

        # Filter by aspiration
        acceptable = [i for i in indices if self.all_utils[i] >= target_asp]
        
        if not acceptable:
            best_idx = indices[np.argmin(np.abs(self.all_utils[indices] - target_asp))]
        else:
            # VECTORIZED EXPECTED UTILITY
            # Calculate utility of all acceptable outcomes for all hypotheses at once
            # Result is (n_acceptable, n_hypotheses)
            subset_matrix = self.outcome_matrix[acceptable]
            hyp_utils = subset_matrix @ self.hypotheses.T
            
            # Weighted average by our probabilities
            expected_opp_utils = hyp_utils @ self.probs
            best_idx = acceptable[np.argmax(expected_opp_utils)]

        best_bid = self.all_outcomes[best_idx]
        self.sent_offers.add(best_bid)
        self.utility_history.append(self.all_utils[best_idx])
        return best_bid

    def respond(self, state, source=None):
        offer = state.current_offer
        if offer:
            self.update_beliefs(offer)
            t = state.step / (self.nmi.n_steps - 1)
            asp = self.beta + (self.alpha - self.beta) * (1.0 - pow(t, self.gamma))
            if self.ufun(offer) >= asp:
                return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER