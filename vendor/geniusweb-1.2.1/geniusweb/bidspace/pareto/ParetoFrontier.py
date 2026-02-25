from typing import List, Set
from geniusweb.profile.Profile import Profile
from abc import ABC, abstractmethod
from geniusweb.issuevalue.Bid import Bid

class ParetoFrontier (ABC):
	'''
	The pareto frontier is the set of {@link Bid}s for which there is no other
	bid that is similar or better for the involved profiles.
	'''

	@abstractmethod
	def getProfiles(self) -> List[Profile] :
		'''
		@return the profiles that form the basis of this pareto frontier.
		'''

	@abstractmethod
	def getPoints(self) -> Set[Bid] :
		'''
		@return the set of all {@link Bid}s that are on the pareto frontier.
		'''

