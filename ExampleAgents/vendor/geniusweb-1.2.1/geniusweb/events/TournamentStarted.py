from geniusweb.events.ProtocolEvent import ProtocolEvent

class TournamentStarted (ProtocolEvent):

	def __init__(self, numberOfSessions:int=0,time:int=0):
		'''
		@param numberOfSessions the total number of sessions in the tournament
		@param time              the current timestamp
	    '''
		super().__init__(time)
		self._numberOfSessions = numberOfSessions
	
	def getNumberOfSessions(self) -> int:
		return self._numberOfSessions

	def __repr__(self) -> str:
		return "TournamentStarted[" + str(self.getTime()) + "," + str(self._numberOfSessions) + "]"
	
	def __hash__(self):
		return hash((self._time, self._numberOfSessions))
	
	def __eq__(self, other) -> bool:
		return super().__eq__(other) and self.getTime()==other.getTime() \
				and self._numberOfSessions==other._numberOfSessions
				