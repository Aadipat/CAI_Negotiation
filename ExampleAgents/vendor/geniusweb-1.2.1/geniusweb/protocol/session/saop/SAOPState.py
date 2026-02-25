from __future__ import annotations

from typing import List, Dict, Optional, TYPE_CHECKING

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.EndNegotiation import EndNegotiation
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.Agreements import Agreements
from geniusweb.issuevalue.Bid import Bid
from geniusweb.progress.Progress import Progress
from geniusweb.progress.ProgressRounds import ProgressRounds
from geniusweb.protocol.ProtocolException import ProtocolException
from geniusweb.protocol.session.DefaultSessionState import DefaultSessionState
from geniusweb.protocol.session.SessionResult import SessionResult
from geniusweb.protocol.session.saop.SAOPSettings import SAOPSettings
from geniusweb.references.PartyWithProfile import PartyWithProfile


class SAOPState (DefaultSessionState[ "SAOPState", "SAOPSettings"]): 
	'''
	Immutable.
	'''

	def __init__(self, actions:List[Action] , connections:List[PartyId] ,
			progress:Optional[Progress] , settings: SAOPSettings ,
			partyprofiles:Dict[PartyId, PartyWithProfile]={},
			error:Optional[ProtocolException]=None):
		'''
		
		@param actions       the actions done by the parties
		@param conns         the existing party connections. If null, default
		                     empty list is used. Can be less than 2 parties in
		                     the first phases of the setup or after parties
		                     disconnected.
		@param progress      the {@link Progress} line. can be null
		@param settings      the {@link SAOPSettings}
		@param partyprofiles map with the {@link PartyWithProfile} for connected
		                     parties. null is equivalent to an empty map.
		@param e             the {@link ProtocolException}, or null if none
		                     occurred.
		'''
		super().__init__(actions, connections, progress, settings, partyprofiles, error) 

	def With(self, actions:List[Action] , conns: List[PartyId],
			progr:Optional[Progress] , settings: SAOPSettings,
			partyprofiles:Dict[PartyId, PartyWithProfile] , e:Optional[ProtocolException]) -> "SAOPState":
		assert isinstance(actions, list)
		# assert isinstance(settings, SAOPSettings)
		assert isinstance(partyprofiles, dict)
		return SAOPState(actions, conns, progr, settings, partyprofiles, e);

	def getAgreements(self) -> Agreements:
		agree = Agreements()
		acts = self.getActions()
		nparticipants = len(self.getConnections())
		if nparticipants < 2 or len(acts) < nparticipants:
			return agree;
		offer = acts[len(acts) - nparticipants]
		if not isinstance(offer, Offer):
			return agree;
		bid = offer.getBid()

		# check that the last n-1 are accepts.
		allaccept = all([ (isinstance(act, Accept) and bid == act.getBid())\
					for act in acts[-(nparticipants - 1):]])
		if allaccept:
			agree = Agreements({party: bid for party in  self._getParties()})
		return agree

	def _getParties(self) -> List[PartyId]:
		'''
		@return all currently connected parties.
		'''
		return self.getConnections()

	def isFinal(self, currentTimeMs:int) -> bool:
		acts = self.getActions()
		return super().isFinal(currentTimeMs) \
				or self.getAgreements().getMap() != {} \
				or (not acts == [] and isinstance(acts[-1], EndNegotiation))

	def WithAction(self, actor:PartyId , action:Action) -> "SAOPState":
		return super().WithAction(actor, action).WithProgress(self.advanceProgress())

	def checkAction(self, actor:PartyId, action:Action) -> Optional[str]:
		msg = super().checkAction(actor, action)
		if msg:
			return msg

		if actor != self._getNextActor():
			return "Party does not have the turn "

		# check protocol is followed for specific actions
		if isinstance(action, Accept):
			bid = self._getLastBid()
			if not bid:
				return "Accept without a recent offer";

			if bid != action.getBid():
				return "Party accepts a bid differing from the last offer ="\
						+str(bid) + ", action=" + str(action) + ")"
			return None
		elif isinstance(action, Offer):
			return None
		elif isinstance(action, EndNegotiation):
			return None
		return "Action " + str(action) + " is not allowed in SAOP"

	def _getLastBid(self) -> Optional[ Bid ]:
		'''
		Check up to nparticipants-1 steps back if there was an offer.
	 
		@return Bid from the most recent offer, or null if no such offer
		'''
		nparticipants = len(self.getConnections())
		acts = self.getActions()
		n = len(acts) - 1
		while n > len(acts) - nparticipants and n >= 0:
			action = acts[n]
			if isinstance(action , Offer):
				return action.getBid()
			n = n - 1
		return None

	def _getNextActor(self) -> PartyId:
		'''
		@return the next actor in the current state. Assumes 1 action per actor
		        every time. NOTE if party disconnects this would jump wildly but
		        nego stops then anyway
		'''		
		return self.getConnections()[len(self.getActions()) % len(self.getConnections())]

	def advanceProgress(self) -> Progress:
		'''
		@return new progress state
		'''		
		newprogress = self.getProgress()
		assert newprogress
		if isinstance(newprogress, ProgressRounds) and self._isLastActor():
			newprogress = newprogress.advance()
		return newprogress

	def _isLastActor(self) -> bool:
		'''
		@return true if the current actor is the last actor in the list
		'''
		nparticipants = len(self.getConnections())
		return len(self.getActions()) % nparticipants == nparticipants - 1;

	def getResults(self) -> List[SessionResult]:
		return [SessionResult(self.getPartyProfiles(), self.getAgreements(),
				{}, self.getError())]
