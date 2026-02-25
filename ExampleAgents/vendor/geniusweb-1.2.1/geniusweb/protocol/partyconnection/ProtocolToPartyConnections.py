from __future__ import annotations
from typing import List, Optional, Dict

from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.Inform import Inform
from geniusweb.protocol.partyconnection.ProtocolToPartyConn import ProtocolToPartyConn


class ProtocolToPartyConnections: #implements Iterable<ProtocolToPartyConn> 
	'''
	Contains all parties with their connections. immutable
	'''

	def __init__(self, connections:List[ProtocolToPartyConn] ):
		self._connections = connections

	def get(self, pid:PartyId) -> Optional[ProtocolToPartyConn] :
		'''
		@param id the {@link PartyId} needed
		@return a connection with that party, or null if no such connection.
		'''
		for conn in self._connections:
			if pid==conn.getParty():
				return conn
		return None

	def allunique(self) ->bool:
		'''
		@return true iff all parties have one connection only
		'''
		return len(self._getParties()) == len(self._connections)

	def broadcast(self, info:Inform) -> Dict[PartyId, BaseException]: 
		'''
		Broadcast info to all parties. Notice that the broadcast immediately
		aborts if an error occurs and remaining parties will not receive the
		event. Therefore it is recommended to instead send to all parties
		individually to ensure all parties are handled individually.
		
		@param info the {@link Inform} to broadcast
		@return a Map&lt;PartyId, IOException&gt; where possible exceptions for
		        each party are stored. Normally a protocol would kick these
		        parties.
		'''
		exceptions:Dict[PartyId, BaseException] = {}
		for conn in self._connections:
			try:
				conn.send(info);
			except Exception as e:
				exceptions[conn.getParty()]=e
		return exceptions


	def size(self) ->int:
		'''
		@return number of connections available
		'''

		return len(self._connections)

	def getConn(self, i:int ) ->ProtocolToPartyConn :
		'''
		@param i the connection number
		@return the ith connection
		'''
		return self._connections[i]

	def __iter__(self):
		return iter(self._connections)

	def With(self, conn:ProtocolToPartyConn) ->"ProtocolToPartyConnections" :
		newconnections:List[ProtocolToPartyConn] = list(self._connections)
		newconnections.append(conn)
		return ProtocolToPartyConnections(newconnections)

	def __repr__(self)->str:
		return "ConnectionWithParties" + str(self._connections)

	def __hash__(self) -> int:
		return hash(tuple(self._connections))

	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			 and  self._connections == other._connections


	def _getParties(self) -> List[PartyId]:
		'''
		@return list (set) of parties currently in the connections.
		'''
		return list(set([ con.getParty() for con in self._connections ]))
