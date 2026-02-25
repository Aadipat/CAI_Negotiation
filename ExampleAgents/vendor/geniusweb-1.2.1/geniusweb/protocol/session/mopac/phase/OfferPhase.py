from typing import List, Any

from geniusweb.actions.Action import Action
from geniusweb.actions.EndNegotiation import EndNegotiation
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.Inform import Inform
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.protocol.ProtocolException import ProtocolException
from geniusweb.protocol.session.mopac.phase.DefaultPhase import DefaultPhase
from geniusweb.protocol.session.mopac.phase.Phase import Phase
from geniusweb.protocol.session.mopac.phase.VotingPhase import VotingPhase


class OfferPhase (DefaultPhase):


	def With(self, actor:PartyId , action:Action ,timems:int)->"OfferPhase" :
		try:
			self._checkAction(actor, action, timems)
		except ProtocolException as ex:
			return self.WithException(ex)
		return OfferPhase(self._partyStates.WithAction(action), self._deadline, self._evaluator);

	def getInform(self)->Inform :
		return YourTurn()

	def WithException(self,  e:ProtocolException) -> "OfferPhase" :
		# don't print to stdout
		# System.out.println("Party kicked because of protocol exception:" + e);
		return OfferPhase(self._partyStates.WithException(e), self._deadline, 
						self._evaluator)

	def finish(self)->Phase :
		return OfferPhase(self._partyStates.finish(), self._deadline, self._evaluator)

	def _checkedNext(self,  deadln:int) ->VotingPhase :
		return VotingPhase(self._getOffers(), self._partyStates.flush(), deadln,
				self._evaluator)

	def _getOffers(self)->List[Offer] :
		return self._partyStates.getActionsOfType(Offer)

	def  getAllowedActions(self)->List[Any] : #Class<? extends Action>> 
		return [Offer, EndNegotiation]

