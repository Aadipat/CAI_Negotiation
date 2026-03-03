from __future__ import annotations

from collections import defaultdict
from random import choice

from negmas import (
	PreferencesChangeType,
	PresortingInverseUtilityFunction,
	ResponseType,
	SAONegotiator,
)


class Group56_Negotiator(SAONegotiator):
	"""
	Bilateral SAOP negotiator with three core components:

	1) A time-based concession policy that starts firm and concedes near deadline.
	2) A reservation-aware acceptance policy.
	3) A lightweight opponent model from observed offer frequencies.

	The design intentionally keeps all computations bounded and simple to satisfy
	strict ANAC-style time constraints while still adapting to opponent behavior.
	"""

	_inv = None
	_best_outcome = None
	_min_utility = None
	_max_utility = None
	_reservation = None

	def __init__(self, *args, **kwargs):
		"""Initialize runtime state and opponent-model containers."""
		super().__init__(*args, **kwargs)
		self._offer_history: list[tuple | None] = []
		self._opponent_value_counts: dict[int, dict[object, int]] = defaultdict(
			lambda: defaultdict(int)
		)
		self._opponent_first_utility: float | None = None
		self._opponent_last_utility: float | None = None

	def on_preferences_changed(self, changes):
		"""
		Build utility inversion helpers and reset model state when preferences change.

		This method prepares fast outcome retrieval for utility intervals and caches
		utility extremes needed by both `propose` and `respond`.
		"""
		changes = [_ for _ in changes if _.type not in (PreferencesChangeType.Scale,)]
		if not changes:
			return

		self._inv = PresortingInverseUtilityFunction(self.ufun)
		self._inv.init()

		worst_outcome, self._best_outcome = self.ufun.extreme_outcomes()
		self._min_utility = float(self.ufun(worst_outcome))
		self._max_utility = float(self.ufun(self._best_outcome))

		reserved = getattr(self.ufun, "reserved_value", None)
		self._reservation = float(reserved) if reserved is not None else self._min_utility

		self._offer_history = []
		self._opponent_value_counts = defaultdict(lambda: defaultdict(int))
		self._opponent_first_utility = None
		self._opponent_last_utility = None
		super().on_preferences_changed(changes)

	def _time_target_utility(self, relative_time: float) -> float:
		"""
		Compute aspiration target utility at time t in [0, 1].

		The base policy is boulware (slow concession), but it adapts based on
		estimated opponent concession measured in our own utility space.
		"""
		t = min(1.0, max(0.0, float(relative_time)))

		# Base exponent > 1.0 yields boulware behavior.
		exponent = 2.2

		if self._opponent_first_utility is not None and self._opponent_last_utility is not None:
			observed_concession = self._opponent_last_utility - self._opponent_first_utility
			if observed_concession > 0.15:
				exponent = 2.8
			elif observed_concession < 0.05:
				exponent = 1.6

		aspiration = self._reservation + (self._max_utility - self._reservation) * (
			1.0 - (t**exponent)
		)

		if t > 0.97:
			aspiration = max(self._reservation, aspiration - 0.03)

		return min(self._max_utility, max(self._reservation, aspiration))

	def _update_opponent_model(self, offer: tuple | None):
		"""
		Update lightweight opponent statistics from the received offer.

		We store per-issue value frequencies and track concession trend using the
		utilities of opponent offers measured by our utility function.
		"""
		if offer is None:
			return
		self._offer_history.append(offer)

		for issue_index, value in enumerate(offer):
			self._opponent_value_counts[issue_index][value] += 1

		utility = float(self.ufun(offer))
		if self._opponent_first_utility is None:
			self._opponent_first_utility = utility
		self._opponent_last_utility = utility

	def _opponent_score(self, outcome: tuple | None) -> float:
		"""
		Estimate opponent preference by value-frequency matching.

		Higher score means the outcome uses values that appeared more frequently in
		opponent offers and is therefore more likely to be acceptable to them.
		"""
		if outcome is None:
			return float("-inf")
		if not self._offer_history:
			return 0.0

		score = 0.0
		for issue_index, value in enumerate(outcome):
			score += float(self._opponent_value_counts[issue_index].get(value, 0))
		return score

	def respond(self, state, source: str | None = None):
		"""
		Accept when offer utility meets current target or dominates next planned bid.

		This acceptance rule balances self-interest with deadline pressure while
		respecting reservation value constraints.
		"""
		offer = state.current_offer
		if offer is None:
			return ResponseType.REJECT_OFFER

		self._update_opponent_model(offer)

		offered_utility = float(self.ufun(offer))
		target_utility = self._time_target_utility(state.relative_time)

		if offered_utility >= target_utility:
			return ResponseType.ACCEPT_OFFER

		planned = self.propose(state)
		if planned is not None and offered_utility >= float(self.ufun(planned)):
			return ResponseType.ACCEPT_OFFER

		if state.relative_time >= 0.995 and offered_utility >= self._reservation:
			return ResponseType.ACCEPT_OFFER

		return ResponseType.REJECT_OFFER

	def propose(self, state, dest: str | None = None):
		"""
		Generate the next offer from outcomes above target utility.

		We select offers near current aspiration, then rank them by estimated
		opponent preference so concessions are directed toward likely agreement.
		"""
		if self._inv is None:
			return self._best_outcome

		target_utility = self._time_target_utility(state.relative_time)
		candidates = self._inv.some((target_utility - 1e-9, self._max_utility + 1e-9), False)

		if not candidates:
			candidates = self._inv.some((self._reservation - 1e-9, self._max_utility + 1e-9), False)
		if not candidates:
			return self._best_outcome

		# Keep the search bounded and deterministic enough for reproducibility.
		if len(candidates) > 300:
			sampled = [candidates[0], candidates[len(candidates) // 2], candidates[-1]]
			sampled.extend(choice(candidates) for _ in range(97))
			candidates = sampled

		best_offer = None
		best_score = float("-inf")
		for outcome in candidates:
			own_u = float(self.ufun(outcome))
			opp_s = self._opponent_score(outcome)
			score = own_u + 0.02 * opp_s
			if score > best_score:
				best_score = score
				best_offer = outcome

		return best_offer if best_offer is not None else self._best_outcome
