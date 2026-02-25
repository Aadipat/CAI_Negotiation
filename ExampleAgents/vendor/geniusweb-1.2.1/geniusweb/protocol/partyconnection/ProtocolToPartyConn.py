from abc import ABC, abstractmethod

from geniusweb.actions.Action import Action
from geniusweb.actions.PartyId import PartyId
from geniusweb.connection.ConnectionEnd import ConnectionEnd
from geniusweb.inform.Inform import Inform


class ProtocolToPartyConn (ConnectionEnd[Action, Inform], ABC):
	'''
	Connection of the protocol with a party. Note, this is the opposite direction
	of a connection of the party with the protocol.
	'''

	@abstractmethod
	def getParty(self)-> PartyId :
		'''
		@return the partyId of the party that this connects to.
		'''
