from typing import List, Set, Optional

from geniusweb import profile
from geniusweb.bidspace.pareto.ParetoFrontier import ParetoFrontier
from geniusweb.bidspace.pareto.PartialPareto import PartialPareto
from geniusweb.issuevalue.Bid import Bid
from geniusweb.profile.Profile import Profile
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive


class ParetoLinearAdditive(ParetoFrontier):
	'''
	pareto frontier implementation for {@link LinearAdditive}. This is a highly
	optimized pareto method for {@link LinearAdditive} spaces
	'''
	
	def __init__(self, utilSpaces:List[LinearAdditive]):
		'''
		@param utilSpaces. Must contain at least two {@link LinearAdditive}s and
		                   all must be defined on the same donain.
		'''
		if utilSpaces == None or len(utilSpaces) < 2:
			raise ValueError("utilSpaces must contain at least 2 spaces")

		domain = utilSpaces[0].getDomain()
		for space in utilSpaces:
			if not space.getDomain() == domain:
				raise ValueError(
					"Expected all spaces using domain " + domain.getName()
								+" but found " + space.getDomain().getName());
		self._utilSpaces = utilSpaces
		self._points:Optional[Set[Bid] ] = None

	# Override
	def getProfiles(self) -> List[Profile]:
		return list(self._utilSpaces)

	# Override
	def getPoints(self) -> Set[Bid]:
		if self._points == None:
			self._points = self._computePareto()
		return self._points  # type:ignore

	# Override
	def toString(self) -> str:
		return "Pareto " + str(self.getPoints())

	def _computePareto(self) -> Set[Bid]:
		issues:List[str] = list(self._utilSpaces[0].getDomain().getIssues())
		partial = PartialPareto.create(self._utilSpaces, issues)
		return set([ point.getBid() for point in partial.getPoints() ])
