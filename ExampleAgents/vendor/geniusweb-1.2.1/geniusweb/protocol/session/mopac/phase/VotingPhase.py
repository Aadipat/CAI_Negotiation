from typing import List, Any

from geniusweb.actions.Action import Action
from geniusweb.actions.EndNegotiation import EndNegotiation
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.actions.Votes import Votes
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Voting import Voting
from geniusweb.protocol.ProtocolException import ProtocolException
from geniusweb.protocol.session.mopac.PartyStates import PartyStates
from geniusweb.protocol.session.mopac.phase.DefaultPhase import DefaultPhase
from geniusweb.protocol.session.mopac.phase.OptInPhase import OptInPhase
from geniusweb.protocol.session.mopac.phase.Phase import Phase
from geniusweb.voting.VotingEvaluator import VotingEvaluator


class VotingPhase (DefaultPhase):

	def __init__(self,  offers: List[Offer],
			partyStates:PartyStates,
			deadline: int,
			evaluator:VotingEvaluator ) :
		super().__init__(partyStates, deadline, evaluator)
		self._offers = offers
		if offers==None:
			raise ValueError("offers must be not null")

	def With(self, actor:PartyId ,action: Action , now:int)-> "VotingPhase" :
		try:
			self._checkAction(actor, action, now)
		except ProtocolException as ex:
			return self.WithException(ex)
		return VotingPhase(self._offers, self._partyStates.WithAction(action), self._deadline,
				self._evaluator);

	def getInform(self)->Inform :
		return Voting(self._offers, self._partyStates.getPowers())

	def WithException(self, e:ProtocolException ) ->"VotingPhase" :
		return VotingPhase(self._offers, self._partyStates.WithException(e), self._deadline,
				self._evaluator)

	def finish(self)->"VotingPhase" :
		return VotingPhase(self._offers, self._partyStates.finish(), self._deadline,
				self._evaluator)

	def _checkedNext(self,deadln:int) ->Phase :
		return OptInPhase(self.getVotes(), self._partyStates.flush(), deadln,
				self._evaluator);

	def getAllowedActions(self) ->List[Any]: #Class<? extends Action>>: 
		return [Votes, EndNegotiation]

	def  getVotes(self)->List[Votes]:
		'''
		@return all votes done in this phase.
		'''
		return  [ act for act in self._partyStates.getActions() if isinstance(act, Votes)]
	
	def getOffers(self)->List[Offer]:
		'''
		@return the offers received in the {@link OfferPhase}
		'''
		return list(self._offers)