from pyson.JsonGetter import JsonGetter
from pyson.JsonValue import JsonValue
from uri.uri import URI  # type: ignore

from geniusweb.references.Reference import Reference


class ProfileRef (Reference):
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
		# EXTRA: we check that the URI is not completely empty. 
		# This to get similar behaviour as Java
		if uri == None or (uri.getHost() == None and uri.getPath() == None):
			raise ValueError("profile=null")
		self._profile = uri
	
	@JsonValue()
	def getURI(self) -> URI:
		return self._profile

	def __repr__(self):
		return "ProfileRef[" + str(self._profile) + "]"

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			self._profile == other._profile

	def __hash__(self):
		'''
		support for using this in dict etc
		'''
		return hash(str(self._profile))
