from typing import Any, Dict
from geniusweb.actions.ActionWithBid import ActionWithBid
from geniusweb.actions.PartyId import PartyId
from geniusweb.issuevalue.Bid import Bid

class Accept (ActionWithBid):
	'''
	An accept done by some party indicates that that party agrees with the bid.
	Usually the contained {@link Bid} must be a bid that was previously
	{@link Offer}ed by some party.
	'''
	def __init__(self,actor:PartyId ,bid:Bid):
		'''
		@param id  the accepting party.
		@param bid the bid that was offered before (usually by some other Party )
		FIXME stronger typing using Bid class
		'''
		super().__init__(actor, bid);

	def __repr__(self)->str:
		return("Accept[" + str(self.getActor()) + "," + str(self.getBid()) + "]")


