from abc import ABC
from typing import List

from pyson.JsonSubTypes import JsonSubTypes
from pyson.JsonTypeInfo import Id, As
from pyson.JsonTypeInfo import JsonTypeInfo

from geniusweb.protocol.NegoSettings import NegoSettings
from geniusweb.protocol.session.SessionResult import SessionResult


@JsonSubTypes([ "geniusweb.protocol.session.saop.SAOPState.SAOPState"])
@JsonTypeInfo(use=Id.NAME, include=As.WRAPPER_OBJECT)
class NegoState (ABC):
	'''
	The current state of the session/tournament. Must be (de)serializabl;e so
	that it can be restarted if a crash occurs. Notice that this restart
	functionality is not yet available.
	<p>
	In general the state contains all the information to control the flow of the
	negotiation: who did what, are we finished, etc. This object may be stored to
	record the final result as well
	'''

	def getSettings(self) -> NegoSettings: 
		'''
		@return the settings that were used to create this Nego
		'''

	def isFinal(self, currentTimeMsLint) -> bool:
		'''
		@param currentTimeMs the current time in ms since 1970, see
		                      {@link System#currentTimeMillis()}
		@return true iff this is the final state. A state can be final because
		        the protocol decided so, eg a deal was achieved, the deadline was
		        reached or someone made a protocol error. If true, no more state
		        changes can occur, including no more protocol errors.
		'''

	def getResults(self) -> List[SessionResult]:
		'''
		@return List of the{@link SessionResult}s. Each SessionResult is a short
		        report of the final outcome. Assumes {@link #isFinal(long)}.
		        result may be undefined if not.
		'''
	
