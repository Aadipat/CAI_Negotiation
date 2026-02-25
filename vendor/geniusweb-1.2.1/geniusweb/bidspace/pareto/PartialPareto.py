from typing import List, Dict

from geniusweb.bidspace.pareto.ParetoPoint import ParetoPoint
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Value import Value
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive


class PartialPareto:
	'''
	 PartialPareto contains a pareto surface of partial bids. Internal-only
	 utility class for computing LinearAdditive pareto surface. Immutable.
	'''

	def __init__(self, points:List[ParetoPoint]):
		'''
		@param points the points to be contained in this PartialPareto
'''
		self._points = points

	@staticmethod
	def create(utilSpaces:List[LinearAdditive] ,
			issues: List[str]) -> "PartialPareto":
		'''
		Constructor. Avoided the standard 'new' constructor as this is
		implemented recursively (O(log(#issues))).
		
		@param utilSpaces the {@link LinearAdditive}s
		@param issues     the issues (subset of all issues in the space) to be
		                  used for this pareto
		@return the pareto surface (non-dominated bids) when considering only the
		        given issues.
		'''

		if len(issues) == 1:
			issue = issues[0]
			map:Dict[str, Value] = {}
			list:List[ParetoPoint] = []
			for value in utilSpaces[0].getDomain().getValues(issue):
				map[issue] = value
				list = PartialPareto._add(list, ParetoPoint.create(Bid(map), utilSpaces))
			return PartialPareto(list)
		else:
			halfway = int(len(issues) / 2)
			return PartialPareto.create(utilSpaces, issues[0: halfway])._merge(
					PartialPareto.create(utilSpaces, issues[halfway:]))

	def getPoints(self) -> List[ParetoPoint]:
		'''
		@return the ParetoPoints on the (possibly partial) Pareto surface
		'''
		return self._points

	def _merge(self, other:"PartialPareto") -> "PartialPareto":
		'''
		This combines two partial paretos. Here is the heart of the algorithm.
		
		@param other another {@link PartialPareto} to be merged with this. The
		             other pareto must be composed with non-overlapping range.
		@return merge of two partial paretos. Checks all partial1*partial2
		        combinations and only non-dominated points are kept.
		'''
		merge:List[ParetoPoint] = []
		for point in  self._points:
			for otherpoint in other._points:
				merge = PartialPareto._add(merge, point.merge(otherpoint))
		return PartialPareto(merge)

	@staticmethod
	def _add(list:List[ParetoPoint], candidate:ParetoPoint) -> List[ParetoPoint]:
		'''
		Add a new ParetoPoint to a list
		
		@param list      the existing list
		@param candidate a new {@link ParetoPoint} candidate
		@return a new list that either ignored the candidate, or added it and
		        removed the old points that are dominated by the candidate
		'''
		for existing in list:
			if candidate.isDominatedBy(existing):
				return list
		# if we get here, candidate is not dominated so we add it
		# and remove existing ones now dominated
		newlist:List[ParetoPoint] = []
		newlist.append(candidate)
		for existing in list:
			if not existing.isDominatedBy(candidate):
				newlist.append(existing)
		return newlist
