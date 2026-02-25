from abc import abstractmethod
from typing import List, Optional

from geniusweb.actions.Action import Action
from geniusweb.inform.Agreements import Agreements
from geniusweb.progress.Progress import Progress
from geniusweb.protocol.NegoState import NegoState
from geniusweb.protocol.session.SessionResult import SessionResult
from geniusweb.protocol.session.SessionSettings import SessionSettings


class SessionState(NegoState):
	'''
	The current state of the session. E.g. typically contains the actions so far
	and the parties currently connected. <br>
	The state checks if transitions (Actions from the party) are following the
	protocol, and thus implement most of the protocol . <br>
	
	If protocol errors occur, these should be stored in the state and the state
	should become {@link #isFinal(long)}. Throwing should happen only in case of
	a bug.<br>
	
	Implementations should be immutable (to ensure thread safety, testability
	etc).
	
	States must be serializable so that listeners can follow what is going on in
	the protocol. As uaual, mark non-serializable fields as transient.
	'''

	@abstractmethod
	def getSettings(self) -> SessionSettings:
		'''
		@return the SessionSettings
		'''
	
	@abstractmethod
	def getActions(self) -> List[Action]: 
		'''
		@return unmodifyable list of actions done so far, in the order in which
		they arrived. List of list allows implementations to add some
		extra structure to the actions, eg one list per phase
		'''
	
	@abstractmethod
	def getProgress(self) -> Optional[Progress]:
		'''
		@return the progress of the session. Can return null if the session did
		        not even start yet. Notice that the protocol determines when a
		        session officially starts (eg, in SAOP it starts after all
		        parties were connected succesfully).
		'''
	
	@abstractmethod
	def getAgreements(self) -> Agreements:
		'''
		@return the current standing agreements
		    An agreement does not necessarily mean {@link #isFinal(long)}.
		'''
	
