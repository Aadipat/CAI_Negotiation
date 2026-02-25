from pyson.JsonValue import JsonValue
from uri.uri import URI

from geniusweb import party
from geniusweb.references.Reference import Reference


class PartyRef (Reference):
	'''
	A URI reference to create a new instance of a party on a party factory
	server. These are used to describe sesion and tournament settings.
	'''

	def __init__(self, party:URI):
		# EXTRA: we check that the URI is not completely empty. 
		# This to get similar behaviour as Java
		if not isinstance(party, URI) or (party.getHost() == None and party.getPath() == None):
			raise ValueError("expected URI, but got " + repr(party))
		self._party = party

	@JsonValue()
	def getURI(self) -> URI:
		return self._party;

	def __repr__(self) -> str:
		return "PartyRef[" + str(self._party) + "]"

	def __eq__(self, other):
		return isinstance(other, self.__class__) and self._party == other._party

	def __hash__(self):
		return hash(self._party)
