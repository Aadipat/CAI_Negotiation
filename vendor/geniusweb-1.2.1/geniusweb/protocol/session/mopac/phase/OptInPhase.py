from typing import List, Any

from geniusweb.actions.Action import Action
from geniusweb.actions.EndNegotiation import EndNegotiation
from geniusweb.actions.PartyId import PartyId
from geniusweb.actions.Votes import Votes
from geniusweb.inform.Inform import Inform
from geniusweb.inform.OptIn import OptIn
from geniusweb.protocol.ProtocolException import ProtocolException
from geniusweb.protocol.session.mopac.PartyStates import PartyStates
from geniusweb.protocol.session.mopac.phase.DefaultPhase import DefaultPhase
from geniusweb.protocol.session.mopac.phase.Phase import Phase
from geniusweb.voting.CollectedVotes import CollectedVotes
from geniusweb.voting.VotingEvaluator import VotingEvaluator


class OptInPhase ( DefaultPhase ):

	def __init__(self, votes:List[Votes] ,
			partyStates:PartyStates ,
			deadline:int,
			evaluator:VotingEvaluator ):
		super().__init__(partyStates, deadline, evaluator)
		self._votes = votes
		if votes==None:
			raise ValueError("votes must be not null")

	def getInform(self)->Inform :
		return OptIn(self._votes)

	def With(self, actor:PartyId , action:Action , now:int)->Phase :
		try:
			self._checkAction(actor, action, now)
			if isinstance(action,Votes):
				self._checkExtends(action)

			return OptInPhase(self._votes, self._partyStates.WithAction(action), 
							self._deadline, self._evaluator)

		except ProtocolException as e:
			return self.WithException(e)

	def _checkExtends(self, newvotes:Votes ) :
		'''
		Check that this action extends previous action.
		
		@param newvotes new {@link Votes} just received
		@throws ProtocolException if this action does not correctly extend
		      previous vote.
		'''
		actor = newvotes.getActor();
		# this actor is active so he must have voted in previous round.
		prevVotes = [v for v in self._votes if v.getActor() == actor ][0]
		if not newvotes.isExtending(prevVotes):
			raise ProtocolException("New votes " + str(newvotes)
					+ " does not extend previous vote " + str(prevVotes), actor)

	def WithException(self,  e:ProtocolException) ->"OptInPhase" :
		return OptInPhase(self._votes, self._partyStates.WithException(e), self._deadline, self._evaluator)

	def finish(self)-> "OptInPhase":
		states = self._partyStates.finish()
		votesmap = { }
		for v in states.getActionsOfType(Votes):
			votesmap[v.getActor()]=v
		allvotes = CollectedVotes(votesmap, states.getPowers())
		newAgree = self._evaluator.create(allvotes).getAgreements()
		if len(newAgree.getMap())>0:
			print("detected new agreements")
		finalStates = states.WithAgreements(newAgree)

		return OptInPhase(self._votes, finalStates, self._deadline, self._evaluator);

	def _checkedNext(self, newdeadline:int) ->"OfferPhase" : #type:ignore
		from geniusweb.protocol.session.mopac.phase.OfferPhase import OfferPhase
		return OfferPhase(self._partyStates.flush(), newdeadline, self._evaluator)

	def getAllowedActions(self) -> List[Any]: #<Class<? extends Action>> :
		return [Votes, EndNegotiation]

	def getVotes(self)->List[Votes]:
		return list(self._votes)

