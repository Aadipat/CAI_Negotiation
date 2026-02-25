from typing import Dict, Any
from geniusweb.actions.AbstractAction import AbstractAction
from geniusweb.actions.PartyId import PartyId
from geniusweb.issuevalue.Bid import Bid


class ActionWithBid ( AbstractAction ):
	'''
	An {@link Action} containing a bid. Note that the presense of a bid does not
	necessarily mean that an offer was placed for this bid.

	'''

	def __init__(self,  actor:PartyId,	bid:Bid):
		'''
		@param param the actor partyid: 
		@param bid the bid. FIXME use Bid object and strong typing
		'''
		super().__init__(actor)
		self._bid = bid

	def getBid(self) -> Bid: 
		'''
		@return the {@link Bid} that this action is about.
		'''
		return self._bid;

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			super().__eq__(other) and self._bid==other._bid

	def __hash__(self):
		return hash((self._actor, self._bid))
	