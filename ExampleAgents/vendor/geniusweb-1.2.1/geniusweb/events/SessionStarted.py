from typing import List
from geniusweb.actions.PartyId import PartyId
from geniusweb.events.ProtocolEvent import ProtocolEvent
class SessionStarted (ProtocolEvent):

	def __init__(self, sessionNumber:int, parties: List[PartyId], time:int):
		super().__init__(time)
		self._sessionNumber = sessionNumber
		self._parties = parties

	def getParties(self) -> List[PartyId]:
		return self._parties

	def getSessionNumber(self)->int:
		return self._sessionNumber

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			super().__eq__(other) and self._parties==other._parties \
				and self._sessionNumber==other._sessionNumber

	def __hash__(self):
		return hash((self._time, self._sessionNumber, tuple(self._parties)))
		
	def __repr__(self)->str:
		return "SessionStarted[" + str(self._sessionNumber) + "," +\
			str(self._parties) + "," + str(self.getTime())+ "]"

