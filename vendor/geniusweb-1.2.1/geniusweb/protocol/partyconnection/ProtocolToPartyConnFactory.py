from abc import abstractmethod
from typing import List

from geniusweb.actions.Action import Action
from geniusweb.connection.ConnectionFactory import ConnectionFactory
from geniusweb.inform.Inform import Inform
from geniusweb.protocol.partyconnection.ProtocolToPartyConn import ProtocolToPartyConn
from geniusweb.references.Reference import Reference


class ProtocolToPartyConnFactory(ConnectionFactory[Action, Inform] ):
	'''
	An extended {@link ConnectionFactory} that store PartyIDs with the
	connections, making it possible to find back the appropriate connection given
	a PartyID. Also, it allows the connection factory to actually assign the
	PartyIDs.
	'''

	@abstractmethod
	def connectAll(self, references: List[Reference] ) -> List[ProtocolToPartyConn]:
		'''
		Connects a set of References in one go, following a modified Banker's
		algorthm.
		
		@param references the list of references to connect with
		@return a List of connections, one fore each Reference.
		@throws ConnectionError         if a connection is failing irrecoverably.
		@throws NoResourcesNowException is there are insufficient resources now.
		                                This also includes a suggested moment to
		                                retry.
		'''
	
