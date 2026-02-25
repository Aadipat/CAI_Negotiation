from geniusweb.references.PartyWithParameters import PartyWithParameters
from geniusweb.references.ProfileRef import ProfileRef


class PartyWithProfile:

	def __init__(self,   party:PartyWithParameters, profile:ProfileRef ) :
		if party == None or profile == None:
			raise ValueError("party and profile must be not None")

		self._party = party
		self._profile = profile

	def getParty(self)->PartyWithParameters :
		'''
		@return the {@link PartyWithParameters}. never null.
		'''
		return self._party

	def getProfile(self)-> ProfileRef:
		'''
		@return the profile setting for this party. Never null.
		'''
		return self._profile

	def __hash__(self):
		'''
		support for using this in dict etc
		'''
		return hash((self._party, self._profile))

	def __repr__(self)->str:
		return "PartyWithProfile[" + str(self._party) + "," + str(self._profile) + "]"

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			self._party==other._party and self._profile==other._profile
