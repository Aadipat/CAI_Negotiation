import random
from negmas.sao import SAONegotiator, ResponseType
from negmas import Outcome

class Adaptive_Negotiator(SAONegotiator):
    def _init_agent(self):
        if hasattr(self, '_is_initialized'): return
        self.res_val = self.ufun.reserved_value if self.ufun.reserved_value is not None else 0.1
        self.all_outcomes = list(self.nmi.outcome_space.enumerate_or_sample(max_cardinality=10000))
        self.my_utilities = {outcome: float(self.ufun(outcome)) for outcome in self.all_outcomes}
        self.sorted_outcomes = sorted(self.all_outcomes, key=lambda o: self.my_utilities[o], reverse=True)
        
        self.best_opponent_offer_utility = self.res_val
        self.my_proposed_offers = set()
        self._is_initialized = True

    def _get_aspiration(self, progress: float) -> float:
        beta = 2.0
        # 基础的 Boulware 衰减曲线
        base_target = 1.0 - (1.0 - self.res_val) * (progress ** beta)
        # 用对手的历史最佳出价进行硬性“兜底” (Backstop)
        return max(base_target, self.best_opponent_offer_utility, self.res_val)

    def respond(self, state, source=None) -> ResponseType:
        self._init_agent()
        offer = state.current_offer
        if offer is None: 
            return ResponseType.REJECT_OFFER
            
        offer_utility = self.my_utilities.get(offer, float(self.ufun(offer)))
        if offer_utility > self.best_opponent_offer_utility:
            self.best_opponent_offer_utility = offer_utility

        current_aspiration = self._get_aspiration(state.relative_time)
        
        if offer_utility >= current_aspiration:
            return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER

    def propose(self, state, dest=None) -> Outcome:
        self._init_agent()
        current_aspiration = self._get_aspiration(state.relative_time)
        
        valid_offers = [o for o in self.sorted_outcomes 
                        if self.my_utilities[o] >= current_aspiration and o not in self.my_proposed_offers]
        
        if valid_offers:
            proposal = random.choice(valid_offers)
        else:
            fallback_offers = [o for o in self.sorted_outcomes if self.my_utilities[o] >= current_aspiration]
            proposal = fallback_offers[-1] if fallback_offers else self.sorted_outcomes[0]
            
        self.my_proposed_offers.add(proposal)
        return proposal