from typing import Dict, Any

from geniusweb.actions.ActionWithBid import ActionWithBid
from geniusweb.actions.PartyId import PartyId
from geniusweb.issuevalue.Bid import Bid


class Offer ( ActionWithBid ):
	'''
	An offer represents a proposal from some actor that others may accept.
	Executing an Offer action usually means that the party doing the action
	accepts the offer himself.
	'''

	def __init__(self,   actor:PartyId, bid:Bid ):
		super().__init__(actor, bid);

	def __repr__(self)->str:
		return "Offer[" + str(self.getActor()) + "," + str(self.getBid()) + "]"

