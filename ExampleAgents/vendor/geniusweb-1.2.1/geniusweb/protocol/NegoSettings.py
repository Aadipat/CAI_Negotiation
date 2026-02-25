from abc import ABC, abstractmethod

from pyson.JsonSubTypes import JsonSubTypes
from pyson.JsonTypeInfo import JsonTypeInfo, As, Id
from tudelft_utilities_logging.Reporter import Reporter

from geniusweb.protocol.NegoProtocol import NegoProtocol


@JsonSubTypes( ["geniusweb.protocol.session.saop.SAOPSettings.SAOPSettings",
			"geniusweb.protocol.session.mopac.MOPACSettings.MOPACSettings",
			"geniusweb.protocol.session.learn.LearnSettings.LearnSettings" ])
@JsonTypeInfo(use = Id.NAME, include = As.WRAPPER_OBJECT)
class NegoSettings(ABC):
	'''
	Interface for negotiation settings. A negotiation can be either a single
	session or a tournament
	'''
	@abstractmethod
	def getMaxRunTime(self) -> float:
		'''
		@return the maximum run time (seconds). In deterministic runs this can be
		        an exact number (#sessions * runtime per session) but this
		        interface also allows more random tournament protocols. The
		        protocol should stick closely with the maximum it provides to
		        enable planning of tournaments properly.
		'''

	@abstractmethod
	def getProtocol(self,  logger:Reporter)->NegoProtocol :
		'''
		@param logger the logger where the protocol can log events to.
		@return an initialized and ready to use {@link NegoProtocol} that can
		        handle this Negotiation.
		'''
