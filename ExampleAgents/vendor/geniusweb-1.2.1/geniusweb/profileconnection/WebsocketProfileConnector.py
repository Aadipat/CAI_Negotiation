from builtins import Exception
import json
import logging
from time import sleep 

from pyson.ObjectMapper import ObjectMapper
from tudelft.utilities.listener.DefaultListenable import DefaultListenable
from tudelft_utilities_logging.Reporter import Reporter
from uri.uri import URI  # type:ignore
import websocket  # type:ignore

from geniusweb.profile.Profile import Profile
from geniusweb.profile.Profile import Profile
from geniusweb.profileconnection.ProfileInterface import ProfileInterface
from geniusweb.profileconnection.Session import Session
from geniusweb.profileconnection.WebSocketClient import WebSocketClient
from geniusweb.profileconnection.WebSocketContainer import WebSocketContainer


class WebsocketProfileConnector (DefaultListenable[Profile], ProfileInterface, WebSocketClient):
	
	_pyson:ObjectMapper = ObjectMapper()
	TIMEOUT_MS = 2000
	_profile:Profile = None #type:ignore
	_session=None

	def __init__(self, uri:URI , reporter:Reporter ,  wscontainer:WebSocketContainer):
		'''
		@param uri         the URI that will provide the {@link Profile}
		@param reporter    the {@link Reporter} for logging issues
		@param wscontainer the {@link WebSocketContainer} that can provide new
		                   websockets. Typically ContainerProvider
		                   .getWebSocketContainer()
		@throws DeploymentException if the annotated endpoint instance is not
		                            valid
		@throws IOException         if there was a network or protocol problem
		                            that prevented the client endpoint being
		                            connected to its server.
		'''
		super().__init__()
		if uri == None or reporter == None or wscontainer == None:
			raise ValueError("uri, reporter and wsconnector must be not null")

		self._uri = uri;
		self._logger = reporter;
		self._wscontainer = wscontainer
		# see #1763 expected max size of profiles.
		wscontainer.setDefaultMaxTextMessageBufferSize(200000)
		wscontainer.connectToServer( uri, self) 

	def onOpen(self, session:Session):
		self._session=session	
		self._logger.log(logging.INFO, "Connected: " + str(session))

	def onClose(self):
		if self._session :
			self._logger.log(logging.INFO,"Closed websocket: " + str(self._session))
			self._session = None

	def onMessage(self, message:str):
		try:
			# this will be called every time the profile changes.
			self._logger.log(logging.INFO, "Received profile: " + message);
			profile:Profile = self._pyson.parse(json.loads(message), Profile) #type:ignore
			self._profile = profile;
			self.notifyListeners(profile);
		except Exception as e:
			self._logger.log(logging.CRITICAL,
				"Something went wrong while processing message "+repr(message), e)
			

	def onError(self, e: BaseException):
		self._logger.log(logging.CRITICAL,
				"Something went wrong while processing downloaded profile "+repr(self._uri), e)

	#Override
	def getProfile(self) ->Profile  :
		remaining_wait = self.TIMEOUT_MS;
		while self._profile == None and remaining_wait > 0:
			remaining_wait -= 100
			sleep(0.1)
		if self._profile == None:
			raise IOError("Server is not responding. failed to fetch profile from " + str(self._uri))
	
		return self._profile
	
	def  close(self):
		if self._session != None:
			self._session.close()
