from typing import List, Dict, Set, Optional

from geniusweb.actions.Action import Action
from geniusweb.actions.LearningDone import LearningDone
from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.Agreements import Agreements
from geniusweb.progress.Progress import Progress
from geniusweb.protocol.ProtocolException import ProtocolException
from geniusweb.protocol.session.DefaultSessionState import DefaultSessionState
from geniusweb.protocol.session.SessionResult import SessionResult
from geniusweb.protocol.session.learn.LearnSettings import LearnSettings
from geniusweb.references.PartyWithProfile import PartyWithProfile


class LearnState (DefaultSessionState["LearnState", "LearnSettings"]):
	'''
	Stores the state for Learn protocol. Immutable.
	'''

	def __init__(self, actions:List[Action] , conns:List[PartyId] ,
			progress:Optional[Progress] , settings:LearnSettings ,
			partyprofiles:Dict[PartyId, PartyWithProfile]={},
			e:Optional[ProtocolException]=None):
		'''
		@param actions       the actions done by the parties
		@param conns         the existing party connections. we assume ownership
		            of this so it should not be modified although
		            connections may of course break. If null, default
		            empty list is used. Can be less than 2 parties in
		            the first phases of the setup.
		@param progress      the {@link Progress} line. can be null
		@param settings      the {@link LearnSettings}
		@param partyprofiles map with the {@link PartyWithProfile} for connected
		            parties. 
		@param e    the {@link ProtocolException}, or null if none
		            occurred.
		'''
		
		super().__init__(actions, conns, progress, settings, partyprofiles, e)

# 	def LearnState(LearnSettings settings) {
# 		'''
# 		Creates the initial state from the given settings and progress=null
# 		
# 		@param settings the {@link LearnSettings}
# 		'''
# 		this(Collections.emptyList(), Collections.emptyList(), null, settings,
# 				null, null);
# 
# 	}

	def With(self, actions:List[Action] , conns:List[PartyId],
			progr:Optional[Progress] , settings:LearnSettings,
			partyprofiles:Dict[PartyId, PartyWithProfile] ,
			e:Optional[ProtocolException]) -> "LearnState":
		return LearnState(actions, conns, progr, settings, partyprofiles,
				e)

	def getAgreements(self) -> Agreements:
		return Agreements()

	def getResults(self) -> List[SessionResult]:
		return [SessionResult(self.getPartyProfiles(), self.getAgreements(),
				{}, None)]

	def isFinal(self, currentTimeMs:int) -> bool:
		done = self._getDoneLearning()
		# if done is empty we're probably still starting up.
		return super().isFinal(currentTimeMs)\
				or (len(done) != 0 and set(self.getConnections()).issubset(done))

	def WithException(self, e:ProtocolException) -> "LearnState":
		'''
		@param e the error that occured
		@return a new state with the error set.
		'''
		return LearnState(self.getActions(), self.getConnections(), self.getProgress(),
				self.getSettings(), self.getPartyProfiles(), e)

	def checkAction(self, actor:PartyId , action:Action) -> Optional[str]:
		'''
		@param actor  the known real actor that did this action
		@param action an {@link Action}
		@return null if action seems ok, or message explaining why not.
		'''
		msg = super().checkAction(actor, action)
		if msg != None:
			return msg
		if actor in self._getDoneLearning():
			return "actor already was done learning"
		if not isinstance(action, LearningDone):
			return "Action " + str(action) + " is not allowed"
		return None

	def _getDoneLearning(self) -> Set[PartyId]:
		'''
		@return set of parties that reported they are done with learning.
		'''
		return set([party.getActor() for party in self.getActions()  ])
	
