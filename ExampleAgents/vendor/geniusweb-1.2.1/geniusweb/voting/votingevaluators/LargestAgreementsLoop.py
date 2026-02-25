from geniusweb.inform.Agreements import Agreements
from geniusweb.voting.CollectedVotes import CollectedVotes
from geniusweb.voting.VotingEvaluator import VotingEvaluator


class LargestAgreementsLoop (VotingEvaluator):
	'''
	{@link #getAgreements()} collects all possible {@link Agreements}. We're
	finished only when {@link #getAgreements()} covers all except possibly 1
	party.
	
	The agreements is a list of {@link Bid}s and a maximum-sized list of
	{@link PartyId}s that placed a satisfied vote for that bid. maximum-sized
	means that there is no larger subset of votes for that bid. There may be
	other subsets of equal size for the bid. If there are no agreements at all
	for a bid, the bid is not placed in the map.
	'''

	def __init__(self) :
		self._allVotes = CollectedVotes({},{})
		self._maxAgreements = None

	
	def getAgreements(self)->Agreements:
		if self._maxAgreements == None:
			self._maxAgreements = self._collectAgreements()
		return self._maxAgreements;

	def isFinished(self)->bool:
		parties = set(self._allVotes.keys())
		parties= set([ party for party in parties 
				if not party in self.getAgreements().getMap().keys()])
		return len(parties) < 2

	def create(self, votes:CollectedVotes ) -> "LargestAgreementsLoop" :
		res= LargestAgreementsLoop()
		res._allVotes = votes
		return res

	def _collectAgreements(self)-> Agreements :
		'''
		@return the agreements that were reached from the given votes, using the
		        greedy algorithm picking the largets votesets.
		'''
		remainingvotes = self._allVotes;
		newagreements = Agreements()
		while True:
			agrees = remainingvotes.getMaxAgreements()
			if len(agrees)==0:
				break;
			# find the bid with max group power
			maxbid = max(agrees.keys(), 
				key=lambda bid: self._allVotes.getTotalPower(agrees[bid]))
			
			maxparties = agrees[maxbid]
			
			agreemap = {party:maxbid for party in maxparties }
			newagreements = newagreements.With(Agreements(agreemap))
			remainingvotes = remainingvotes.Without(maxparties)
		return newagreements

	def __hash__(self):
		'''
		WARNING you must manually set prime=37 here to fix collision with
		{@link LargestAgreement}.
		'''
		return 37*hash(self._allVotes)
		
	def __eq__(self, other):
		return isinstance(other, self.__class__) and\
			self._allVotes == other._allVotes

	def __repr__(self):
		return "LargestAgreementsLoop";

