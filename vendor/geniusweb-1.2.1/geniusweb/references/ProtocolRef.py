from pyson.JsonGetter import JsonGetter
from pyson.JsonValue import JsonValue
from uri.uri import URI # type: ignore

from geniusweb.references.Reference import Reference


class ProtocolRef (Reference):
	'''
	A URI reference to get a copy of a profile. This usually is a "ws://"
	(websocket) URI, allowing users (parties) to get notifications if the profile
	is changed.
	<p>
	In debugging scenarios, this is usually a "file://" URI, in which case the
	profile is assumed to be static during the run. Parties that support
	debugging eg with the simplerunner should support the file: protocol.
	'''

	def __init__(self, uri:URI):
		assert isinstance(uri, URI)
		self._protocol = uri
	
	@JsonValue()
	def getURI(self) -> URI :
		return self._protocol

	def __repr__(self):
		return "ProtocolRef[" + str(self._protocol) + "]"

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			self._protocol==other._protocol

	def __hash__(self):
		return hash(str(self._protocol))
