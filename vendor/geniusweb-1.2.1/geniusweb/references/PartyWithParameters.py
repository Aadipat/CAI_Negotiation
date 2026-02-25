from __future__ import annotations
from geniusweb.references.Parameters import Parameters
from geniusweb.references.PartyRef import PartyRef

class PartyWithParameters:
	'''
	Container holding a partyref with parameters
	'''

	def __init__(self, partyref:PartyRef , parameters:Parameters):
		self._partyref = partyref
		self._parameters = parameters

	def getPartyRef(self) -> PartyRef :
		return self._partyref

	def getParameters(self) ->Parameters :
		return self._parameters;


	def With(self, parameters2:Parameters) ->"PartyWithParameters":
		'''
		@param parameters2 the additional parameters
		@return this party but with the given parameters added to our parameters
		'''
		return PartyWithParameters(self._partyref, self._parameters.WithParameters(parameters2));

	def __repr__(self)->str:
		if self._parameters.isEmpty():
			return str(self._partyref)
		return str(self._partyref) + str(self._parameters)

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			self._partyref==other._partyref and self._parameters==other._parameters

	def __hash__(self):
		return hash((self._parameters, self._partyref))
