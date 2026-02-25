from typing import List
from geniusweb.references.PartyWithParameters import PartyWithParameters
class Team:
	'''
	A team is a group of parties, each with their own parameters. Each will be
	coupled to a {@link ProfileList} in the generation phase of the protocol
	'''
	def __init__(self, parties: List[PartyWithParameters]):
		'''
		@param ps a list of {@link PartyWithParameters}. Each party is always
		          associated with the given parameters. The order of them is
		          important as it will be matched with the order in the
		          {@link ProfileList}.
		'''
		self._parties = list(parties)

	def	getParties(self) -> List[PartyWithParameters] :
		'''
		@return list of all team {@link PartyWithParameters}.
		'''
		return list(self._parties)

	def __hash__(self):
		return hash(tuple(self._parties))


	def __eq__(self, other):
		return isinstance(other, self.__class__) and  self._parties == other._parties

	def __repr__(self):
		return repr(self._parties)

