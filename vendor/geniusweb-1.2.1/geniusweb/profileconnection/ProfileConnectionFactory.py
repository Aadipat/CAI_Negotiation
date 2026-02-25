from tudelft_utilities_logging.Reporter import Reporter
from uri.uri import URI  # type:ignore

from geniusweb.profileconnection.FileProfileConnector import FileProfileConnector
from geniusweb.profileconnection.ProfileInterface import ProfileInterface
from geniusweb.profileconnection.WebSocketContainer import DefaultWebSocketContainer
from geniusweb.profileconnection.WebsocketProfileConnector import WebsocketProfileConnector


class ProfileConnectionFactory:
	'''
	 * factory that provides a ProfileInterface given an URI, supporting both the ws
	 * and the file scheme for the uri
	'''

	@staticmethod
	def create( uri:URI,  reporter:Reporter) -> ProfileInterface:
		'''
		@param uri      the URI that can provide the {@link Profile}. Support
		                both the ws and the file scheme for the uri.
		@param reporter the {@link Reporter} to log issues to
		@return a {@link ProfileInterface}
		@throws IOException         if connection can't be made
		@throws DeploymentException if endpoint can't be published
		'''
		scheme=str(uri.getScheme())
		if "ws"==scheme:
			return WebsocketProfileConnector(uri, reporter,	DefaultWebSocketContainer())
		if "file"==scheme:
			return FileProfileConnector(uri.getPath());
		raise ValueError("Unsupported profile scheme " + str(uri));

