from decimal import Decimal
from typing import List, Dict

from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Value import Value
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive


class ParetoPoint:
	'''
	A Paretopoint is a Bid together with an N-dimensional utility vector. This is
	also a caching mechanism to avoid repeated utility computation of good bids.
	This is a internal utility class to streamline pareto computations.
	'''

	def __init__(self, utils:List[Decimal] , bid:Bid):
		'''
		@param bid    a (possibly partial) {@link Bid}
		@param utils the utilities of the bid in all spaces, in order
		'''
		self._bid = bid;
		self._utilities = list(utils)

	@staticmethod
	def create(bid:Bid , spaces:List[LinearAdditive]) -> "ParetoPoint":
		'''
		@param bid    a (possibly partial) {@link Bid}
		@param spaces the {@link LinearAdditive}s to consider
		'''
		utilities:List[Decimal] = []
		for space in spaces:
			utilities.append(space.getUtility(bid))
		return ParetoPoint(utilities, bid)

	def merge(self, otherpoint:"ParetoPoint") -> "ParetoPoint":
		'''
		Merges the issues from both bids and adds the utilities. This only works
		correctly if the issues in other point are completely disjoint from our
		bid issues.
		
		@param otherpoint with the utils summed and the issue values merged
		'''
		summedutils:List[Decimal] = []
		for n in range(len(self._utilities)):
			summedutils.append(self._utilities[n] + otherpoint._utilities[n])

		return ParetoPoint(summedutils, self._bid.merge(otherpoint.getBid()))

	def isDominatedBy(self, other:"ParetoPoint") -> bool:
		'''
		@param other
		@return true if this ParetoPoint is dominated by the other. That means
		        other has better or equal utilities in ALL dimensions.
		'''
		otherutils:List[Decimal] = other.getUtilities()
		for i  in range(len(self._utilities)):
			if otherutils[i] < self._utilities[i]:
				return False
		return True

	def getUtilities(self) -> List[Decimal]:
		return self._utilities

	def getBid(self) -> Bid:
		return self._bid
