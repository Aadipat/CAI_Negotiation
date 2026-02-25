from negmas.sao import SAONegotiator, ResponseType
from negmas import Outcome

class Micro_Negotiator(SAONegotiator):
    def _init_agent(self):
        if hasattr(self, '_is_initialized'): return
        
        self.res_val = self.ufun.reserved_value if self.ufun.reserved_value is not None else 0.1
        self.all_outcomes = list(self.nmi.outcome_space.enumerate_or_sample(max_cardinality=10000))
        self.my_utilities = {outcome: float(self.ufun(outcome)) for outcome in self.all_outcomes}
        self.sorted_outcomes = sorted(self.all_outcomes, key=lambda o: self.my_utilities[o], reverse=True)
        
        self.micro_pointer = 0 
        self.seen_opponent_offers = set() 
        self._is_initialized = True

    def respond(self, state, source=None) -> ResponseType:
        self._init_agent()
        offer = state.current_offer
        
        if offer is None:
            return ResponseType.REJECT_OFFER
            
        if offer not in self.seen_opponent_offers:
            self.seen_opponent_offers.add(offer)
            # 对手提出新出价，我方退让一步 (pointer + 1)
            self.micro_pointer = min(self.micro_pointer + 1, len(self.sorted_outcomes) - 1)
            
        offer_utility = self.my_utilities.get(offer, float(self.ufun(offer)))
        current_my_target_utility = self.my_utilities[self.sorted_outcomes[self.micro_pointer]]
        
        if offer_utility >= current_my_target_utility:
            return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER

    def propose(self, state, dest=None) -> Outcome:
        self._init_agent()
        return self.sorted_outcomes[self.micro_pointer]