from abc import abstractmethod

from geniusweb.actions.Action import Action
from geniusweb.actions.PartyId import PartyId
from geniusweb.protocol.ProtocolException import ProtocolException
from geniusweb.protocol.session.mopac.PartyStates import PartyStates
from geniusweb.protocol.session.mopac.phase.Phase import Phase, PHASE_MINTIME, \
	PHASE_MAXTIME
from geniusweb.voting.VotingEvaluator import VotingEvaluator


class DefaultPhase(Phase):
	# deadline for this phase, ms since 1970
	
	def __init__(self,  partyStates:PartyStates, deadline:int,
			evaluator:VotingEvaluator ): 
		'''
		@param partyStates the {@link PartyStates}
		@param deadline    deadline for this phase, ms since 1970
		@param evaluator   the {@link VotingEvaluator} to be used
		'''
		self._partyStates = partyStates
		self._deadline = deadline
		self._evaluator = evaluator

	def isFinal(self, now:int)->bool:
		return now >= self._deadline or len(self._partyStates.getNotYetActed())==0

	def getDeadline(self)->int:
		return self._deadline

	def _checkAction(self, actor:PartyId ,action: Action , now:int):
		'''
		Check if actor can do given action. Basic checks:
		<ul>
		<li>real actor does not match action's actor
		<li>deadline for this phase has passed
		<li>action is not allowed in this phase
		<li>actor already acted in this phase
		</ul>
		@param actor  the actor that really acted
		@param action the action that was done
		@param now    current time
		@throws ProtocolException if the action violates the protocol
		'''
		if action == None:
			raise ProtocolException("Action=null", actor)
		if actor != action.getActor():
			raise ProtocolException(
					"Incorrect actor info in action:" + str(action.getActor()),
					actor)
		if self.isFinal(now):
			raise ProtocolException("passed deadline", actor)
		if not type(action) in self.getAllowedActions():
			raise ProtocolException("Action not allowed in "
					+ type(self).__name__ + ": " + str(action), actor)
		if not actor in self._partyStates.getNotYetActed():
			raise ProtocolException("Actor can not act anymore", actor)
		return

	def getPartyStates(self)->PartyStates :
		'''
		@return current PartyStates
		'''
		return self._partyStates

	def getEvaluator(self)->VotingEvaluator :
		return self._evaluator

	def next(self, now:int, duration:int)->Phase : 
		if duration < PHASE_MINTIME or duration > PHASE_MAXTIME:
			raise ValueError("Bug, illegal duration")
		if not self.isFinal(now):
			raise ValueError("phase is not final")
		return self._checkedNext(now + duration)

	@abstractmethod
	def  _checkedNext(self, dl:int)-> Phase:
		'''
		As {@link #next(long, long)} but DefaultPhase already checked that 1.
		there is enough time for a next phase 2. current state is final 3.
		
		@param dl the deadline for the next phase (ms since 1970).
		@return the next phase
		'''

	def __repr__(self):
		return type(self).__name__ + "[" + str(self._partyStates) + "," + \
			str(self._deadline) + "," + str(self._evaluator) + "]"

	def __hash__(self):
		return hash((self._deadline, self._evaluator, self._partyStates))


	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			and self._partyStates==other._partyStates \
			and self._deadline==other._deadline\
			and self._evaluator==other._evaluator

