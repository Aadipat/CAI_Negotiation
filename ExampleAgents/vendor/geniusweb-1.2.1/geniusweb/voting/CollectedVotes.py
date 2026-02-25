from typing import Dict, Set, FrozenSet

from tudelft.utilities.immutablelist.FixedList import FixedList
from tudelft.utilities.immutablelist.PowerSet import PowerSet

from geniusweb.PriorityQueue import PriorityQueue
from geniusweb.actions.PartyId import PartyId
from geniusweb.actions.Vote import Vote
from geniusweb.actions.Votes import Votes
from geniusweb.issuevalue.Bid import Bid
from geniusweb.utils import toTuple, toStr


# who removed sign function from python?
sign = lambda a: (a>0) - (a<0)

class CollectedVotes:
	'''
	Utility class. Typically contains all the votes collected from 1 round. Can
	find the best combinations of votes, eg to get the maximum consensus group
	'''


	def __init__(self, votesMap:Dict[PartyId, Votes] ,	powers:Dict[PartyId, int] ) :
		''''
		@param votesMap the {@link Votes} done for each party
		@param powers    the power of each party. The power is an integer number.
		                In the voting process, the party powers add up to form
		                the total voting power. This set may contain parties that
		                are not in newmap.
		'''
		self._allvotes = dict(votesMap)
		self._powers = dict(powers)
		self._allBids = None 

		if not set(votesMap.keys()).issubset(set(powers.keys())):
			raise ValueError("All voting parties must have a power")

	def  With(self, votes:Votes , power:int)->"CollectedVotes":
		'''
		@param votes additional set of votes for a new party that did not yet
		             vote.
		@param power powers for the new party, can be null if power already set
		             previously.
		@return new CollectedVotes with the new votes added.
		'''
		actor = votes.getActor()
		if actor in self._allvotes:
			raise ValueError("Party " + str(actor) + " already voted")

		newpowers:Dict[PartyId, int]  = dict(self._powers)
		if not actor in self._powers:
			if power == None:
				raise ValueError("Power must be set for new actor " + str(actor))
			newpowers[actor]= power

		newmap = dict(self._allvotes)
		newmap[actor]= votes
		return CollectedVotes(newmap, newpowers)

	def getVotes(self)->Dict[PartyId, Votes] :
		'''
		@return all the votes placed so far
		'''
		return dict(self._allvotes)

	def getPowers(self) ->Dict[PartyId, int] :
		'''
		@return the powers of all parties
		'''
		return dict(self._powers)

	def  getMaxAgreements(self)->Dict[Bid, FrozenSet[PartyId]]:
		'''
		@return a map containing for each {@link Bid}s a subset of
		        {@link PartyId}s that placed a satisfied vote for that bid, such
		        that the subset has maximum power. Maximum power means that there
		        is no other subset of satisfied votes for that bid with more
		        group power. There may be other subsets of equal power for the
		        bid. If there are no concensus possibilities at all for a bid,
		        the bid is not placed in the map.
		'''
		agreements: Dict[Bid, FrozenSet[PartyId]]  = {}
		allbidsmap = self.getAllBids()
		for bid in allbidsmap.keys():
			mx = self._getMaxPowerGroup(allbidsmap[bid])
			if len(mx)>0:
				agreements[bid]=mx
		return agreements

	def getAllBids(self) -> Dict[Bid, Set[Vote]]:
		'''
		@return all bids that were voted on and the votes for that bid. This
		        basically reverses keys and values in {@link #allvotes}
		'''
		if self._allBids == None: #type:ignore
			self._allBids = self._getAllBids1()  #type:ignore
		return self._allBids  #type:ignore

	def Without(self, parties:Set[PartyId] )->"CollectedVotes":
		'''
		@param parties the parties to be removed
		@return new CollectedVotes without given parties
		'''
		newvotes = dict(self._allvotes)
		newpower = dict(self._powers)
		for party in parties:
			newvotes.pop(party)
			newpower.pop(party)
		
		return CollectedVotes(newvotes, newpower)

	def getTotalPower(self, parties:FrozenSet[PartyId] ) -> int:
		'''
		@param parties a list of parties
		@return total voting power of the parties
		'''
		return sum([self._powers[p] for p in parties])

	def _getMaxPowerGroupBreathFirst(self, allvotes:Set[Vote] ) -> FrozenSet[PartyId] :
		''' 
		Breath-first optimized search, similar as {@link #getMaxPowerGroup(Set)}
		but more efficient on average (remains to be proven). Notice that this
		algorithm may be more expensive particularly if there is no consensus at
		all, because of the added overhead of the breath-first search
		
		@param allvotes a list of all votes for a particular bid.
		@return a consensus-group with maximum power, so there is no other
		    consensus group that has more power (but there may be other
		    groups with same power). returns empty set if no consensus found
		'''
		
		# CHECK how about scoping. What is 'this' referring to?
		this=self
		def comparator(vs1:Set[Vote], vs2:Set[Vote]):
			parties1 = frozenset([vote.getActor() for vote in vs1])
			parties2 = frozenset([vote.getActor() for vote in vs2])
			return sign(this.getTotalPower(parties1)-
					this.getTotalPower(parties2)) 

		'''
		queue that keeps the options for the breath-first search sorted from
		highest to lowest power of the voters.
		'''
		queue = PriorityQueue[Set[Vote]] (comparator)
		queue.put(allvotes) 

		while not queue.empty():
			# try one with the highest power
			vs = queue.get()
			if self._isViable(vs):
				return self.getParties(vs)
			if len(vs) > 1:
				# vote can be splitted. push all new subsets
				for vote in vs:
					subvotes = set(vs)
					subvotes.remove(vote)
					# avoid duplicate work. Since this has a removed party,
					# and assuming power of each party >=1,
					# we can not already have checked subvotes
					if not subvotes in queue:
						queue.put(subvotes)

		return frozenset()

	def _getMaxPowerGroup(self, votes:Set[Vote] )-> FrozenSet[PartyId] :
		'''
		@param votes a list of all votes for a particular bid. The parties that
		             placed the votes are called 'voters'
		@return a consensus-group with maximum power, so there is no other
		        consensus group that has more power (but there may be other
		        groups with same power). returns empty set if no consensus found
		'''
		maxgroup:FrozenSet[PartyId] = frozenset()
		maxpower = 0

		for parties  in self._getConsensusGroups(votes):
			power = self.getTotalPower(parties)
			if power > maxpower:
				maxgroup = parties
				maxpower = power
		return frozenset(maxgroup)

	def _getConsensusGroups(self, votes: Set[Vote] )-> FrozenSet[FrozenSet[PartyId]] :
		'''
		@param votes a set of {@link Votes} for one single {@link Bid}. It is
		             assumed all votes are by different parties.
		@return all subsets sets of parties that create a viable consensus vote.
		        A viable consensus voteset VS is a subset of the votes, such that
		        <ol>
		        <li>|VS| &ge; 2
		        <li>TP = The sum of the powers of the parties in VS
		        <li>forall v in VS: v_minpower &le; TP &le; v_maxpower
		        </ol>
		        Notice that this algorithm works in exponential space
		        (=expensive) and not suited for large numbers of parties. Should
		        work fine for up to 10 parties.
		'''
		groups:Set[FrozenSet[PartyId]]  = set()

		allVotePermutations = PowerSet[Vote](FixedList[Vote](votes))
		# check each possible subset.
		for voteList in allVotePermutations:
			if self._isViable(voteList):
				groups.add(self.getParties(voteList))
		return frozenset(groups)

	def _isViable(self, voteList) -> bool:
		'''
		@param voteList a :list_iterator of votes for a single bid.
		@return true if this votelist satisfies the requirements of all
		        participants and there are &ge; 2 parties
		'''
		parties = self.getParties(voteList)
		totalpower = self.getTotalPower(parties);
		return len(parties) >= 2 and totalpower >= self._getMinPower(voteList)\
				and totalpower <= self._getMaxPower(voteList)

	@staticmethod
	def getParties(voteList) -> FrozenSet[PartyId] :
		'''
		@param voteList iterable of Vote, list of all {@link Vote}s
		@return frozen set with all parties that did a vote
		'''
		parties:Set[PartyId]  = set()
		for vote in voteList:
			parties.add(vote.getActor())
		return frozenset(parties)

	def _getMinPower(self, votes) ->int:
		'''
		@param votes a iterable of Vote, list of {@link Vote}s on one Bid. All parties must be
		             known
		@return the minimum voting power needed for this group, so that all can
		        accept. This is equal to the max of the vote.getMinPower
		'''
		mx = 0
		for vote in votes:
			mx = max(mx, vote.getMinPower())
		return mx

	def _getMaxPower(self, votes) -> int:
		'''
		@param votes a iterable Vote list of {@link Vote}s on one Bid. All parties must be
		             known
		@return the maximum voting power needed for this group, so that all can
		        accept. This is equal to the min of the vote.getMaxPower
		'''
		mn = 9999999999999999 #int.maxvalue?
		for vote in votes:
			mn = min(mn, vote.getMaxPower())
		return mn

	def _getAllBids1(self) -> Dict[Bid, Set[Vote]]:
		bids:Dict[Bid, Set[Vote]]  = {}
		for votes in self._allvotes.values():
			for vote in votes.getVotes():
				bid = vote.getBid()
				if not bid in bids:
					bids[bid]=set()
				bids[bid].add(vote)
		return bids

	def __hash__(self):
		return hash((toTuple(self._allvotes), toTuple(self._powers)))

	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			and self._allvotes == other._allvotes\
			and self._powers==other._powers

	def __repr__(self)->str:
		return "CollectedVotes[" + toStr(self._allvotes) \
			+ "," + toStr(self._powers) + "]"
