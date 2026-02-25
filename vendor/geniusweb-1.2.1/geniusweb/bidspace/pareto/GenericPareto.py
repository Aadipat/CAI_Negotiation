import threading
from typing import List, Set, Optional

from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.bidspace.pareto.ParetoFrontier import ParetoFrontier
from geniusweb.issuevalue.Bid import Bid
from geniusweb.profile.PartialOrdering import PartialOrdering
from geniusweb.profile.Profile import Profile
from geniusweb.utils import val


class GenericPareto(ParetoFrontier):
	'''
	A set of all pareto points associated with a set of profiles. Generally
	applicable but slow.
	'''

	def __init__(self, profiles:List[PartialOrdering]):
		'''
		Constructs pareto from a general {@link PartialOrdering}. This is a
		brute-force algorithm that will inspect (but not store) ALL bids in the
		space, and therefore may be inapproproate depending on the size of your
		domain. Complexity O( |bidspace|^2 |profiles| )
		
		@param profiles a set of at least 2 {@link PartialOrdering}s. All must be
		                defined on the same domain.
		'''
		if len(profiles) < 2:
			raise ValueError("at least 2 profiles are needed")
		
		if None in profiles:
			raise ValueError("Profiles must not be None")
		domain = profiles[0].getDomain()
		for profile in profiles:
			if not domain == profile.getDomain():
				raise ValueError(
						"All profiles must be on same domain ("
								+domain.getName() + ") but found " + str(profile));
		self._profiles = list(profiles)
		self._paretobids:Optional[Set[Bid]] = None
		self._lock = threading.Lock()

	# Override
	def getProfiles(self) -> List[Profile]:
		return list(self._profiles)

	# Override
	def getPoints(self) -> Set[Bid]:
		with self._lock:
			if self._paretobids == None:
				self._computePareto()
			return set(val(self._paretobids))

	# Override
	def __repr__(self):
		return "Pareto " + str(self.getPoints())

	def _computePareto(self):
		'''
		assigns {@link #paretobids}.
		'''
		self._paretobids:Set[Bid] = set()

		for newbid in AllBidsList(self._profiles[0].getDomain()):
			'''
			invariant: paretobids contains bids not dominated by other bids
			in paretobids. That means we need (1) check if new bid is
			dominated (2) if existing bids are dominated if we add a new bid
			 '''
			newBidIsDominated = any(self._isDominatedBy(newbid, paretobid) 
								for paretobid in self._paretobids)

			# if new bid is not dominated, we add it and we re-check existing
			# if they are now dominated
			if not newBidIsDominated:
				self._paretobids = {paretobid for paretobid in self._paretobids
					if not self._isDominatedBy(paretobid, newbid)}
				self._paretobids.add(newbid)

	def _isDominatedBy(self, bid1:Bid , dominantbid: Bid) -> bool:
		'''
		@param bid1        the bid to check
		@param dominantbid the bid that is supposed to dominate bid1
		@return true iff bid1 is dominated by dominant bid. "Dominated by" means
		        that the bid is preferred or equal in all profiles.
		'''
		return all(profile.isPreferredOrEqual(dominantbid, bid1)
				for profile in self._profiles)
