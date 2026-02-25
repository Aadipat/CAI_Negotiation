from abc import ABC
from typing import List, Any

from pyson.JsonSubTypes import JsonSubTypes
from pyson.JsonTypeInfo import JsonTypeInfo, Id, As

from geniusweb.actions.Action import Action
from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.Inform import Inform
from geniusweb.protocol.ProtocolException import ProtocolException
from geniusweb.protocol.session.mopac.PartyStates import PartyStates 
from geniusweb.voting.VotingEvaluator import VotingEvaluator


PHASE_MAXTIME = 30000 # 30sec
PHASE_MINTIME = 100   # 100 millisec


@JsonTypeInfo(use=Id.NAME, include=As.WRAPPER_OBJECT)
@JsonSubTypes(["geniusweb.protocol.session.mopac.phase.OfferPhase.OfferPhase",
			"geniusweb.protocol.session.mopac.phase.OptInPhase.OptInPhase",
			"geniusweb.protocol.session.mopac.phase.VotingPhase.VotingPhase"])
class Phase(ABC):
	'''
	A Phase is a part of the round structure. In each round parties have to take
	multiple actions. Each action is part of a phase.
	
	Invariant: A phase object handles negotiation events, ensuring that the
	events are handled according to the possible actions in this phase. A phase
	object must always remain in a consistent state. It does so by modifying the
	contained {@link PartyStates} as needed.
	<p>
	The standard exception handling is assumed: unchecked exceptions are thrown
	only if there is a bug in the protocol. Because none of the functions in this
	interface throws, any error must be either ignored or the party must be
	kicked.
	'''

	def With(self, actor:PartyId ,action: Action ,now:int)->"Phase" :
		'''
		Handle an actor's action. If a {@link ProtocolException} occurs, this is
		handled by updating the PartyStates
		
		@param actor  the real actor (may differ from the actor contained in the
		              action)
		@param action the action submitted by actor, which this phase can really
		              handle.
		@param now    the current time
		@return new VotingPhase
		'''

	def WithException(self,  e:ProtocolException)->"Phase" :
		'''
		@param e a {@link ProtocolException}
		@return new Phase with a party disabled because it violated a protocol eg
	          breaking a websocket link.
		'''

	def getInform(self)->Inform :
		'''
		@return the inform object to send to all parties at start of phase.
		'''

	def isFinal(self, now:int) -> bool:
		'''
		@param now the current time
		@return true iff past deadline or no more actions are allowed anyway.
		        (which usually means, all parties have done exactly one act).
		        Notice, this is the main reason that it is desirable to require
		        all parties to act exactly once in each phase. Without such a
		        rule, the protocol will always have to wait till the deadline.
		'''

	def finish(self)->"Phase" :
		'''
		@return finished state. That means, all parties that did not act have
		         been kicked, new agreements have been computed, etc.
		'''

	def next(self, now:int, duration:int) -> "Phase" :
		'''
		Determines the next phase. Resets the actions field. Can only be called
		after {@link #finish()}
		
		@param now      the current time
		@param duration the max duration (ms) of the next phase. Must be between
		                {@link #PHASE_MINTIME} and {@link #PHASE_MAXTIME}. Also
		                make sure that now+duration is at most at the total
		                negotiation deadline.
		@return the next phase, or null if negotiation is complete.
		'''

	def getEvaluator(self)->VotingEvaluator :
		'''
		@return the voting evaluator
		'''

	def getDeadline(self)->int:
		'''
		@return time (ms since 1970) at which phase ends. The phase may end
    	    before, but never after this.
		'''

	def getPartyStates(self)->PartyStates :
		'''
		@return the party states. Notice that someone must call
	        {@link PartyStates#finish()} if passed the deadline.
		'''

	def  getAllowedActions(self) -> List[Any]: # Class<? extends Action>... 
		'''
		@return the allowed actinos in this phase
		'''
