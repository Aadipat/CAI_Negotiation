import threading
from typing import TypeVar, List, cast, Optional

from tudelft.utilities.listener.Listener import Listener
from tudelft_utilities_logging.ReportToLogger import ReportToLogger
from tudelft_utilities_logging.Reporter import Reporter

from geniusweb.actions.Action import Action
from geniusweb.connection.ConnectionEnd import ConnectionEnd
from geniusweb.inform.Inform import Inform
from geniusweb.party.Party import Party



class DefaultParty (Party, Listener[Inform]):
	'''
	Party with default implementation to handle the connection.
	'''

	def __init__(self, reporter:Reporter=None):
		'''
		@param reporter the reporter to use. Generated automatically if None
		'''
		if not reporter:
			reporter = ReportToLogger(self.__class__.__name__)
		if not isinstance(reporter, Reporter):
			raise ValueError("reporter must be instance of reporter, got "+str(reporter))
		self._reporter=reporter
		self._connection: Optional[ConnectionEnd[Inform,Action]] = None
		self._lock = threading.Lock()

	def connect(self, connection: ConnectionEnd[Inform, Action] ):
		try:
			self._lock.acquire()
			if self._connection:
				raise ValueError("Already connected")
			self._connection = connection
			self._connection.addListener(self)
		finally:
			self._lock.release()

	#Override
	def disconnect(self):
		self._lock.acquire()
		if self._connection:
			self._connection.removeListener(self)
			self._connection.close()
			self._connection = None #type:ignore
		self._lock.release()
	

	#Override
	def terminate(self):
		self.disconnect();
	

	def getConnection(self) -> Optional[ConnectionEnd[Inform, Action]]:
		'''
		@return currently available connection, or null if not currently
        connected.
		'''
		return self._connection;
	

	def getReporter(self)->Reporter:
		return self._reporter;

