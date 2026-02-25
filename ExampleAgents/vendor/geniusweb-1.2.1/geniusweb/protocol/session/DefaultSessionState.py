from __future__ import annotations
from abc import abstractmethod
from typing import List, Dict, Optional, TypeVar, Generic

from geniusweb.actions.Action import Action
from geniusweb.actions.PartyId import PartyId
from geniusweb.progress.Progress import Progress
from geniusweb.protocol.ProtocolException import ProtocolException
from geniusweb.protocol.session.SessionSettings import SessionSettings
from geniusweb.protocol.session.SessionState import SessionState
from geniusweb.references.PartyWithProfile import PartyWithProfile
from geniusweb.utils import toTuple, val

S = TypeVar('S', bound=SessionSettings)   
P = TypeVar('P', bound="DefaultSessionState")


class DefaultSessionState (SessionState, Generic[P, S]):
	'''
	The default current state of the session. immutable.
	
	@param <P> the actual SessionState object
	@param <S> the actual SessionSettings object
	'''

	# 	error: Optional[ProtocolException]
	# 	progress: Progress
	# 	partyprofiles: Optional[Dict[PartyId, PartyWithProfile]]
	# 	settings: S

	def __init__(self, actions:List[Action], connections:List[PartyId],
			progress:Optional[Progress], settings:S,
			partyprofiles:Optional[Dict[PartyId, PartyWithProfile]]=None,
			error:Optional[ProtocolException]=None):
		'''
		@param actions       value for actions done so far. None equals to empty
		                     list
		@param conns         the currently existing connections. Can be empty. If
		                     None it is assumed to be empty. Each connection
		                     represents another party. Normally there is exactly
		                     1 connection for every party. The protocol should
		                     check this.
		@param progr         the {@link Progress} that governs this session. Can
		                     be null if session did not yet start.
		@param settings      the settings used for the session
		@param partyprofiles map with the {@link PartyWithProfile} for connected
		                     parties. None is equivalent to an empty map.
		@param e             the exception that occured, usually None. All errors
		                     occuring due to faulty {@link Action}s translate to
		                     {@link ProtocolException}s. All errors in our own
		                     code are bugs (not ProtocolExceptions) and should
		                     result in a throw and terminate the session.
		'''

		self._partyprofiles = dict(partyprofiles) if partyprofiles else {}		

		self._connections = list(connections) if connections else []

		self._actions = list(actions) if actions else []

		if len(self._connections) != len(set(self._connections)):
			raise ValueError("There can not be multiple connections for a party:"
							+str(self._connections))

		if not settings:
			raise ValueError("Settings must be not null");
		self._progress = progress;
		self._settings = settings;
		self._error = error;

	@abstractmethod
	def With(self, actions1:List[Action] , conns:List[PartyId],
			progress1:Optional[Progress] , settings1:S,
			partyprofiles1:Dict[PartyId, PartyWithProfile] , e: Optional[ProtocolException]) -> P:
		'''
		Construct a new session state, where the DefaultSessionState changes
		while the rest of the state remains unchanged. Notice the return type P.
		
		@param actions1       the new {@link Action}s
		@param conns          the new connected {@link PartyId}s
		@param progress1      the new {@link Progress}, can be None still
		@param settings1      the new {@link SessionSettings}. Normally this is
		                      constant during a session.
		@param partyprofiles1 the new {@link PartyWithProfile}s for all parties.
		                      Normally this remains constant during a session.
		@param e              an error that occured that caused the session to
		                      reach its terminated/final state. If an error does
		                      not cause termination, only a warning should be
		                      logged.
		@return the new state of the derived sessionstate.
		'''

	def getConnections(self) -> List[PartyId]:
		'''
		@return existing connections.
		'''
		return list(self._connections)

	def getPartyProfiles(self) -> Dict[PartyId, PartyWithProfile]:
		'''
		@return map with {@link PartyWithProfile} for the parties. May be an
        incomplete map, as more parties with their profiles may be set
        only later.
		'''
		return dict(self._partyprofiles)

	def getActions(self) -> List[Action]:
		'''
		@return unmodifyable list of actions done so far.
		'''
		return list(self._actions)

	def getProgress(self) -> Optional[Progress]:
		return self._progress

	def getSettings(self) -> S:
		return self._settings

	def isFinal(self, currentTimeMs:int) -> bool:
		return self._error != None or \
			(self._progress != None and self._progress.isPastDeadline(currentTimeMs))  # type:ignore

	def getError(self) -> Optional[ProtocolException]:
		'''
		@return an error that occured that caused the session to
              reach its terminated/final state. If an error does
              not cause termination, only a warning should be
              logged. None if no error occured.
		'''
		return self._error

	def WithDeadlineReached(self) -> P:
		return self.With(self._actions, self._connections, val(self._progress), self._settings,
				self._partyprofiles, self._error) 

	def WithoutParty(self, party:PartyId) -> P:
		assert isinstance(party, PartyId)
		newconn = list(self._connections)
		newconn.remove(party);
		return self.With(self._actions, newconn, val(self._progress), \
				self._settings, self._partyprofiles, self._error)

	def WithException(self, e:ProtocolException) -> P:
		'''
		@param e the error that occured
		@return a new state with the error set/updated.
		'''
		assert isinstance(e, ProtocolException)
		return self.With(self._actions, self._connections, self._progress,
						self._settings, self._partyprofiles, e)

	def WithParty(self, connection:PartyId, partyprofile:PartyWithProfile) -> P:
		assert isinstance(connection, PartyId)
		assert isinstance(partyprofile, PartyWithProfile)
		newconns = list(self.getConnections())
		newconns.append(connection)
		newprofiles = dict(self.getPartyProfiles())
		newprofiles[connection] = partyprofile
		return self.With(self.getActions(), newconns, self._progress, self.getSettings(),
				newprofiles, None)

	def WithProgress(self, newprogress:Progress) -> P:
		'''
		Sets the new progress for this session.
		
		@param newprogress the new progress
		@return new SAOPState with the progress set to new value
		'''
		assert isinstance(newprogress, Progress)
		if not newprogress:
			raise ValueError("newprogress must be not null");
		return self.With(self._actions, self._connections, newprogress, self._settings,
						self._partyprofiles, self._error)

	def WithAction(self, actor:PartyId , action:Action) -> P:
		'''
		@param actor  the actor that did this action. Can be used to check if
		              action is valid. NOTICE caller has to make sure the current
		              state is not final.
		@param action the action that was proposed by actor.
		@return new SAOPState with the action added as last action.
		'''
		msg = self.checkAction(actor, action)
		if msg:
			raise ValueError(msg)

		newactions = list(self.getActions())
		newactions.append(action)
		return self.With(newactions, self._connections, val(self._progress),
				self._settings, self._partyprofiles, self._error)

	def checkAction(self, actor:PartyId , action:Action) -> Optional[str]:
		'''
		@param actor  the known real actor that did this action
		@param action an {@link Action}
		@return null if action seems ok, or message explaining why not.
		'''
		if not actor:
			return "actor must not be null"
		if not action:
			return "action is null"
		if actor != action.getActor():
			return "act contains wrong credentials: " + str(action)
		return None

	def __repr__(self) -> str:
		return type(self).__name__ + "[" + str(self._actions) + ","\
				+str(self._connections) + "," + str(self._progress) + "," + \
				str(self._settings) + "," + str(self._error);

	def __hash__(self):
		return hash((tuple(self._actions), tuple(self._connections),
					toTuple(self._partyprofiles),
					self._progress, self._settings, self._error))

	def __eq__(self, other) -> bool:
		return isinstance(other, self.__class__) and \
			self._partyprofiles == other._partyprofiles and \
			self._actions == other._actions and \
			self._connections == other._connections and \
			self._progress == other._progress and \
			self._settings == other._settings and \
			self._error == other._error

