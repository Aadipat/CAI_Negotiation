from negmas.sao import SAONegotiator, ResponseType
from negmas import Outcome

class TitForTat_Negotiator(SAONegotiator):
    def _init_agent(self):
        if hasattr(self, '_is_initialized'): return
        self.res_val = self.ufun.reserved_value if self.ufun.reserved_value is not None else 0.1
        self.all_outcomes = list(self.nmi.outcome_space.enumerate_or_sample(max_cardinality=10000))
        self.my_utilities = {outcome: float(self.ufun(outcome)) for outcome in self.all_outcomes}
        self.sorted_outcomes = sorted(self.all_outcomes, key=lambda o: self.my_utilities[o], reverse=True)
        
        self.max_opponent_utility = 0.0 
        self._is_initialized = True

    def _get_aspiration(self, progress: float) -> float:
        concession_made_by_opponent = self.max_opponent_utility
        target = 1.0 - concession_made_by_opponent
        
        # 防死锁机制：如果时间快耗尽(>95%)，强制妥协以促成协议
        if progress > 0.95:
            panic_concession = (progress - 0.95) * 20.0  # 0 到 1 的插值
            target = target - (target - self.res_val) * panic_concession
            
        return max(target, self.res_val)

    def respond(self, state, source=None) -> ResponseType:
        self._init_agent()
        offer = state.current_offer
        
        if offer is None:
            return ResponseType.REJECT_OFFER
            
        offer_utility = self.my_utilities.get(offer, float(self.ufun(offer)))
        
        if offer_utility > self.max_opponent_utility:
            self.max_opponent_utility = offer_utility
        
        current_aspiration = self._get_aspiration(state.relative_time)
        
        if offer_utility >= current_aspiration:
            return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER

    def propose(self, state, dest=None) -> Outcome:
        self._init_agent()
        current_aspiration = self._get_aspiration(state.relative_time)
        
        best_proposal = self.sorted_outcomes[0]
        for outcome in self.sorted_outcomes:
            if self.my_utilities[outcome] >= current_aspiration:
                best_proposal = outcome
            else:
                break
        return best_proposal