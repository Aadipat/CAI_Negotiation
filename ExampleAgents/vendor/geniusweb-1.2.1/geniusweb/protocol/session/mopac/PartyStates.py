from typing import Set, List, Dict, TypeVar, Optional

from geniusweb.actions.Action import Action
from geniusweb.actions.EndNegotiation import EndNegotiation
from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.Agreements import Agreements
from geniusweb.protocol.ProtocolException import ProtocolException
from geniusweb.utils import toTuple, val, toStr


class PartyStates:
	'''
	Invariant: contains the current state of all participating parties. A party
	either notYetActed, did action, reached an agreement, walked away or made a
	{@link ProtocolException}.
	<p>
	After a phase completes, the actions are filtered/handled to collect
	agreements and move remaining parties back to notYetActed.
	'''
	# all parties must be in exactly one state at all times.
	
	def __init__(self, powers:Dict[PartyId, int],
			notYetActed:Optional[Set[PartyId]]=None,
			actions: List[Action] =[],
			agreements:Agreements = Agreements(),
			walkedAway:List[PartyId]=[],
			exceptions:Dict[PartyId, ProtocolException] ={}):
		'''
		notice: order of arguments, power is now first instead of last because
		python requires obligatory arguments first.
		'''
		if notYetActed!=None:
			self._notYetActed = set(notYetActed) #type:ignore
		else:
			self._notYetActed = set(powers.keys())
		self._actions = list(actions)
		self._agreements = agreements
		self._walkedAway = list(walkedAway)
		self._exceptions = dict(exceptions)
		self._powers = dict(powers)



	def WithAction(self,  action:Action)-> "PartyStates":
		'''
		@param action the action done by some party. The correctness of action,
		              particularly of {@link Action#getActor()}, must be correct.
		@return new state with party done given action. This just accepts any
		        given action and is not considering number of rounds, time or
		        whether an action is allowed.
		
		@throws IllegalArgumentException if party doing action already acted.
		                                 This is just a safety check as legality
		                                 of actions should be checked before
		                                 calling this.
		'''
		if not action.getActor() in self._notYetActed:
			raise ValueError("actor already acted: " + str(action))
		if isinstance(action, EndNegotiation):
			return self.WithWalkAway(action.getActor())
		newActions = list(self._actions)
		newActions.append(action)
		return PartyStates(self._powers, self._removeParty(action.getActor()), newActions,
				self._agreements, self._walkedAway, self._exceptions)

	def WithAgreements(self, newAgree:Agreements )->"PartyStates" :
		'''
		 @param newAgree a new agreements to be merged with existing agreements.
		                 The parties in the agreement must have acted and thus in
		                 actions.
		 @return new PartyStates with agreeing parties removed from actions and
		         added to Agreements.
		'''
		parties = newAgree.getMap().keys()
		newActions = [act for act in self._actions if not act.getActor() in parties] 
		return PartyStates(self._powers, self._notYetActed, newActions,
				self._agreements.With(newAgree), self._walkedAway, self._exceptions)


	def  WithWalkAway(self, actor:PartyId ) ->"PartyStates": 
		if not actor in self._notYetActed:
			raise ValueError("actor already acted: " + str(actor))
		newWalkAway = list(self._walkedAway)
		newWalkAway.append(actor)
		return PartyStates(self._powers,self._removeParty(actor), self._actions, self._agreements,
				newWalkAway, self._exceptions)

	def  WithException(self, e:ProtocolException ) -> "PartyStates":
		'''
		Move party from active to exceptions.
		
		@param e the exception that the party caused
		@return new PartyStates with party that caused the exception in the
		        exceptions list and removed from the active list. Nothing happens
		        if party is not active.
	'''
		if not e.getParty() in self._notYetActed:
			# complex case. Party did valid action but now is messing around.
			# Easiest seems to completely ignore it. CHECK.
			return self;

		newExc = dict(self._exceptions)
		newExc[val(e.getParty())]= e
		return PartyStates(self._powers, self._removeParty(val(e.getParty())), 
			self._actions, self._agreements,self._walkedAway, newExc)

	def  getNotYetActed(self)->Set[PartyId]:
		'''
		@return parties that have not yet acted

		'''
		return self._notYetActed

	def  getNegotiatingParties(self)-> Set[PartyId]:
		'''
		@return parties that are still in the negotiation. These are the parties
		        that not yet acted plus the ones that did an action.
		'''
		parties = set([ act.getActor() for act in self._actions ])
		
		parties = parties.union(self._notYetActed)
		return parties

	def _removeParty(self, party:PartyId )->Set[PartyId] :
		'''
		@param actor
		@return {@link #notYetActed} with actor removed
		 @throws IllegalArgumentException if party already acted (not in
		                                 {@link #notYetActed}).
	'''
		newActiveParties = set(self._notYetActed)
		if not party in newActiveParties:
			raise ValueError(
					"Party " + str(party) + " is not active, can't be removed")
		newActiveParties.remove(party)
		return newActiveParties

	def getAgreements(self)->Agreements :
		return self._agreements

	def getPowers(self)->Dict[PartyId,int] :
		return dict(self._powers)

	def  getExceptions(self)->Dict[PartyId, ProtocolException]:
		return dict(self._exceptions)

	def finish(self)->"PartyStates": 
		'''
		@return new state where all {@link #notYetActed} are moved to the
		        exceptions list.
		'''
		newstate = self
		for party in self._notYetActed:
			newstate = newstate.WithException(ProtocolException("Party did not act", party))
		return newstate

	def getActions(self)->List[Action] :
		return list(self._actions)

	def getWalkedAway(self)->List[PartyId] :
		'''
		@return all parties that walked away
		'''
		return list(self._walkedAway)

# 	T=TypeVar("T", Action)
	def  getActionsOfType(self, typ) -> List:
		'''
		@param <T>  the type of objects requested
		@param typ the type of actions to extract. Must be of type T, needed
			    because of java's type erasure.
		
		@return all actions of requested type in this phase
		''' 
		return [act for act in self._actions if isinstance(act, typ) ]

	def __repr__(self):
		return "PartyStates[" + str(list(self._notYetActed)) + "," + str(self._actions) + "," + \
			str(self._agreements)+  "," + str(self._walkedAway) + "," + toStr(self._exceptions) + "]"

	def flush(self)->"PartyStates" :
		'''
		@return states with all parties that are in {@link #actions} moved back
		        to {@link #notYetActed}. This state is then ready for a next
		        phase.
		@throws IllegalStateException if {@link #notYetActed} is not empty
		'''
		if len(self._notYetActed)!=0:
			raise ValueError(
					"Some parties did not yet act:" + str(self._notYetActed))
		return PartyStates(self._powers, self.getNegotiatingParties(), [],
				self._agreements, self._walkedAway, self._exceptions)

	def __hash__(self):
		return hash((tuple(self._actions), self._agreements, toTuple(self._exceptions), 
					tuple(self._notYetActed), toTuple(self._powers), tuple(self._walkedAway)))

	def __eq__(self, other):
		return isinstance(other, self.__class__)\
			and self._actions == other._actions \
			and self._agreements == other._agreements \
			and self._exceptions == other._exceptions \
			and self._notYetActed == other._notYetActed \
			and self._powers == other._powers \
			and self._walkedAway == other._walkedAway 

