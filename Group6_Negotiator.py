import random
from collections import defaultdict
from negmas.sao import SAONegotiator, ResponseType
from negmas import Outcome

class Group6_Negotiator(SAONegotiator):
 

    def _init_agent(self):
        if hasattr(self, '_is_initialized'): 
            return
        
        # 1. 忽略底层默认的 0.0，强行设定钢铁底线（例如 0.5，代表绝不放弃一半以上的利益）
        default_res = self.ufun.reserved_value if self.ufun.reserved_value is not None else 0.0
        self.strict_floor = max(default_res, 0.5) 
        
        self.all_outcomes = list(self.nmi.outcome_space.enumerate_or_sample(max_cardinality=10000))
        self.my_utilities = {outcome: float(self.ufun(outcome)) for outcome in self.all_outcomes}
        self.sorted_outcomes = sorted(self.all_outcomes, key=lambda o: self.my_utilities[o], reverse=True)
        
        self.opponent_bid_history = []
        self.issue_value_counts = defaultdict(lambda: defaultdict(int))
        self.best_opponent_offer_utility = self.strict_floor
        
        self.my_proposed_offers = set()
        self._is_initialized = True

    def respond(self, state, source=None) -> ResponseType:
        self._init_agent()
        offer = state.current_offer
        
        if offer is None:
            return ResponseType.REJECT_OFFER
            
        self._update_opponent_model(offer)
        my_utility_for_offer = self.my_utilities.get(offer, float(self.ufun(offer)))
        progress = state.relative_time
        
        if my_utility_for_offer > self.best_opponent_offer_utility:
            self.best_opponent_offer_utility = my_utility_for_offer
        
        target_utility = self._bidding_strategy(progress)
        
        if my_utility_for_offer >= target_utility:
            return ResponseType.ACCEPT_OFFER

        # 即使在末期恐慌，也绝对不接受低于钢铁底线的条件
        if progress > 0.98 and my_utility_for_offer >= max(self.strict_floor, self.best_opponent_offer_utility - 0.05):
            return ResponseType.ACCEPT_OFFER
            
        return ResponseType.REJECT_OFFER

    def propose(self, state, dest=None) -> Outcome:
        self._init_agent()
        progress = state.relative_time
        target_utility = self._bidding_strategy(progress)
        return self._generate_offer_with_om(target_utility)

    def _update_opponent_model(self, offer: Outcome):
        self.opponent_bid_history.append(offer)
        for issue_idx, val in enumerate(offer):
            self.issue_value_counts[issue_idx][val] += 1

    def _bidding_strategy(self, progress: float) -> float:
        beta = 2.5  
        # 使用 strict_floor 计算衰减，确保 target_utility 永远不会跌穿地心
        base_target = 1.0 - (1.0 - self.strict_floor) * (progress ** beta)
        return max(base_target, self.best_opponent_offer_utility, self.strict_floor)

    def _generate_offer_with_om(self, target_utility: float) -> Outcome:
        # 只有真正满足钢铁底线的，才是 valid 的
        valid_outcomes = [o for o in self.sorted_outcomes 
                          if self.my_utilities[o] >= target_utility and o not in self.my_proposed_offers]
                
        if not valid_outcomes:
            valid_outcomes = [o for o in self.sorted_outcomes if self.my_utilities[o] >= target_utility]
            if not valid_outcomes:
                fallback = [o for o in self.sorted_outcomes if self.my_utilities[o] >= self.strict_floor]
                valid_outcomes = [fallback[-1] if fallback else self.sorted_outcomes[0]]

        if len(self.opponent_bid_history) < 5:
            top_k = min(5, len(valid_outcomes))
            best_outcome = random.choice(valid_outcomes[:top_k])
            self.my_proposed_offers.add(best_outcome)
            return best_outcome

        best_outcome_for_opponent = valid_outcomes[0]
        max_opponent_score = -1

        for outcome in valid_outcomes:
            opponent_score = sum(self.issue_value_counts[i][val] for i, val in enumerate(outcome))
            if opponent_score > max_opponent_score:
                max_opponent_score = opponent_score
                best_outcome_for_opponent = outcome

        self.my_proposed_offers.add(best_outcome_for_opponent)
        return best_outcome_for_opponent