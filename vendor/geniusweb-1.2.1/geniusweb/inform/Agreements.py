from __future__ import annotations

from typing import Any, Dict

from pyson.JsonValue import JsonValue

from geniusweb.actions.PartyId import PartyId
from geniusweb.issuevalue.Bid import Bid
from geniusweb.utils import toStr


class Agreements:
	'''
	There can be multiple agreements from a single negotiation. This object
	contains the agreements. Each party can agree only on 1 bid and there are
	always at least 2 parties agreeing on a bid.
	'''
	def __init__(self, agreements:Dict[PartyId, Bid] =  {} ) :
		'''
		@param agrees a map, with the bid that was agreed on by a party
		HACK Must be Dict[PartyId, Bid]
		'''
		if type(agreements)!=dict:
			raise ValueError("Agreements must be a dict")
		self._agreements = agreements

	@JsonValue()
	def getAgreements(self)->Dict[PartyId, Bid]:
		return self._agreements

	def With(self, other:"Agreements" ) ->"Agreements" :
		'''
		* @param other {@link Agreements}
		* @return a new Agreement containing this plus other agreements
		* @throws IllegalArgumentException if parties in other are already in this
		*    agreement.
		'''
		newagrees = self._agreements.copy()
		for pid in  other._agreements.keys():
			if pid in newagrees:
				raise ValueError("party " + str(pid) + " already has agreement");
			newagrees[pid]=other._agreements[pid]
		return Agreements(newagrees);

	def getMap(self)-> Dict[PartyId,Bid]: 
		'''
		@return actual agreemenets contained here
		'''
		return self._agreements.copy()


	def __repr__(self): 
		return "Agreements" + toStr(self._agreements)
	
	def __eq__(self, other):
		return isinstance(other, self.__class__) and  self._agreements == other._agreements

	
	def __hash__(self):
		return sum([ hash(k) + 31 * hash(v) for (k,v) in self._agreements.items()])
