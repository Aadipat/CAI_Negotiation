from typing import Optional, Dict, FrozenSet

from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.Agreements import Agreements
from geniusweb.issuevalue.Bid import Bid
from geniusweb.voting.CollectedVotes import CollectedVotes
from geniusweb.voting.VotingEvaluator import VotingEvaluator


class LargestAgreement(VotingEvaluator):
	'''
	Take the first possible agreement, and take the largest possible agreement.
	Stop after first agreement.
	'''

	def __init__(self ) :
		'''
		@param votes the votes collected so far.
		YOU MUST USE THE DEFAULT VALUE.
		'''
		self._allVotes = CollectedVotes({},{});
		self._maxAgreements:Optional[Agreements ] = None

	def getVotes(self):
		return self._allVotes

	def getAgreements(self)->Agreements :
		if self._maxAgreements == None:
			self._maxAgreements = self._collectVotes()
		return self._maxAgreements #type:ignore

	def isFinished(self)-> bool:
		parties = set(self._allVotes.getVotes().keys())
		for party in self.getAgreements().getMap().keys():
			parties.remove(party)
		return len(parties) < 2

	def create(self, votes:CollectedVotes ) ->VotingEvaluator :
		newagree= LargestAgreement()
		# bit hacky, because we can not have overloaded constructor
		# like in java
		newagree._allVotes=votes
		return newagree

	def _collectVotes(self)->Agreements:
		'''
		@return the agreements that were reached from the given votes, using the
		        greedy algorithm picking the largets votesets.
		'''
		agreement = Agreements()

		agrees:Dict[Bid, FrozenSet[PartyId]] = self._allVotes.getMaxAgreements()
		if len(agrees)==0:
			return agreement; # none

		# find the bid with max group power
		maxpower = -9999999999999
		for bid in agrees:
			power = self._allVotes.getTotalPower(agrees[bid])
			if power>maxpower:
				maxpower=power
				maxbid = bid
		agreemap = { party:maxbid for party in agrees[maxbid]}
		agreement = agreement.With(Agreements(agreemap))
		return agreement

	def __hash__(self):
		return hash(self._allVotes)

	def __eq__(self, other):
		return isinstance(other, self.__class__) and\
			self._allVotes == other._allVotes

	def __repr__(self):
		return "LargestAgreement";
