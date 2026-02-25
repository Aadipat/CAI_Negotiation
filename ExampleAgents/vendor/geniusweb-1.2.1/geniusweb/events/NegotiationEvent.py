from abc import abstractmethod, ABC

from pyson.JsonSubTypes import JsonSubTypes
from pyson.JsonTypeInfo import Id, As
from pyson.JsonTypeInfo import JsonTypeInfo

@JsonSubTypes([ "geniusweb.events.ActionEvent.ActionEvent",
			    "geniusweb.events.SessionStarted.SessionStarted",
			    "geniusweb.events.TournamentStarted.TournamentStarted"])
@JsonTypeInfo(use=Id.NAME, include=As.WRAPPER_OBJECT)
class NegotiationEvent (ABC):
	'''
	 reports some event happened in the negotiation system. Generally, parties are
	 informed about events in the system, but this depends on the protocol.
	 '''
	@abstractmethod
	def getTime(self)->int:
		'''
		@return the time at which the event happened on the server, measured in
		        milliseconds, between the start time and midnight, January 1,
		        1970 UTCas. See also {@link System#currentTimeMillis()}. <br>
		
		        If the event is about an {@link Action} done by a negotiation
		        party on another machine, this time refers to the time the action
		        was handled on the server (which may differ from the clock time
		        on the other machine). <br>
		
		        Note: we do not use RFC 3339 because we need millisecond
		        accuracy.
		'''
