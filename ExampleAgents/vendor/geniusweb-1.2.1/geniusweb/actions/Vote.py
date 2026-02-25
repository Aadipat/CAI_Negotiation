from geniusweb.actions.ActionWithBid import ActionWithBid
from geniusweb.actions.PartyId import PartyId
from geniusweb.issuevalue.Bid import Bid

class Vote ( ActionWithBid ):
	'''
	A vote is an indication by a party that it conditionally accepts a bid. It's
	then up to the protocol to determine the outcome.
	'''
	
	def __init__(self, actor:PartyId, bid:Bid ,minPower :int , maxPower:int):
		'''
		@param id       the {@link PartyId} that does the action
		@param bid      the bid that is voted on
		@param minPower the minimum power this bid must get in order for the vote
		                to be valid. Power is the sum of the powers of the
		                parties that are in the deal. If power=1 for all
		                participants (usually the default) power can be
		                interpreted as number of votes
		@param maxPower the maximum power this bid must get in order for the vote
		                 to be valid. See {@link #minPower}
		'''
		super().__init__(actor, bid)
		self._minPower = minPower
		self._maxPower = maxPower
		if bid == None or minPower == None or minPower < 1 or maxPower == None or maxPower < minPower:
			raise ValueError("Vote must have non-null bid and minVotes, and minPower must be >=1 and maxPower must be >=minPower")

	def getMinPower(self)  -> int:
		'''
		@return the minimum power this bid must get in order for the vote to be
		        valid.
		'''
		return self._minPower

	def getMaxPower(self)->int:
		'''
		@return the max power this bid must get in order for the vote to be
		        valid.
		'''
		return self._maxPower;

	#Override
	def __repr__(self) -> str:
		return "Vote[" + repr(self.getActor()) + "," + repr(self.getBid()) + ","\
			 + repr(self._minPower) + "," + repr(self._maxPower) + "]"

	def __hash__(self):
		return hash((self._actor, self._bid, self._minPower, self._maxPower))

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			super().__eq__(other) and self._minPower==other._minPower \
			and self._maxPower==other._maxPower

	
