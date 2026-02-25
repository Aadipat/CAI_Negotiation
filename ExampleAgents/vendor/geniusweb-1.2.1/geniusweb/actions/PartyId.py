import re
from pyson.JsonValue import JsonValue

class PartyId:
	'''
	Unique ID of a party in a negotiation. The name should start with a short
	string indicating the party (eg, the party name plus some machine
	identifier), optionally followed by an "_", and more characters to make the
	partyid unique. We require the name and "-" so that the string up to the
	first "-" can be used to determine between sessions which opponents are
	instances of the same class.
	<h2>Note</h2> Normally, negotiation parties should not create new Party IDs
	as all needed IDs should be provided by the protocol.
	'''
	

	def __init__(self,name:str):
		'''
		 @param name a simple name, starting with letter, followed by zero or more
		             letters, digits or _.

		'''
		if name == None or not re.fullmatch("[a-zA-Z]\\w*", name):
			raise ValueError("name '" + name
					+ "' is not a letter followed by zero or more word characters (letter, digit or _)");
		self._name = name;

	@JsonValue()
	def getName(self) -> str:
		return self._name

	def __repr__(self):
		return self._name

	
	def __eq__(self, other):
		return super().__eq__(other) and isinstance(other, self.__class__) and \
			self._name==other._name

	def __hash__(self):
		'''
		support for using this in dict etc
		'''
		return hash(self._name)
