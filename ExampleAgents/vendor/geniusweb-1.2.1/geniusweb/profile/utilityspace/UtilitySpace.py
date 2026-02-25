from decimal import Decimal

from geniusweb.issuevalue.Bid import Bid
from geniusweb.profile.FullOrdering import FullOrdering


class UtilitySpace (FullOrdering ):
	'''
	A utilityspace defines a profile in terms of a utility of a bid. Bids with
	higher utility are preferred over bids with less utility.
	'''

	def getUtility(self, bid:Bid ) -> Decimal:
		'''
		@param bid the {@link Bid} to be evaluated
		@return the utility value of this bid. This MUST return a number in the range
		        [0,1]. 0 means preferred the least and 1 means preferred the most.
		'''

	def isPreferredOrEqual(self, bid1:Bid, bid2:Bid ) -> bool:
		return self.getUtility(bid1) >= self.getUtility(bid2)

